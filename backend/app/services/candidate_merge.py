"""Склейка (merge) накопленных дублей кандидатов в одну «золотую» запись.

Пункт 2 большой правки дедупа: пункт 1 (перекрытие «крана» на импорте hh) уже сделан
в v1.7.22 — новые отклики к существующему кандидату больше не плодят дубль. Здесь —
РАЗОВАЯ склейка того, что уже накопилось до фикса.

Модуль СЕРВИСНЫЙ и ЧИСТЫЙ (без ввода-вывода/argparse) — чтобы покрыть тестами. CLI-
обёртка живёт в `app/jobs/merge_duplicate_candidates.py` и лишь оркеструет сессию,
режимы (dry-run / --execute) и печать отчёта. Вся логика мержа — здесь.

Границы:
- Мержим ТОЛЬКО «сильные» связные компоненты (Tier-1, авто): пара считается сильной,
  если совпадает по (phone AND email) ИЛИ (phone AND last_name) ИЛИ (email AND last_name).
- Спорное (общий телефон, но разные фамилии И разный email — «слабое» ребро) НЕ мержим,
  а собираем в REVIEW-список (Tier-2) на глазной просмотр (решение заказчика).
- Всё строго company-scoped (§2.3). Изменяющее действие → audit_log (§2.2).

⚠️ Уникальные констрейнты, которые обязаны быть обработаны, иначе UPDATE оборвёт
транзакцию: candidate_tags(candidate_id,tag_id), candidate_embeddings(candidate_id),
message_reads(user_id,candidate_id), ai_evaluations(candidate_id,application_id),
employees(application_id) uq_employees_application_id (коллизия «нанят дважды»),
comments talantix-partial(company_id,candidate_id,external_id), applications partial
(company_id,hh_negotiation_id)/(…habr_response_id)/(…avito_application_id).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AiEvaluation,
    Candidate,
    CandidateEducation,
    CandidateEmbedding,
    CandidateExperience,
    CandidateSkill,
    CandidateTag,
    Comment,
    Consent,
    Document,
    Employee,
    Event,
    InterviewLink,
    Message,
    MessageRead,
    StageHistory,
    TestAssignment,
    TestAttempt,
    TestResult,
    Verification,
    Application,
)
from .audit import audit

logger = logging.getLogger(__name__)

_NUM_PREFIX_RE = re.compile(r"^\d+-")  # префикс потока: «023-Тальников»
_NON_DIGIT_RE = re.compile(r"\D")

# Продвинутость этапа (больше = дальше по воронке). Кастомный/неизвестный → «средний»
# (между selected и response) — так он не «съедает» реальный оффер, но обгоняет отклик.
STAGE_RANK: dict[str, int] = {
    "hired": 100,
    "offer": 90,
    "manager": 80,
    "interview": 70,
    "screening": 60,
    "recruiter": 50,
    "selected": 40,
    "response": 30,
    "added": 20,
    "rejected": 10,
}
_UNKNOWN_STAGE_RANK = 35  # между selected(40) и response(30)


def _stage_rank(stage: str | None) -> int:
    if not stage:
        return _UNKNOWN_STAGE_RANK
    return STAGE_RANK.get(stage, _UNKNOWN_STAGE_RANK)


# --- ключи сопоставления (чистые функции) -----------------------------------

def _phone_key(phone: str | None) -> str | None:
    """Последние 10 цифр телефона (длина ≥10), иначе None."""
    if not phone:
        return None
    digits = _NON_DIGIT_RE.sub("", str(phone))
    if len(digits) < 10:
        return None
    return digits[-10:]


def _email_key(email: str | None) -> str | None:
    if not email:
        return None
    key = str(email).strip().lower()
    return key or None


def _last_name_key(last_name: str | None) -> str:
    if not last_name:
        return ""
    return _NUM_PREFIX_RE.sub("", str(last_name).strip()).strip().lower()


def _last_name_strong(a: str | None, b: str | None) -> bool:
    """Строгое совпадение фамилий для СИЛЬНОГО ребра: ОБЕ непусты и равны после
    нормализации. Пустая фамилия = «неизвестно», НЕ совпадение — иначе кандидат с
    пустой фамилией бриджил бы РАЗНЫХ людей, делящих один телефон (в review, не мерж)."""
    ka, kb = _last_name_key(a), _last_name_key(b)
    return bool(ka) and bool(kb) and ka == kb


# Вырожденные ключи (плейсхолдер/мусорный телефон, общий корп-номер): НЕ образуют
# рёбер, иначе схлопнули бы РАЗНЫХ людей в один компонент. Реальный максимум живой
# группы на проде — 8; порог берём с запасом. Плейсхолдер-телефоны: все одинаковые
# цифры (0000000000) и горячая линия 8-800 (её вписывают «за компанию»).
MAX_KEY_GROUP = 15
_PLACEHOLDER_PHONE_RE = re.compile(r"^(?:(\d)\1{9}|800\d{7})$")


def _is_placeholder_phone(key: str) -> bool:
    return bool(_PLACEHOLDER_PHONE_RE.match(key))


def _strip_num_prefix(value: str | None) -> str | None:
    if not value:
        return value
    return _NUM_PREFIX_RE.sub("", str(value)) or value


# --- группировка (union-find по сильным рёбрам) ------------------------------

@dataclass
class ReviewItem:
    candidate_id: UUID
    name: str
    phone: str | None
    email: str | None
    source: str | None


def compute_components(
    candidates: list[Candidate],
) -> tuple[list[list[UUID]], list[ReviewItem]]:
    """Разбить кандидатов ОДНОЙ компании на:
      - components: связные компоненты по СИЛЬНЫМ рёбрам, размер ≥2 (авто-мерж, Tier-1);
      - review: кандидаты, у которых связь ТОЛЬКО слабая (общий телефон/email, но не
        сильное ребро) и которые при этом не попали ни в один авто-компонент (Tier-2).

    Сильные рёбра существуют только между кандидатами, делящими phone или email (каждая
    ветка «сильности» требует phone или email), поэтому кандидатов сравниваем лишь внутри
    групп по phone/email — без общего O(n²).
    """
    by_id: dict[UUID, Candidate] = {c.id: c for c in candidates}
    parent: dict[UUID, UUID] = {c.id: c.id for c in candidates}

    def find(x: UUID) -> UUID:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: UUID, b: UUID) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Пары, делящие phone или email, с флагами какого ключа совпадение.
    pair_flags: dict[frozenset[UUID], list[bool]] = {}

    def _index(getter) -> dict:
        groups: dict[str, list[UUID]] = {}
        for c in candidates:
            k = getter(c)
            if k:
                groups.setdefault(k, []).append(c.id)
        return groups

    phone_groups = _index(lambda c: _phone_key(c.phone))
    email_groups = _index(lambda c: _email_key(c.email))

    # Плейсхолдер-телефоны не образуют рёбер (0000000000 / 8-800 — не личный номер).
    phone_groups = {k: v for k, v in phone_groups.items() if not _is_placeholder_phone(k)}

    def _add_pairs(groups: dict[str, list[UUID]], slot: int) -> None:
        for ids in groups.values():
            if len(ids) > MAX_KEY_GROUP:
                continue  # вырожденный ключ (плейсхолдер/общий) — рёбер не строим
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    key = frozenset((ids[i], ids[j]))
                    flags = pair_flags.get(key)
                    if flags is None:
                        flags = [False, False]
                        pair_flags[key] = flags
                    flags[slot] = True

    _add_pairs(phone_groups, 0)
    _add_pairs(email_groups, 1)

    weak_pairs: list[tuple[UUID, UUID]] = []
    for key, (shares_phone, shares_email) in pair_flags.items():
        a_id, b_id = tuple(key)
        ln_match = _last_name_strong(by_id[a_id].last_name, by_id[b_id].last_name)
        strong = (
            (shares_phone and shares_email)
            or (shares_phone and ln_match)
            or (shares_email and ln_match)
        )
        if strong:
            union(a_id, b_id)
        else:
            weak_pairs.append((a_id, b_id))

    # Компоненты по сильным рёбрам.
    comp_members: dict[UUID, list[UUID]] = {}
    for c in candidates:
        comp_members.setdefault(find(c.id), []).append(c.id)
    components = [ids for ids in comp_members.values() if len(ids) >= 2]
    comp_size = {cid: len(comp_members[find(cid)]) for cid in parent}

    # Review: слабое ребро между РАЗНЫМИ компонентами; в список берём только тех
    # endpoints, кто сам НЕ в авто-компоненте («связь ТОЛЬКО слабая»).
    review_ids: set[UUID] = set()
    for a_id, b_id in weak_pairs:
        if find(a_id) == find(b_id):
            continue
        for x in (a_id, b_id):
            if comp_size.get(x, 1) == 1:
                review_ids.add(x)

    review = [
        ReviewItem(
            candidate_id=x,
            name=by_id[x].full_name,
            phone=by_id[x].phone,
            email=by_id[x].email,
            source=by_id[x].source,
        )
        for x in review_ids
    ]
    review.sort(key=lambda r: (r.phone or "", r.email or "", str(r.candidate_id)))
    return components, review


# --- результат мержа одного компонента --------------------------------------

@dataclass
class ComponentResult:
    company_id: UUID | None = None
    survivor_id: UUID | None = None
    merged_ids: list[UUID] = field(default_factory=list)
    apps_reparented: int = 0
    app_collisions_resolved: int = 0
    collision_details: list[dict] = field(default_factory=list)
    skipped: bool = False
    error: str | None = None


# --- загрузка/подсчёты -------------------------------------------------------

async def load_company_candidates(session: AsyncSession, company_id: UUID) -> list[Candidate]:
    """Живые (deleted_at IS NULL) кандидаты компании — материал для группировки."""
    res = await session.execute(
        select(Candidate).where(
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
        )
    )
    return list(res.scalars().all())


async def _count_map(session: AsyncSession, col, member_ids: list[UUID]) -> dict[UUID, int]:
    res = await session.execute(
        select(col, func.count()).where(col.in_(member_ids)).group_by(col)
    )
    return {row[0]: row[1] for row in res.all()}


async def _richness_counts(session: AsyncSession, member_ids: list[UUID]) -> dict[UUID, int]:
    """Суммарное число дочерних записей на кандидата — метрика «богатейшего»."""
    total: dict[UUID, int] = {mid: 0 for mid in member_ids}
    cols = [
        Application.candidate_id,
        Comment.candidate_id,
        Message.candidate_id,
        Document.candidate_id,
        Verification.candidate_id,
        CandidateExperience.candidate_id,
        CandidateSkill.candidate_id,
        CandidateEducation.candidate_id,
    ]
    for col in cols:
        partial = await _count_map(session, col, member_ids)
        for cid, n in partial.items():
            total[cid] = total.get(cid, 0) + n
    return total


# --- утилиты Core update/delete (без ORM-синхронизации) ----------------------

async def _exec(session: AsyncSession, stmt) -> None:
    await session.execute(stmt, execution_options={"synchronize_session": False})


# --- главная функция мержа ---------------------------------------------------

# Поля-скаляры, которыми у survivor дозаполняем ПУСТОТЫ из проигравших.
_BACKFILL_FIELDS = (
    "middle_name", "birth_date", "gender", "city", "region", "phone", "email",
    "salary_expectation", "salary_from", "salary_to", "last_position", "last_company",
    "last_period", "resume_text", "resume_summary", "ai_score", "source_url",
    "external_source", "external_id", "talantix_person_id", "habr_contacts_opened_at",
)
_NAME_FIELDS = {"middle_name"}  # снимаем «\d+-» при подстановке имени


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


async def merge_component(
    session: AsyncSession,
    company_id: UUID,
    member_ids: list[UUID],
    *,
    now: datetime | None = None,
) -> ComponentResult:
    """Слить компонент дублей в одного survivor. Пишет в session (flush), НЕ коммитит —
    транзакцией/savepoint управляет вызывающий (CLI: savepoint на компонент).

    Идемпотентно: перечитывает ЖИВЫХ членов; если живых <2 — no-op (skipped=True).
    """
    now = now or datetime.now(timezone.utc)

    # Живые члены (уже слитые проигравшие имеют deleted_at → выпадают).
    # populate_existing=True: перечитать ВСЕ поля, даже если инстанс уже в сессии с
    # expired-полями (created_at/extra — server_default). Иначе синхронный доступ к
    # expired-полю в sorted(key=…created_at) ниже → MissingGreenlet (грабля identity-map).
    res = await session.execute(
        select(Candidate).where(
            Candidate.id.in_(member_ids),
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
        ).execution_options(populate_existing=True)
    )
    members = list(res.scalars().all())
    if len(members) < 2:
        return ComponentResult(company_id=company_id, skipped=True)

    live_ids = [m.id for m in members]
    by_id = {m.id: m for m in members}

    # --- 1. SURVIVOR ---------------------------------------------------------
    richness = await _richness_counts(session, live_ids)
    emp_rows = await session.execute(
        select(Employee.candidate_id).where(Employee.candidate_id.in_(live_ids))
    )
    employee_ids = {r[0] for r in emp_rows.all() if r[0] is not None}

    def _survivor_key(m: Candidate):
        return (
            0 if m.id in employee_ids else 1,   # employee первым
            -richness.get(m.id, 0),             # богатейший
            m.created_at,                        # старейший
            str(m.id),                           # стабильный тай-брейк (меньший id)
        )

    survivor = sorted(members, key=_survivor_key)[0]
    S = survivor.id
    losers = [m for m in members if m.id != S]
    loser_ids = [m.id for m in losers]
    # Проигравшие в порядке «богатства» (для выбора источника секций резюме).
    losers_by_rich = sorted(
        losers, key=lambda m: (-richness.get(m.id, 0), m.created_at, str(m.id))
    )

    result = ComponentResult(company_id=company_id, survivor_id=S, merged_ids=loser_ids)
    # hh_seen_nids: объединяем survivor + ВСЕХ проигравших (+ nid коллизий ниже). Иначе
    # «увиденные» nid проигравших потерялись бы и поллер v1.7.22 взял бы эти отклики заново.
    seen_nids: list[str] = list((survivor.extra or {}).get("hh_seen_nids") or [])
    for _m in losers:
        for _n in ((_m.extra or {}).get("hh_seen_nids") or []):
            if _n not in seen_nids:
                seen_nids.append(_n)

    # --- 4a. Заявки: план коллизий ------------------------------------------
    app_res = await session.execute(
        select(
            Application.id,
            Application.candidate_id,
            Application.vacancy_id,
            Application.stage,
            Application.created_at,
            Application.hh_negotiation_id,
        ).where(Application.candidate_id.in_(live_ids))
    )
    app_rows = app_res.all()
    by_vacancy: dict[UUID, list] = {}
    for row in app_rows:
        by_vacancy.setdefault(row.vacancy_id, []).append(row)

    app_remap: dict[UUID, UUID] = {}   # losing_app_id -> winner_app_id
    losing_app_ids: list[UUID] = []
    for vac_id, rows in by_vacancy.items():
        if len(rows) < 2:
            continue  # нет коллизии — заявка просто переедет на survivor (шаг 4c)
        winner = sorted(
            rows, key=lambda r: (_stage_rank(r.stage), r.created_at)
        )[-1]
        losing = [r for r in rows if r.id != winner.id]
        for r in losing:
            app_remap[r.id] = winner.id
            losing_app_ids.append(r.id)
            if r.hh_negotiation_id and r.hh_negotiation_id not in seen_nids:
                seen_nids.append(r.hh_negotiation_id)
        result.collision_details.append({
            "vacancy_id": str(vac_id),
            "winning_stage": winner.stage,
            "losing_stages": [r.stage for r in losing],
        })
    result.app_collisions_resolved = len(result.collision_details)

    # --- 4b. ДЕТЕЙ проигравших заявок → winner-app (ДО удаления заявок, иначе
    #         CASCADE их сотрёт). ai_evaluations — отдельно (уник + dedup). -----
    # winner-заявки, у которых УЖЕ есть Employee: второй на них не переносим (уник
    # uq_employees_application_id оборвал бы компонент). loser-Employee останется на
    # своей заявке → при её DELETE ниже FK SET NULL обнулит application_id (сам Employee
    # уцелеет, candidate_id уедет на survivor в общем reparent). Случай «нанят дважды».
    winner_has_emp: set = set()
    if app_remap:
        _emp_rows = await session.execute(
            select(Employee.application_id).where(Employee.application_id.in_(set(app_remap.values())))
        )
        winner_has_emp = {r[0] for r in _emp_rows.all() if r[0] is not None}
    for losing_id, winner_id in app_remap.items():
        for model in (StageHistory, Comment, Message, TestAssignment, TestAttempt, TestResult, InterviewLink):
            await _exec(
                session,
                update(model).where(model.application_id == losing_id).values(application_id=winner_id),
            )
        # employees.application_id → winner ТОЛЬКО если у winner ещё нет Employee.
        if winner_id not in winner_has_emp:
            res_emp = await session.execute(
                update(Employee).where(Employee.application_id == losing_id).values(application_id=winner_id),
                execution_options={"synchronize_session": False},
            )
            if (res_emp.rowcount or 0) > 0:
                winner_has_emp.add(winner_id)  # занят — следующий loser сюда не перенесём

    # ai_evaluations: candidate_id=S + application_id (remap) + dedup (candidate_id, application_id).
    # Делаем ДО удаления заявок (FK на applications = CASCADE).
    ev_res = await session.execute(
        select(AiEvaluation.id, AiEvaluation.application_id, AiEvaluation.created_at)
        .where(AiEvaluation.candidate_id.in_(live_ids))
    )
    ev_rows = ev_res.all()
    # Winner-оригиналы (не в remap) обрабатываем ПЕРВЫМИ — их и оставляем при коллизии.
    ev_sorted = sorted(
        ev_rows, key=lambda r: (1 if r.application_id in app_remap else 0, r.created_at)
    )
    ev_seen: set[UUID] = set()
    ev_delete: list[UUID] = []
    ev_update: dict[UUID | None, list[UUID]] = {}
    for eid, app_id, _ in ev_sorted:
        new_app = app_remap.get(app_id, app_id)
        if new_app is not None:
            if new_app in ev_seen:
                ev_delete.append(eid)
                continue
            ev_seen.add(new_app)
        ev_update.setdefault(new_app, []).append(eid)
    if ev_delete:
        await _exec(session, delete(AiEvaluation).where(AiEvaluation.id.in_(ev_delete)))
    for new_app, ids in ev_update.items():
        await _exec(
            session,
            update(AiEvaluation).where(AiEvaluation.id.in_(ids)).values(candidate_id=S, application_id=new_app),
        )

    # --- 4c. Удаляем проигравшие заявки, остальные переносим на survivor -----
    _losing_set = set(losing_app_ids)
    result.apps_reparented = sum(
        1 for r in app_rows if r.id not in _losing_set and r.candidate_id != S
    )
    if losing_app_ids:
        await _exec(session, delete(Application).where(Application.id.in_(losing_app_ids)))
    await _exec(
        session,
        update(Application).where(Application.candidate_id.in_(loser_ids)).values(candidate_id=S),
    )

    # --- Секции резюме -------------------------------------------------------
    for model in (CandidateExperience, CandidateSkill, CandidateEducation):
        counts = await _count_map(session, model.candidate_id, live_ids)
        survivor_has = counts.get(S, 0) > 0
        if survivor_has:
            await _exec(session, delete(model).where(model.candidate_id.in_(loser_ids)))
            continue
        # у survivor нет секций этого типа → берём у богатейшего проигравшего с записями
        source_loser = next((m.id for m in losers_by_rich if counts.get(m.id, 0) > 0), None)
        if source_loser is None:
            continue
        await _exec(session, update(model).where(model.candidate_id == source_loser).values(candidate_id=S))
        drop = [lid for lid in loser_ids if lid != source_loser]
        if drop:
            await _exec(session, delete(model).where(model.candidate_id.in_(drop)))

    # --- candidate_tags: reparent новых, dup — удалить ------------------------
    tag_res = await session.execute(
        select(CandidateTag.id, CandidateTag.tag_id, CandidateTag.candidate_id)
        .where(CandidateTag.candidate_id.in_(live_ids))
    )
    tag_rows = tag_res.all()
    seen_tags = {r.tag_id for r in tag_rows if r.candidate_id == S}
    tag_reparent: list[UUID] = []
    tag_delete: list[UUID] = []
    for r in tag_rows:
        if r.candidate_id == S:
            continue
        if r.tag_id in seen_tags:
            tag_delete.append(r.id)
        else:
            seen_tags.add(r.tag_id)
            tag_reparent.append(r.id)
    if tag_delete:
        await _exec(session, delete(CandidateTag).where(CandidateTag.id.in_(tag_delete)))
    if tag_reparent:
        await _exec(session, update(CandidateTag).where(CandidateTag.id.in_(tag_reparent)).values(candidate_id=S))

    # --- candidate_embeddings: survivor оставляем; если у него НЕТ вектора, а у
    #     проигравшего есть — переносим ОДИН (богатейшего), чтобы survivor не выпал из
    #     семантического поиска (уник candidate_id → только один). Остальных удаляем.
    emb_res = await session.execute(
        select(CandidateEmbedding.candidate_id).where(CandidateEmbedding.candidate_id.in_(live_ids))
    )
    emb_owners = {r[0] for r in emb_res.all()}
    adopt_emb = None if S in emb_owners else next((m.id for m in losers_by_rich if m.id in emb_owners), None)
    if adopt_emb is not None:
        await _exec(session, update(CandidateEmbedding).where(CandidateEmbedding.candidate_id == adopt_emb).values(candidate_id=S))
    drop_emb = [lid for lid in loser_ids if lid != adopt_emb]
    if drop_emb:
        await _exec(session, delete(CandidateEmbedding).where(CandidateEmbedding.candidate_id.in_(drop_emb)))

    # --- message_reads: одна строка на user_id, last_read_at = max -----------
    mr_res = await session.execute(
        select(MessageRead.id, MessageRead.user_id, MessageRead.candidate_id, MessageRead.last_read_at)
        .where(MessageRead.candidate_id.in_(live_ids))
    )
    mr_rows = mr_res.all()
    mr_by_user: dict[UUID, list] = {}
    for r in mr_rows:
        mr_by_user.setdefault(r.user_id, []).append(r)
    for uid, rs in mr_by_user.items():
        surv_rows = [r for r in rs if r.candidate_id == S]
        kept = surv_rows[0] if surv_rows else rs[0]
        max_time = max(r.last_read_at for r in rs)
        drop = [r.id for r in rs if r.id != kept.id]
        if drop:
            await _exec(session, delete(MessageRead).where(MessageRead.id.in_(drop)))
        if kept.candidate_id != S:
            await _exec(
                session,
                update(MessageRead).where(MessageRead.id == kept.id).values(candidate_id=S, last_read_at=max_time),
            )
        elif max_time > kept.last_read_at:
            await _exec(session, update(MessageRead).where(MessageRead.id == kept.id).values(last_read_at=max_time))

    # --- comments: candidate_id → S. talantix-заметки уникальны по
    #     (company, candidate, external_id) → дедуп; остальные (hh/manual) — прямой reparent.
    await _exec(
        session,
        update(Comment).where(Comment.candidate_id.in_(loser_ids), Comment.source != "talantix").values(candidate_id=S),
    )
    tc_res = await session.execute(
        select(Comment.id, Comment.external_id, Comment.candidate_id)
        .where(Comment.candidate_id.in_(live_ids), Comment.source == "talantix")
    )
    tc_rows = tc_res.all()
    seen_ext = {r.external_id for r in tc_rows if r.candidate_id == S and r.external_id}
    tc_reparent: list[UUID] = []
    tc_delete: list[UUID] = []
    for r in tc_rows:
        if r.candidate_id == S:
            continue
        if r.external_id and r.external_id in seen_ext:
            tc_delete.append(r.id)
        else:
            if r.external_id:
                seen_ext.add(r.external_id)
            tc_reparent.append(r.id)
    if tc_delete:
        await _exec(session, delete(Comment).where(Comment.id.in_(tc_delete)))
    if tc_reparent:
        await _exec(session, update(Comment).where(Comment.id.in_(tc_reparent)).values(candidate_id=S))

    # --- прочие дети без уник-коллизий: candidate_id → S ---------------------
    for model in (Document, Message, Verification, Consent, Event, TestAssignment, Employee):
        await _exec(session, update(model).where(model.candidate_id.in_(loser_ids)).values(candidate_id=S))

    # --- Скаляры survivor: снять «\d+-» с фамилии, дозаполнить пустоты --------
    stripped_last = _strip_num_prefix(survivor.last_name)
    if stripped_last and stripped_last != survivor.last_name:
        survivor.last_name = stripped_last

    for fld in _BACKFILL_FIELDS:
        if not _is_empty(getattr(survivor, fld)):
            continue
        for m in losers_by_rich:
            val = getattr(m, fld)
            if fld in _NAME_FIELDS:
                val = _strip_num_prefix(val)
            if not _is_empty(val):
                setattr(survivor, fld, val)
                break
    # messengers: если у survivor пусто — берём непустой список проигравшего.
    if not (survivor.messengers or []):
        for m in losers_by_rich:
            if m.messengers:
                survivor.messengers = list(m.messengers)
                break

    # extra: докладываем ключи, которых у survivor нет (не перетирая), + hh_seen_nids.
    merged_extra = dict(survivor.extra or {})
    for m in losers_by_rich:
        for k, v in (m.extra or {}).items():
            if k not in merged_extra:
                merged_extra[k] = v
    if seen_nids:
        merged_extra["hh_seen_nids"] = seen_nids
    survivor.extra = merged_extra  # переприсваиваем dict — dirty-tracking JSONB

    # --- Проигравшие: soft-delete + пометки ----------------------------------
    for m in losers:
        m.deleted_at = now
        m.duplicate_of = S
        m.is_duplicate = True
        m.extra = {**(m.extra or {}), "merged_into": str(S)}

    # --- Audit (§2.2): одно системное действие на компонент ------------------
    await audit(
        session,
        action="candidates_merged",
        entity_type="candidate",
        entity_id=S,
        after={
            "survivor_id": str(S),
            "merged_ids": [str(x) for x in loser_ids],
            "apps_reparented": result.apps_reparented,
            "app_collisions_resolved": result.app_collisions_resolved,
            "review_skipped": 0,
        },
        actor_type="system",
        actor_user_id=None,
        company_id=company_id,
    )

    await session.flush()
    return result


# --- отчёт по компании (для CLI) --------------------------------------------

@dataclass
class CompanyReport:
    company_id: UUID
    total_candidates: int = 0
    components_total: int = 0            # сильных компонентов найдено
    components_processed: int = 0        # обработано (с учётом --limit)
    merged_components: int = 0           # реально слитых (не skipped/не error)
    trashed: int = 0                     # кандидатов в утиль
    apps_reparented: int = 0
    app_collisions_resolved: int = 0
    collision_details: list[dict] = field(default_factory=list)
    errors: int = 0
    review: list[ReviewItem] = field(default_factory=list)
    results: list[ComponentResult] = field(default_factory=list)
