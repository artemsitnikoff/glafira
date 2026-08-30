"""Тесты сервиса склейки дублей кандидатов (services/candidate_merge.py).

Фикстуры — из conftest: db_session, admin_user (создаёт компанию), test_company.
Сущности строим напрямую в тест-сессии. merge_component НЕ коммитит — управляем
транзакцией в тесте (flush/commit внутри транзакции фикстуры db_session).

⚠️ Локально НЕ гоняются (нет рантайма) — только py_compile. Прогон на VPS.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import (
    Application,
    Candidate,
    CandidateExperience,
    CandidateTag,
    Comment,
    Employee,
    StageHistory,
    Tag,
    Vacancy,
)
from app.services.candidate_merge import (
    compute_components,
    load_company_candidates,
    merge_component,
)


# --- helpers -----------------------------------------------------------------

async def _mk_candidate(session, company_id, *, last_name="Иванов", first_name="Иван",
                        phone=None, email=None, source="manual", created_at=None, **kw):
    c = Candidate(
        company_id=company_id, last_name=last_name, first_name=first_name,
        source=source, phone=phone, email=email, **kw,
    )
    session.add(c)
    await session.flush()
    if created_at is not None:
        c.created_at = created_at
        await session.flush()
    return c


async def _mk_comment(session, company_id, candidate_id, author_user_id, body="c",
                      application_id=None, source="manual", external_id=None):
    cm = Comment(
        company_id=company_id, candidate_id=candidate_id, author_user_id=author_user_id,
        body=body, application_id=application_id, source=source, external_id=external_id,
    )
    session.add(cm)
    await session.flush()
    return cm


async def _mk_vacancy(session, company_id, name="Python"):
    v = Vacancy(company_id=company_id, name=name, status="active")
    session.add(v)
    await session.flush()
    return v


async def _mk_application(session, company_id, candidate_id, vacancy_id, stage="response",
                          hh_negotiation_id=None, created_at=None):
    a = Application(
        company_id=company_id, candidate_id=candidate_id, vacancy_id=vacancy_id,
        stage=stage, hh_negotiation_id=hh_negotiation_id,
    )
    session.add(a)
    await session.flush()
    if created_at is not None:
        a.created_at = created_at
        await session.flush()
    return a


async def _count(session, model, **filters):
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return (await session.execute(stmt)).scalar_one()


# --- 1. простой мерж 2 дублей ------------------------------------------------

@pytest.mark.asyncio
async def test_simple_merge_two_duplicates(db_session, test_company, admin_user):
    cid = test_company.id
    # оба Иванов + один телефон → сильное ребро (phone AND last_name)
    c1 = await _mk_candidate(db_session, cid, phone="79001112233", email="a@x.ru")
    c2 = await _mk_candidate(db_session, cid, phone="+7 900 111-22-33", email=None, source="hh")
    # c1 богаче (2 коммента) → survivor; c2 (1 коммент) → loser
    await _mk_comment(db_session, cid, c1.id, admin_user.id, body="s1")
    await _mk_comment(db_session, cid, c1.id, admin_user.id, body="s2")
    await _mk_comment(db_session, cid, c2.id, admin_user.id, body="l1")
    await db_session.flush()

    res = await merge_component(db_session, cid, [c1.id, c2.id])
    await db_session.commit()
    db_session.expunge_all()  # детач: значения PK сохраняются (синхронный доступ без IO), get() ниже перечитает свежее

    assert res.skipped is False and res.error is None
    assert res.survivor_id == c1.id
    assert res.merged_ids == [c2.id]

    surv = await db_session.get(Candidate, c1.id)
    loser = await db_session.get(Candidate, c2.id)
    assert surv.deleted_at is None
    assert loser.deleted_at is not None
    assert loser.duplicate_of == c1.id
    assert loser.is_duplicate is True
    assert loser.extra.get("merged_into") == str(c1.id)

    # 3 коммента (2 survivor + 1 перенесённый) все на survivor, у loser — 0
    assert await _count(db_session, Comment, candidate_id=c1.id) == 3
    assert await _count(db_session, Comment, candidate_id=c2.id) == 0


# --- 2. коллизия заявок на одной вакансии ------------------------------------

@pytest.mark.asyncio
async def test_application_collision_most_advanced_wins(db_session, test_company, admin_user):
    cid = test_company.id
    now = datetime.now(timezone.utc)
    # c1 старше → при равной «богатости» станет survivor; его заявка 'response' (продвинутее)
    c1 = await _mk_candidate(db_session, cid, phone="79005550011", email="k@x.ru",
                             created_at=now - timedelta(days=10))
    c2 = await _mk_candidate(db_session, cid, phone="79005550011", email="k@x.ru",
                             source="hh", created_at=now - timedelta(days=1))
    v = await _mk_vacancy(db_session, cid)
    app_win = await _mk_application(db_session, cid, c1.id, v.id, stage="response",
                                    hh_negotiation_id="N1")
    app_lose = await _mk_application(db_session, cid, c2.id, v.id, stage="rejected",
                                     hh_negotiation_id="N2")
    # c1 богаче (2 плоских коммента) → survivor, а его заявка 'response' и есть winner
    await _mk_comment(db_session, cid, c1.id, admin_user.id, body="s1")
    await _mk_comment(db_session, cid, c1.id, admin_user.id, body="s2")
    # ребёнок ПРОИГРАВШЕЙ заявки — должен переехать на winner-app
    sh = StageHistory(application_id=app_lose.id, from_stage=None, to_stage="rejected",
                      actor_type="system")
    db_session.add(sh)
    lose_comment = await _mk_comment(db_session, cid, c2.id, admin_user.id,
                                     application_id=app_lose.id, body="on-lose")
    await db_session.flush()

    res = await merge_component(db_session, cid, [c1.id, c2.id])
    await db_session.commit()
    db_session.expunge_all()

    assert res.survivor_id == c1.id
    assert res.app_collisions_resolved == 1
    assert res.collision_details[0]["winning_stage"] == "response"

    # ровно ОДНА заявка на вакансии, со stage='response'
    apps = (await db_session.execute(
        select(Application).where(Application.vacancy_id == v.id)
    )).scalars().all()
    assert len(apps) == 1
    assert apps[0].id == app_win.id
    assert apps[0].stage == "response"
    assert apps[0].candidate_id == c1.id

    # дети проигравшей заявки переехали на winner-app
    moved_sh = await db_session.get(StageHistory, sh.id)
    assert moved_sh.application_id == app_win.id
    moved_cm = await db_session.get(Comment, lose_comment.id)
    assert moved_cm.application_id == app_win.id
    assert moved_cm.candidate_id == c1.id

    # nid проигравшей заявки — в extra survivor (поллер не переимпортирует)
    surv = await db_session.get(Candidate, c1.id)
    assert "N2" in (surv.extra.get("hh_seen_nids") or [])


# --- 3. survivor = employee, несмотря на «беднее» ----------------------------

@pytest.mark.asyncio
async def test_survivor_is_employee_despite_poorer(db_session, test_company, admin_user):
    cid = test_company.id
    c1 = await _mk_candidate(db_session, cid, phone="79007778899", email="e@x.ru")  # employee, беднее
    c2 = await _mk_candidate(db_session, cid, phone="79007778899", email="e@x.ru", source="hh")
    # c2 богаче (2 коммента), но у c1 есть строка employee
    await _mk_comment(db_session, cid, c2.id, admin_user.id, body="l1")
    await _mk_comment(db_session, cid, c2.id, admin_user.id, body="l2")
    emp = Employee(company_id=cid, candidate_id=c1.id, full_name="Иван Иванов",
                   start_date=datetime.now(timezone.utc).date())
    db_session.add(emp)
    await db_session.flush()

    res = await merge_component(db_session, cid, [c1.id, c2.id])
    await db_session.commit()
    db_session.expunge_all()

    assert res.survivor_id == c1.id  # employee победил «богатство»
    loser = await db_session.get(Candidate, c2.id)
    assert loser.deleted_at is not None and loser.duplicate_of == c1.id
    # employee остался на survivor, комменты loser переехали
    assert await _count(db_session, Employee, candidate_id=c1.id) == 1
    assert await _count(db_session, Comment, candidate_id=c1.id) == 2


# --- 4. слабое ребро → НЕ мержим, в review -----------------------------------

@pytest.mark.asyncio
async def test_weak_edge_not_merged_goes_to_review(db_session, test_company, admin_user):
    cid = test_company.id
    # общий телефон, но разные фамилии И разный email → слабое ребро
    c1 = await _mk_candidate(db_session, cid, last_name="Иванов", phone="79001234567", email="a@x.ru")
    c2 = await _mk_candidate(db_session, cid, last_name="Петров", phone="79001234567", email="b@y.ru")
    await db_session.flush()

    candidates = await load_company_candidates(db_session, cid)
    components, review = compute_components(candidates)

    assert components == []  # нечего авто-мержить
    review_ids = {r.candidate_id for r in review}
    assert c1.id in review_ids and c2.id in review_ids
    # оба живы (мы их не трогали)
    assert (await db_session.get(Candidate, c1.id)).deleted_at is None
    assert (await db_session.get(Candidate, c2.id)).deleted_at is None


# --- 5. уник-коллизия candidate_tags -----------------------------------------

@pytest.mark.asyncio
async def test_candidate_tags_unique_collision(db_session, test_company, admin_user):
    cid = test_company.id
    c1 = await _mk_candidate(db_session, cid, phone="79002223344", email="t@x.ru")
    c2 = await _mk_candidate(db_session, cid, phone="79002223344", email="t@x.ru", source="hh")
    # c1 богаче → survivor
    await _mk_comment(db_session, cid, c1.id, admin_user.id, body="s")
    tag_a = Tag(company_id=cid, name="A")
    tag_b = Tag(company_id=cid, name="B")
    db_session.add_all([tag_a, tag_b])
    await db_session.flush()
    # общий тег A у обоих + уникальный B у loser
    db_session.add_all([
        CandidateTag(company_id=cid, candidate_id=c1.id, tag_id=tag_a.id),
        CandidateTag(company_id=cid, candidate_id=c2.id, tag_id=tag_a.id),
        CandidateTag(company_id=cid, candidate_id=c2.id, tag_id=tag_b.id),
    ])
    await db_session.flush()

    res = await merge_component(db_session, cid, [c1.id, c2.id])
    await db_session.commit()  # не должно упасть на uq (candidate_id, tag_id)

    assert res.survivor_id == c1.id
    # у survivor ровно 2 тега (A, B), у loser — 0, дубль A снят
    assert await _count(db_session, CandidateTag, candidate_id=c1.id) == 2
    assert await _count(db_session, CandidateTag, candidate_id=c2.id) == 0


# --- 6. изоляция по компании -------------------------------------------------

@pytest.mark.asyncio
async def test_company_isolation(db_session, test_company, admin_user, other_company):
    a_id = test_company.id
    b_id = other_company.id
    # одинаковый телефон+фамилия, но РАЗНЫЕ компании
    ca = await _mk_candidate(db_session, a_id, phone="79000000001", email="z@x.ru")
    cb = await _mk_candidate(db_session, b_id, phone="79000000001", email="z@x.ru")
    await db_session.flush()

    a_candidates = await load_company_candidates(db_session, a_id)
    comps_a, _ = compute_components(a_candidates)
    b_candidates = await load_company_candidates(db_session, b_id)
    comps_b, _ = compute_components(b_candidates)

    # в каждой компании — по одному кандидату, компонентов нет
    assert comps_a == [] and comps_b == []
    assert {c.id for c in a_candidates} == {ca.id}
    assert {c.id for c in b_candidates} == {cb.id}


# --- 7. идемпотентность ------------------------------------------------------

@pytest.mark.asyncio
async def test_idempotent_second_merge_is_noop(db_session, test_company, admin_user):
    cid = test_company.id
    c1 = await _mk_candidate(db_session, cid, phone="79003334455", email="i@x.ru")
    c2 = await _mk_candidate(db_session, cid, phone="79003334455", email="i@x.ru", source="hh")
    await _mk_comment(db_session, cid, c1.id, admin_user.id, body="s")
    await db_session.flush()

    res1 = await merge_component(db_session, cid, [c1.id, c2.id])
    await db_session.commit()
    db_session.expunge_all()
    assert res1.skipped is False and res1.survivor_id == c1.id

    # повторный мерж того же компонента — no-op (loser уже удалён → живых <2)
    res2 = await merge_component(db_session, cid, [c1.id, c2.id])
    await db_session.commit()
    db_session.expunge_all()
    assert res2.skipped is True

    surv = await db_session.get(Candidate, c1.id)
    loser = await db_session.get(Candidate, c2.id)
    assert surv.deleted_at is None
    assert loser.deleted_at is not None and loser.duplicate_of == c1.id


# --- 8. секции резюме --------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_sections_reparent_and_no_dup(db_session, test_company, admin_user):
    cid = test_company.id

    # Сценарий A: survivor БЕЗ опыта (но богаче коммента́ми) + loser с опытом → опыт у survivor
    s1 = await _mk_candidate(db_session, cid, phone="79004440001", email="a1@x.ru")
    l1 = await _mk_candidate(db_session, cid, phone="79004440001", email="a1@x.ru", source="hh")
    # survivor богаче (3 коммента), опыта НЕТ; loser — 1 опыт
    for i in range(3):
        await _mk_comment(db_session, cid, s1.id, admin_user.id, body=f"s{i}")
    db_session.add(CandidateExperience(company_id=cid, candidate_id=l1.id,
                                       position="Dev", order_index=0))
    await db_session.flush()

    resA = await merge_component(db_session, cid, [s1.id, l1.id])
    await db_session.commit()
    db_session.expunge_all()
    assert resA.survivor_id == s1.id
    assert await _count(db_session, CandidateExperience, candidate_id=s1.id) == 1
    assert await _count(db_session, CandidateExperience, candidate_id=l1.id) == 0

    # Сценарий B: survivor С опытом + loser с опытом → опыт loser НЕ дублируется
    s2 = await _mk_candidate(db_session, cid, phone="79004440002", email="b2@x.ru")
    l2 = await _mk_candidate(db_session, cid, phone="79004440002", email="b2@x.ru", source="hh")
    for i in range(3):
        await _mk_comment(db_session, cid, s2.id, admin_user.id, body=f"sb{i}")
    db_session.add(CandidateExperience(company_id=cid, candidate_id=s2.id,
                                       position="Own", order_index=0))
    db_session.add(CandidateExperience(company_id=cid, candidate_id=l2.id,
                                       position="Other", order_index=0))
    await db_session.flush()

    resB = await merge_component(db_session, cid, [s2.id, l2.id])
    await db_session.commit()
    db_session.expunge_all()
    assert resB.survivor_id == s2.id
    # только СВОЙ опыт survivor (1), loser'ов опыт удалён (не 2)
    assert await _count(db_session, CandidateExperience, candidate_id=s2.id) == 1
    assert await _count(db_session, CandidateExperience, candidate_id=l2.id) == 0


# --- 9. плейсхолдер-телефон НЕ образует компонента (защита от смешения) -------

@pytest.mark.asyncio
async def test_placeholder_phone_not_merged(db_session, test_company, admin_user):
    cid = test_company.id
    # РАЗНЫЕ люди с плейсхолдер-телефоном (все нули / 8-800) и разными email → не мержим
    await _mk_candidate(db_session, cid, last_name="Иванов", phone="70000000000", email="a@x.ru")
    await _mk_candidate(db_session, cid, last_name="Иванов", phone="70000000000", email="b@y.ru")
    await _mk_candidate(db_session, cid, last_name="Петров", phone="78005553535", email="c@z.ru")
    await _mk_candidate(db_session, cid, last_name="Петров", phone="78005553535", email="d@w.ru")
    await db_session.flush()

    candidates = await load_company_candidates(db_session, cid)
    components, _review = compute_components(candidates)
    # плейсхолдер-ключи отброшены → ни рёбер, ни компонентов (никого не слили)
    assert components == []


# --- 10. пустая фамилия НЕ бриджит разных людей с общим телефоном -------------

@pytest.mark.asyncio
async def test_empty_lastname_not_bridged(db_session, test_company, admin_user):
    cid = test_company.id
    # пустая фамилия + двое с разными фамилиями, общий телефон, разные email
    c_empty = await _mk_candidate(db_session, cid, last_name="", first_name="Аноним",
                                  phone="79001112200", email="e@x.ru")
    c_p = await _mk_candidate(db_session, cid, last_name="Петров", phone="79001112200", email="p@x.ru")
    c_s = await _mk_candidate(db_session, cid, last_name="Сидоров", phone="79001112200", email="s@x.ru")
    await db_session.flush()

    candidates = await load_company_candidates(db_session, cid)
    components, review = compute_components(candidates)
    # пустая фамилия НЕ даёт сильного ребра → авто-мержа нет, все в review (на глаза)
    assert components == []
    review_ids = {r.candidate_id for r in review}
    assert {c_empty.id, c_p.id, c_s.id} <= review_ids
