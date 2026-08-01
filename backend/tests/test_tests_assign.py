"""Тесты фазы 2Б модуля «Тесты»: назначение тестов, авто-отправка на этапе,
авто-отказ по результату, рекрутёрские результат-эндпоинты, поля воронки.

Модели тестового модуля импортируем через `from app.models import tests as tm` —
чтобы классы Test*/… не коллектились pytest'ом как тест-классы.
Доставка ссылки (email/telegram/hh) в сеть НЕ идёт: deliver_test_link мокается.
"""
import re
import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.models import Application, Candidate, Company, StageHistory, Vacancy
from app.models import tests as tm
from app import seed_tests as seed_mod
from app.services import tests_assign as ta
from app.services import tests_public as tp


# ── Хелперы построения окружения ────────────────────────────────────────────────
async def _make_company(db_session) -> uuid.UUID:
    comp = Company(id=uuid.uuid4(), name="Компания для тестов назначения")
    db_session.add(comp)
    await db_session.flush()
    return comp.id


async def _logic_test(db_session, company_id, *, auto_reject_below=None):
    """Засеять тест «Логика» (20 матриц) и, при необходимости, задать порог автоотказа."""
    await seed_mod.seed_logic_test(db_session, company_id)
    await db_session.flush()
    test = (
        await db_session.execute(
            select(tm.Test).where(tm.Test.company_id == company_id, tm.Test.key == "logic")
        )
    ).scalar_one()
    if auto_reject_below is not None:
        test.auto_reject_below = auto_reject_below
        await db_session.flush()
    return test


async def _make_app(db_session, company_id, *, stage="interview"):
    cand = Candidate(
        company_id=company_id,
        last_name="Иванов",
        first_name="Иван",
        source="manual",
        email="ivan@example.com",
        phone="+7 900 000 00 00",
        city="Москва",
    )
    db_session.add(cand)
    vac = Vacancy(company_id=company_id, name="Тест-вакансия", status="active")
    db_session.add(vac)
    await db_session.flush()
    app = Application(
        company_id=company_id, candidate_id=cand.id, vacancy_id=vac.id, stage=stage
    )
    db_session.add(app)
    await db_session.flush()
    return app, cand, vac


async def _logic_items(db_session, test_id):
    return (
        await db_session.execute(
            select(tm.TestItem)
            .where(tm.TestItem.test_id == test_id)
            .order_by(tm.TestItem.order_index)
        )
    ).scalars().all()


# ── Назначение через API ────────────────────────────────────────────────────────
async def test_assign_creates_assignment_bound_to_application_idempotent(
    async_client, db_session, admin_user, auth_headers, monkeypatch
):
    monkeypatch.setattr("app.services.tests_assign.deliver_test_link", AsyncMock(), raising=True)
    cid = admin_user.company_id
    app, cand, vac = await _make_app(db_session, cid)
    test = await _logic_test(db_session, cid)
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/applications/{app.id}/tests/assign",
        json={"test_id": str(test.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["test_id"] == str(test.id)
    assert body["status"] == "sent"
    assert body["url"] and "/test/" in body["url"]
    first_id = body["id"]

    # Привязка к Application: candidate_id взят ИЗ заявки (не передавался клиентом).
    assignments = (
        await db_session.execute(
            select(tm.TestAssignment).where(tm.TestAssignment.application_id == app.id)
        )
    ).scalars().all()
    assert len(assignments) == 1
    assert assignments[0].candidate_id == cand.id
    assert assignments[0].token

    # Идемпотентность: тот же test_id по той же заявке → та же assignment, второго токена нет.
    resp2 = await async_client.post(
        f"/api/v1/applications/{app.id}/tests/assign",
        json={"test_id": str(test.id)},
        headers=auth_headers,
    )
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["id"] == first_id
    assignments2 = (
        await db_session.execute(
            select(tm.TestAssignment).where(tm.TestAssignment.application_id == app.id)
        )
    ).scalars().all()
    assert len(assignments2) == 1


async def test_remind_and_cancel(
    async_client, db_session, admin_user, auth_headers, monkeypatch
):
    monkeypatch.setattr("app.services.tests_assign.deliver_test_link", AsyncMock(), raising=True)
    cid = admin_user.company_id
    app, cand, vac = await _make_app(db_session, cid)
    test = await _logic_test(db_session, cid)
    await db_session.commit()

    r = await async_client.post(
        f"/api/v1/applications/{app.id}/tests/assign",
        json={"test_id": str(test.id)},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    # remind активного (sent) → 200, статус не меняется
    rr = await async_client.post(
        f"/api/v1/applications/{app.id}/tests/{aid}/remind", headers=auth_headers
    )
    assert rr.status_code == 200, rr.text
    assert rr.json()["status"] == "sent"

    # cancel → 'cancelled'
    rc = await async_client.post(
        f"/api/v1/applications/{app.id}/tests/{aid}/cancel", headers=auth_headers
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["status"] == "cancelled"


async def test_cancel_completed_conflict(
    async_client, db_session, admin_user, auth_headers
):
    cid = admin_user.company_id
    app, cand, vac = await _make_app(db_session, cid)
    test = await _logic_test(db_session, cid)
    assignment = tm.TestAssignment(
        company_id=cid,
        application_id=app.id,
        candidate_id=cand.id,
        test_id=test.id,
        token=secrets.token_urlsafe(16),
        status="completed",
    )
    db_session.add(assignment)
    await db_session.commit()

    rc = await async_client.post(
        f"/api/v1/applications/{app.id}/tests/{assignment.id}/cancel", headers=auth_headers
    )
    assert rc.status_code == 409, rc.text


async def test_assign_manager_not_assigned_forbidden(
    async_client, db_session, admin_user, manager_user, manager_headers, monkeypatch
):
    monkeypatch.setattr("app.services.tests_assign.deliver_test_link", AsyncMock(), raising=True)
    cid = admin_user.company_id
    app, cand, vac = await _make_app(db_session, cid)  # вакансия НЕ назначена менеджеру
    test = await _logic_test(db_session, cid)
    await db_session.commit()

    r = await async_client.post(
        f"/api/v1/applications/{app.id}/tests/assign",
        json={"test_id": str(test.id)},
        headers=manager_headers,
    )
    assert r.status_code == 403, r.text


# ── Авто-отправка на этапе ──────────────────────────────────────────────────────
async def test_send_test_links_at_stage_idempotent(db_session, admin_user, monkeypatch):
    monkeypatch.setattr("app.services.tests_assign.deliver_test_link", AsyncMock(), raising=True)
    cid = admin_user.company_id
    test = await _logic_test(db_session, cid)

    cand = Candidate(
        company_id=cid, last_name="Петров", first_name="Пётр", source="manual",
        email="petr@example.com",
    )
    db_session.add(cand)
    vac = Vacancy(
        company_id=cid, name="Авто-тест вакансия", status="active",
        auto_test=True, auto_test_id=test.id, auto_test_stage="interview",
    )
    db_session.add(vac)
    await db_session.flush()
    app = Application(company_id=cid, candidate_id=cand.id, vacancy_id=vac.id, stage="interview")
    db_session.add(app)
    await db_session.commit()

    stats = await ta.send_test_links(db_session, cid)
    assert stats["sent"] == 1
    assignments = (
        await db_session.execute(
            select(tm.TestAssignment).where(tm.TestAssignment.application_id == app.id)
        )
    ).scalars().all()
    assert len(assignments) == 1
    assert assignments[0].channel == "email"  # авто = email-only
    assert assignments[0].created_by is None

    # Повторный прогон НЕ плодит (идемпотентность → skipped_active).
    stats2 = await ta.send_test_links(db_session, cid)
    assert stats2["sent"] == 0
    assert stats2["skipped_active"] == 1
    assignments2 = (
        await db_session.execute(
            select(tm.TestAssignment).where(tm.TestAssignment.application_id == app.id)
        )
    ).scalars().all()
    assert len(assignments2) == 1


# ── Авто-отказ по результату (finalize_attempt) ─────────────────────────────────
async def _prep_attempt(db_session, cid, test, app, cand, *, correct_count=0, answered=5):
    """Собрать assignment(started)+attempt(in_progress)+ответы. По умолчанию все неверные."""
    now = datetime.now(timezone.utc)
    assignment = tm.TestAssignment(
        company_id=cid, application_id=app.id, candidate_id=cand.id, test_id=test.id,
        token=secrets.token_urlsafe(16), status="started",
    )
    db_session.add(assignment)
    await db_session.flush()
    attempt = tm.TestAttempt(
        company_id=cid, assignment_id=assignment.id, application_id=app.id,
        started_at=now, current_item_index=0, options_seed=12345, status="in_progress",
    )
    db_session.add(attempt)
    await db_session.flush()
    items = await _logic_items(db_session, test.id)
    for i, it in enumerate(items[:answered]):
        db_session.add(tm.TestAnswer(
            company_id=cid, attempt_id=attempt.id, item_id=it.id,
            chosen_option_id=(it.correct_option_id if i < correct_count else "x"),
            is_correct=(i < correct_count), time_ms=20000,
        ))
    await db_session.flush()
    return assignment, attempt, items, now


async def test_finalize_auto_reject_below_threshold(db_session):
    cid = await _make_company(db_session)
    test = await _logic_test(db_session, cid, auto_reject_below=10)
    app, cand, vac = await _make_app(db_session, cid, stage="interview")
    assignment, attempt, items, now = await _prep_attempt(db_session, cid, test, app, cand)

    # raw_score = 0 (все неверные) < 10 → автоотказ
    await tp.finalize_attempt(
        db_session, attempt=attempt, assignment=assignment, test=test,
        items=items, blocks=[], now=now,
    )

    await db_session.refresh(app)
    assert app.stage == "rejected"

    sh = (
        await db_session.execute(
            select(StageHistory).where(
                StageHistory.application_id == app.id, StageHistory.to_stage == "rejected"
            )
        )
    ).scalars().all()
    assert len(sh) == 1
    assert sh[0].actor_type == "ai"

    res = (
        await db_session.execute(
            select(tm.TestResult).where(tm.TestResult.application_id == app.id)
        )
    ).scalar_one()
    assert res.raw_score == 0


async def test_finalize_no_auto_reject_when_threshold_none(db_session):
    cid = await _make_company(db_session)
    test = await _logic_test(db_session, cid, auto_reject_below=None)  # OFF
    app, cand, vac = await _make_app(db_session, cid, stage="interview")
    assignment, attempt, items, now = await _prep_attempt(db_session, cid, test, app, cand)

    await tp.finalize_attempt(
        db_session, attempt=attempt, assignment=assignment, test=test,
        items=items, blocks=[], now=now,
    )

    await db_session.refresh(app)
    assert app.stage == "interview"  # заявка НЕ тронута

    res = (
        await db_session.execute(
            select(tm.TestResult).where(tm.TestResult.application_id == app.id)
        )
    ).scalar_one()
    assert res is not None  # результат всё равно записан


# ── Рекрутёрский результат-эндпоинт ─────────────────────────────────────────────
async def _completed_result(db_session, cid, test, app, cand, *, raw_score=1, category="low"):
    now = datetime.now(timezone.utc)
    asg = tm.TestAssignment(
        company_id=cid, application_id=app.id, candidate_id=cand.id, test_id=test.id,
        token=secrets.token_urlsafe(16), status="completed",
    )
    db_session.add(asg)
    await db_session.flush()
    attempt = tm.TestAttempt(
        company_id=cid, assignment_id=asg.id, application_id=app.id,
        started_at=now, current_item_index=20, status="completed", finished_at=now,
    )
    db_session.add(attempt)
    await db_session.flush()
    items = await _logic_items(db_session, test.id)
    db_session.add(tm.TestAnswer(
        company_id=cid, attempt_id=attempt.id, item_id=items[0].id,
        chosen_option_id=items[0].correct_option_id, is_correct=True, time_ms=30000,
    ))
    db_session.add(tm.TestAnswer(
        company_id=cid, attempt_id=attempt.id, item_id=items[1].id,
        chosen_option_id="x", is_correct=False, time_ms=25000,
    ))
    res = tm.TestResult(
        company_id=cid, application_id=app.id, assignment_id=asg.id, test_id=test.id,
        raw_score=raw_score, max_score=20, block_scores={}, category=category,
        percentile=None, validity_flags=[], duration_sec=100, completed_at=now,
    )
    db_session.add(res)
    return asg, res


async def test_result_endpoint_returns_result_for_recruiter(
    async_client, db_session, admin_user, auth_headers
):
    cid = admin_user.company_id
    test = await _logic_test(db_session, cid)
    app, cand, vac = await _make_app(db_session, cid)
    await _completed_result(db_session, cid, test, app, cand, raw_score=1, category="low")
    await db_session.commit()

    r = await async_client.get(
        f"/api/v1/applications/{app.id}/tests", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    item = data[0]
    assert item["status"] == "completed"
    assert item["result"] is not None
    result = item["result"]
    assert result["raw_score"] == 1
    # percentile None при базе компании < 30
    assert result["percentile"] is None
    # рекрутёру верность ответов показывать МОЖНО
    assert len(result["answers"]) == 2
    assert all("is_correct" in a for a in result["answers"])
    assert any(a["is_correct"] is True for a in result["answers"])
    # ярлык категории берётся из порогов теста (low → «Низкий»)
    assert result["category"] == "low"
    assert result["category_label"] == "Низкий"


async def test_result_endpoint_company_isolation_404(
    async_client, db_session, admin_user, other_company, auth_headers
):
    other_cid = other_company.id
    test = await _logic_test(db_session, other_cid)
    app, cand, vac = await _make_app(db_session, other_cid)
    await db_session.commit()

    # admin (компания по умолчанию) читает заявку ЧУЖОЙ компании → 404
    r = await async_client.get(
        f"/api/v1/applications/{app.id}/tests", headers=auth_headers
    )
    assert r.status_code == 404, r.text


async def test_result_bound_to_application_not_candidate(
    async_client, db_session, admin_user, auth_headers
):
    """Один кандидат в ДВУХ вакансиях (2 заявки) → каждый GET отдаёт СВОЙ результат."""
    cid = admin_user.company_id
    test = await _logic_test(db_session, cid)
    cand = Candidate(
        company_id=cid, last_name="Сидоров", first_name="Сидор", source="manual",
        email="sidor@example.com",
    )
    db_session.add(cand)
    vac1 = Vacancy(company_id=cid, name="Вакансия 1", status="active")
    vac2 = Vacancy(company_id=cid, name="Вакансия 2", status="active")
    db_session.add_all([vac1, vac2])
    await db_session.flush()
    app1 = Application(company_id=cid, candidate_id=cand.id, vacancy_id=vac1.id, stage="interview")
    app2 = Application(company_id=cid, candidate_id=cand.id, vacancy_id=vac2.id, stage="interview")
    db_session.add_all([app1, app2])
    await db_session.flush()

    now = datetime.now(timezone.utc)
    for app_obj, score in ((app1, 5), (app2, 15)):
        asg = tm.TestAssignment(
            company_id=cid, application_id=app_obj.id, candidate_id=cand.id, test_id=test.id,
            token=secrets.token_urlsafe(16), status="completed",
        )
        db_session.add(asg)
        await db_session.flush()
        db_session.add(tm.TestResult(
            company_id=cid, application_id=app_obj.id, assignment_id=asg.id, test_id=test.id,
            raw_score=score, max_score=20, block_scores={}, category=None, percentile=None,
            validity_flags=[], duration_sec=100, completed_at=now,
        ))
    await db_session.commit()

    r1 = await async_client.get(f"/api/v1/applications/{app1.id}/tests", headers=auth_headers)
    r2 = await async_client.get(f"/api/v1/applications/{app2.id}/tests", headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()[0]["result"]["raw_score"] == 5
    assert r2.json()[0]["result"]["raw_score"] == 15


# ── Поля воронки (ApplicationRow) ───────────────────────────────────────────────
async def test_application_row_test_fields(
    async_client, db_session, admin_user, auth_headers
):
    cid = admin_user.company_id
    test = await _logic_test(db_session, cid)
    app, cand, vac = await _make_app(db_session, cid, stage="interview")
    now = datetime.now(timezone.utc)
    asg = tm.TestAssignment(
        company_id=cid, application_id=app.id, candidate_id=cand.id, test_id=test.id,
        token=secrets.token_urlsafe(16), status="completed",
    )
    db_session.add(asg)
    await db_session.flush()
    db_session.add(tm.TestResult(
        company_id=cid, application_id=app.id, assignment_id=asg.id, test_id=test.id,
        raw_score=15, max_score=20, block_scores={}, category="above", percentile=None,
        validity_flags=[], duration_sec=100, completed_at=now,
    ))
    await db_session.commit()

    r = await async_client.get(
        f"/api/v1/vacancies/{vac.id}/applications", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    row = next(x for x in items if x["id"] == str(app.id))
    assert row["test_status"] == "completed"
    assert row["test_score"] == 15
    assert row["test_category"] == "above"


# ── IQ не считается/не упоминается в коде модуля ────────────────────────────────
def test_no_iq_in_module_source():
    from app.api.v1 import tests as tests_router_mod
    from app.schemas import tests as tests_schema_mod

    for mod in (ta, tests_router_mod, tests_schema_mod):
        with open(mod.__file__, encoding="utf-8") as fh:
            src = fh.read()
        assert re.search(r"\biq\b", src, re.IGNORECASE) is None, mod.__file__
