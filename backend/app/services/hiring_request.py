"""Сервис модуля «Заявки на подбор».

Инварианты:
- company_id в КАЖДОМ запросе (мультитенантность §2.3).
- Роль hiring_manager видит ТОЛЬКО свои заявки (author_user_id==он) — форсим на списке,
  проверяем на детали/мутациях (образец pulse.py). Мутации этапов/отклонение/создание
  вакансии hiring_manager запрещены.
- Каждое изменяющее действие → audit_log (§2.2) + человекочитаемое Event type='request'
  (история заявки; в общей ленте Главной такие события скрыты).
- Прогресс найма считается РЕАЛЬНО из воронки связанной вакансии (кандидаты на 'hired'),
  автозакрытие — единой точкой в move_application (см. services/application.py).
"""
import html as _html
import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..core.errors import ForbiddenError, NotFoundError, ValidationError, ConflictError
from ..core.request_stages import (
    REQUEST_FIXED_STAGES,
    PROTECTED_REQUEST_STAGE_KEYS,
    TERMINAL_REQUEST_STAGE_KEYS,
    build_stage_flow,
    valid_stage_keys,
)
from ..models import (
    HiringRequest, RequestComment, RequestFunnelStage, RequestSettings,
    Event, Application, Vacancy, User,
)
from .audit import audit

logger = logging.getLogger(__name__)

_FIXED_LABELS = {s.key: s.label for s in REQUEST_FIXED_STAGES}


# ── Роль/доступ ───────────────────────────────────────────────────────────────
# «Персонал рекрутинга» — видит и ведёт ВСЕ заявки компании. Остальные роли
# (hiring_manager И manager-ассистент) — только СВОИ заявки, без управления этапами.
# Обобщение закрывает least-privilege gap: до этого manager видел все заявки компании.
def _is_staff(user: User) -> bool:
    return user.role in ("admin", "recruiter")


def _is_hiring_manager(user: User) -> bool:
    return user.role == "hiring_manager"


def assert_request_access(request: HiringRequest, user: User) -> None:
    """Не-персонал может касаться ТОЛЬКО своей заявки; иначе — как будто её нет (404)."""
    if not _is_staff(user) and request.author_user_id != user.id:
        raise NotFoundError("Заявка")


def assert_can_manage(user: User) -> None:
    """Переводы/отклонение/закрытие/создание вакансии — только recruiter/admin."""
    if not _is_staff(user):
        raise ForbiddenError("Недостаточно прав для управления заявкой")


# ── Настройки / стадии ────────────────────────────────────────────────────────
async def get_or_create_settings(session: AsyncSession, company_id: UUID) -> RequestSettings:
    row = (await session.execute(
        select(RequestSettings).where(RequestSettings.company_id == company_id)
    )).scalar_one_or_none()
    if row is None:
        row = RequestSettings(company_id=company_id)
        session.add(row)
        await session.flush()
    return row


async def _custom_stage_dicts(session: AsyncSession, company_id: UUID) -> list[dict]:
    rows = (await session.execute(
        select(RequestFunnelStage)
        .where(RequestFunnelStage.company_id == company_id)
        .order_by(RequestFunnelStage.order_index)
    )).scalars().all()
    return [
        {"stage_key": r.stage_key, "label": r.label,
         "order_index": r.order_index, "description": r.description}
        for r in rows
    ]


async def get_stage_flow(session: AsyncSession, company_id: UUID) -> list[dict]:
    return build_stage_flow(await _custom_stage_dicts(session, company_id))


async def _valid_status_keys(session: AsyncSession, company_id: UUID) -> set[str]:
    return valid_stage_keys(await _custom_stage_dicts(session, company_id))


def _stage_label(flow: list[dict], key: str) -> str:
    for s in flow:
        if s["key"] == key:
            return s["label"]
    return key


# ── История / события ────────────────────────────────────────────────────────
async def _write_event(
    session: AsyncSession, *, company_id: UUID, request_id: UUID, text: str,
    actor_type: str, actor_user_id: UUID | None, vacancy_id: UUID | None = None,
) -> None:
    session.add(Event(
        company_id=company_id, type="request", actor_type=actor_type,
        actor_user_id=actor_user_id, text=text, request_id=request_id, vacancy_id=vacancy_id,
    ))


async def get_history(session: AsyncSession, company_id: UUID, request_id: UUID) -> list[dict]:
    rows = (await session.execute(
        select(Event)
        .where(Event.company_id == company_id, Event.request_id == request_id)
        .order_by(Event.created_at.asc(), Event.id.asc())
    )).scalars().all()
    return [{"label": e.text, "at": e.created_at} for e in rows]


# ── Прогресс найма (РЕАЛЬНО из воронки вакансии) ─────────────────────────────
async def compute_hired(session: AsyncSession, company_id: UUID, vacancy_id: UUID) -> int:
    return (await session.execute(
        select(func.count(Application.id)).where(
            Application.company_id == company_id,
            Application.vacancy_id == vacancy_id,
            Application.stage == "hired",
        )
    )).scalar_one()


async def _progress(session: AsyncSession, company_id: UUID, req: HiringRequest) -> dict | None:
    if not req.vacancy_id:
        return None
    vac = (await session.execute(
        select(Vacancy).where(Vacancy.id == req.vacancy_id, Vacancy.company_id == company_id)
    )).scalar_one_or_none()
    if vac is None:
        return None
    counts = (await session.execute(
        select(
            func.count(Application.id).label("total"),
            func.count(case((Application.stage.in_(["response", "added"]), 1), else_=None)).label("new_c"),
            func.count(case((Application.stage == "hired", 1), else_=None)).label("hired"),
        ).where(
            Application.company_id == company_id,
            Application.vacancy_id == vac.id,
            Application.stage != "rejected",
        )
    )).one()
    return {
        "vacancy_id": vac.id, "vacancy_name": vac.name,
        "candidates": counts.total, "new_count": counts.new_c,
        "hired": counts.hired, "positions": vac.positions_count,
    }


# ── Номер заявки (per-company, защита от гонки через unique) ──────────────────
async def _next_num(session: AsyncSession, company_id: UUID) -> int:
    cur = (await session.execute(
        select(func.coalesce(func.max(HiringRequest.num), 0)).where(
            HiringRequest.company_id == company_id
        )
    )).scalar_one()
    return int(cur) + 1


# ── Уведомление менеджеру (ЧЕСТНО: email, если автор — юзер Глафиры) ──────────
async def _notify_manager_stage_change(
    session: AsyncSession, company_id: UUID, req: HiringRequest, stage_label: str
) -> None:
    """Best-effort письмо автору-пользователю о смене этапа. Сбой НЕ блокирует переход.

    Единственный реальный канал адресного уведомления пользователя — email (нет таблицы
    notifications, нет TG-бота для сотрудников). Внешним авторам (via=form, без юзера)
    авто-уведомления НЕ шлём — у них только текстовый контакт для рекрутера.
    """
    st = await get_or_create_settings(session, company_id)
    if not st.notify_manager_on_stage or not req.author_user_id:
        return
    author = (await session.execute(
        select(User).where(User.id == req.author_user_id, User.company_id == company_id)
    )).scalar_one_or_none()
    if not author or not author.email:
        return
    try:
        from .integrations.smtp.templates import render_simple_email
        from .integrations.smtp.service import send_email
        heading = f"Заявка №{req.num}: этап «{stage_label}»"
        body_html = render_simple_email(
            heading,
            f'<p style="margin:0 0 12px;">Статус вашей заявки «{_html.escape(req.title)}» '
            f'изменён на «{_html.escape(stage_label)}».</p>'
            f'<p style="margin:0;">Подробности и переписку с рекрутером — в разделе «Мои заявки».</p>',
            preheader=f"Заявка №{req.num} — {stage_label}",
        )
        await send_email(
            session, company_id, to=author.email,
            subject=heading, body_text=f"Заявка №{req.num}: этап «{stage_label}».",
            body_html=body_html,
        )
    except Exception as exc:  # noqa: BLE001 — уведомление best-effort
        logger.info("[requests] уведомление менеджеру не отправлено: %s", exc)


# ── CRUD заявок ───────────────────────────────────────────────────────────────
def _to_list_item(req: HiringRequest, progress: dict | None) -> dict:
    return {
        "id": req.id, "num": req.num, "title": req.title, "department": req.department,
        "city": req.city, "positions": req.positions, "deadline": req.deadline,
        "priority": req.priority, "status": req.status, "via": req.via,
        "author_name": req.author_name, "author_role": req.author_role,
        "created_at": req.created_at, "progress": progress,
    }


async def create_request(
    session: AsyncSession, *, company_id: UUID, user: User | None, data,
    via: str, author_name: str | None = None, author_role: str | None = None,
    author_contact: str | None = None,
) -> HiringRequest:
    """Создать заявку. via: cabinet (менеджер-юзер) | form (публичная) | manual (со слов).

    В via=cabinet автор — user; в form/manual — текстовые поля author_*.
    """
    # Защита от гонки номера: до 5 попыток при коллизии unique(company_id,num).
    # Каждая попытка insert — в savepoint, чтобы откат не задел транзакцию вызывающего.
    req = None
    for _attempt in range(5):
        num = await _next_num(session, company_id)
        req = HiringRequest(
            company_id=company_id, num=num,
            title=data.title.strip(), description=data.description.strip(),
            department=(data.department or None), city=(data.city or None),
            positions=data.positions, deadline=data.deadline,
            salary_from=data.salary_from, salary_to=data.salary_to,
            employment_format=data.employment_format, priority=data.priority,
            status="new", via=via,
            author_user_id=(user.id if (via == "cabinet" and user) else None),
            author_name=(user.full_name if (via == "cabinet" and user) else author_name),
            author_role=(user.position if (via == "cabinet" and user) else author_role),
            author_contact=(None if via == "cabinet" else author_contact),
        )
        try:
            async with session.begin_nested():
                session.add(req)
                await session.flush()
            break
        except IntegrityError:
            if _attempt == 4:
                raise
            req = None
            continue

    actor_name = (user.full_name if user else (author_name or "заявитель"))
    who = "по ссылке-форме · " if via == "form" else ("вручную · " if via == "manual" else "· ")
    await _write_event(
        session, company_id=company_id, request_id=req.id,
        text=f"Заявка подана {who}{actor_name}",
        actor_type=("system" if via == "form" else "human"),
        actor_user_id=(user.id if user else None),
    )
    await audit(
        session, action="create", entity_type="request", entity_id=req.id,
        before=None, after={"status": "new", "via": via},
        actor_user_id=(user.id if user else None), company_id=company_id,
        actor_type=("system" if via == "form" else "human"),
    )
    return req


async def list_requests(
    session: AsyncSession, *, company_id: UUID, user: User,
    status: str | None = None, query: str | None = None,
    limit: int = 100, offset: int = 0,
) -> tuple[list[dict], int]:
    conds = [HiringRequest.company_id == company_id]
    # Не-персонал (hiring_manager/manager): ФОРСИМ автора == он (fail-closed, фильтры игнорируются).
    if not _is_staff(user):
        conds.append(HiringRequest.author_user_id == user.id)
    if status and status != "all":
        conds.append(HiringRequest.status == status)
    if query:
        raw = query.strip()
        q = f"%{raw.lower()}%"
        ors = [
            func.lower(HiringRequest.title).like(q),
            func.lower(func.coalesce(HiringRequest.author_name, "")).like(q),
            func.lower(func.coalesce(HiringRequest.author_role, "")).like(q),
        ]
        # Поиск по номеру: «21» или «№21»
        digits = raw.lstrip("№").strip()
        if digits.isdigit():
            ors.append(HiringRequest.num == int(digits))
        conds.append(or_(*ors))
    total = (await session.execute(
        select(func.count(HiringRequest.id)).where(*conds)
    )).scalar_one()
    rows = (await session.execute(
        select(HiringRequest).where(*conds)
        .order_by(HiringRequest.num.desc())
        .limit(limit).offset(offset)
    )).scalars().all()
    items = []
    for r in rows:
        prog = await _progress(session, company_id, r) if r.status == "sourcing" else None
        items.append(_to_list_item(r, prog))
    return items, total


async def get_request_or_raise(
    session: AsyncSession, company_id: UUID, request_id: UUID
) -> HiringRequest:
    req = (await session.execute(
        select(HiringRequest)
        .where(HiringRequest.id == request_id, HiringRequest.company_id == company_id)
        .options(selectinload(HiringRequest.comments))
    )).scalar_one_or_none()
    if req is None:
        raise NotFoundError("Заявка")
    return req


async def build_detail(session: AsyncSession, company_id: UUID, req: HiringRequest) -> dict:
    prog = await _progress(session, company_id, req)
    vacancy_name = prog["vacancy_name"] if prog else None
    comments = sorted(req.comments, key=lambda c: c.created_at)
    d = _to_list_item(req, prog)
    d.update({
        "description": req.description, "salary_from": req.salary_from,
        "salary_to": req.salary_to, "employment_format": req.employment_format,
        "author_contact": req.author_contact, "author_user_id": req.author_user_id,
        "vacancy_id": req.vacancy_id, "vacancy_name": vacancy_name,
        "reject_reason": req.reject_reason, "closed_note": req.closed_note,
        "comments": [
            {"id": c.id, "side": c.side, "author_name": c.author_name,
             "author_user_id": c.author_user_id, "body": c.body, "created_at": c.created_at}
            for c in comments
        ],
        "history": await get_history(session, company_id, req.id),
    })
    return d


# ── Переходы ──────────────────────────────────────────────────────────────────
async def move_request(
    session: AsyncSession, *, company_id: UUID, user: User, req: HiringRequest, target: str
) -> HiringRequest:
    assert_can_manage(user)
    if target == req.status:
        return req
    valid = await _valid_status_keys(session, company_id)
    if target not in valid:
        raise ValidationError("Неизвестный этап заявки")
    # Терминалы — только через свои пути (reject требует причину, close — итог). Общий move
    # НЕ должен ставить 'rejected'/'done' в обход (иначе отказ без причины/rejected_at).
    if target == "rejected":
        raise ValidationError("Отклонение — кнопкой «Отклонить» с указанием причины")
    if target == "done":
        raise ValidationError("Закрытие — кнопкой «Закрыть» с итогом")
    # Перевод в «В подборе» без вакансии = запуск создания вакансии (делает фронт-мастер).
    if target == "sourcing" and not req.vacancy_id:
        raise ConflictError(
            "Для этапа «В подборе» создайте вакансию из заявки.",
            code="VACANCY_REQUIRED",
        )
    flow = await get_stage_flow(session, company_id)
    label = _stage_label(flow, target)
    before = req.status
    req.status = target
    # Реактивация из терминала (напр. done→work кастомным этапом) — чистим устаревшие
    # терминальные поля, чтобы деталь не показывала «Закрыта»/причину при рабочем статусе.
    if before in TERMINAL_REQUEST_STAGE_KEYS:
        req.closed_note = None
        req.closed_at = None
        req.reject_reason = None
        req.rejected_at = None
    await _write_event(
        session, company_id=company_id, request_id=req.id,
        text=f"Переведена на этап «{label}» · {user.full_name}",
        actor_type="human", actor_user_id=user.id, vacancy_id=req.vacancy_id,
    )
    await audit(
        session, action="move", entity_type="request", entity_id=req.id,
        before={"status": before}, after={"status": target},
        actor_user_id=user.id, company_id=company_id,
    )
    await _notify_manager_stage_change(session, company_id, req, label)
    return req


async def reject_request(
    session: AsyncSession, *, company_id: UUID, user: User, req: HiringRequest, reason: str
) -> HiringRequest:
    assert_can_manage(user)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Укажите причину отклонения — её увидит менеджер")
    before = req.status
    req.status = "rejected"
    req.reject_reason = reason
    req.rejected_at = datetime.now(timezone.utc)
    await _write_event(
        session, company_id=company_id, request_id=req.id,
        text=f"Отклонена · {user.full_name}", actor_type="human", actor_user_id=user.id,
    )
    await audit(
        session, action="reject", entity_type="request", entity_id=req.id,
        before={"status": before}, after={"status": "rejected", "reason": reason},
        actor_user_id=user.id, company_id=company_id,
    )
    await _notify_manager_stage_change(session, company_id, req, "Отклонена")
    return req


async def restore_request(
    session: AsyncSession, *, company_id: UUID, user: User, req: HiringRequest
) -> HiringRequest:
    assert_can_manage(user)
    if req.status != "rejected":
        raise ValidationError("Вернуть в работу можно только отклонённую заявку")
    req.status = "work"
    req.reject_reason = None
    req.rejected_at = None
    await _write_event(
        session, company_id=company_id, request_id=req.id,
        text=f"Возвращена в работу · {user.full_name}", actor_type="human", actor_user_id=user.id,
    )
    await audit(
        session, action="restore", entity_type="request", entity_id=req.id,
        before={"status": "rejected"}, after={"status": "work"},
        actor_user_id=user.id, company_id=company_id,
    )
    return req


async def close_request(
    session: AsyncSession, *, company_id: UUID, user: User, req: HiringRequest, note: str | None
) -> HiringRequest:
    assert_can_manage(user)
    before = req.status
    req.status = "done"
    req.closed_note = (note or "").strip() or "Закрыта вручную"
    req.closed_at = datetime.now(timezone.utc)
    await _write_event(
        session, company_id=company_id, request_id=req.id,
        text=f"Закрыта · {user.full_name}", actor_type="human", actor_user_id=user.id,
        vacancy_id=req.vacancy_id,
    )
    await audit(
        session, action="close", entity_type="request", entity_id=req.id,
        before={"status": before}, after={"status": "done"},
        actor_user_id=user.id, company_id=company_id,
    )
    await _notify_manager_stage_change(session, company_id, req, "Закрыта")
    return req


# ── Тред уточнений ────────────────────────────────────────────────────────────
async def add_comment(
    session: AsyncSession, *, company_id: UUID, user: User, req: HiringRequest, body: str
) -> RequestComment:
    body = (body or "").strip()
    if not body:
        raise ValidationError("Пустое сообщение")
    side = "recruiter" if _is_staff(user) else "manager"
    comment = RequestComment(
        company_id=company_id, request_id=req.id, side=side,
        author_user_id=user.id, author_name=user.full_name, body=body,
    )
    session.add(comment)
    # Правило: вопрос из «Новой» переводит заявку в «В работе» (если правило включено).
    st = await get_or_create_settings(session, company_id)
    if req.status == "new" and st.question_moves_to_work:
        req.status = "work"
        await _write_event(
            session, company_id=company_id, request_id=req.id,
            text=f"Взята в работу (задан вопрос) · {user.full_name}",
            actor_type="human", actor_user_id=user.id,
        )
        await audit(
            session, action="move", entity_type="request", entity_id=req.id,
            before={"status": "new"}, after={"status": "work"},
            actor_user_id=user.id, company_id=company_id,
        )
    await session.flush()
    return comment


# ── Создание вакансии из заявки (связь 1:1) ─────────────────────────────────
async def link_vacancy_to_request(
    session: AsyncSession, *, company_id: UUID, vacancy: Vacancy,
    request_id: UUID, actor_user_id: UUID | None, actor_type: str = "human",
) -> None:
    """Привязать созданную вакансию к заявке + перевести заявку в «В подборе».

    Вызывается из create_vacancy при переданном request_id. Валидирует принадлежность
    компании и отсутствие уже привязанной вакансии (связь строго 1:1).
    """
    req = (await session.execute(
        select(HiringRequest).where(
            HiringRequest.id == request_id, HiringRequest.company_id == company_id
        )
    )).scalar_one_or_none()
    if req is None:
        raise NotFoundError("Заявка")
    if req.vacancy_id is not None:
        raise ConflictError("К заявке уже привязана вакансия", code="REQUEST_HAS_VACANCY")
    req.vacancy_id = vacancy.id
    vacancy.request_id = req.id
    if req.status not in TERMINAL_REQUEST_STAGE_KEYS:
        req.status = "sourcing"
    await session.flush()
    await _write_event(
        session, company_id=company_id, request_id=req.id,
        text=f"Создана вакансия «{vacancy.name}»",
        actor_type=actor_type, actor_user_id=actor_user_id, vacancy_id=vacancy.id,
    )
    await audit(
        session, action="vacancy_created", entity_type="request", entity_id=req.id,
        before={"status": "work"}, after={"status": "sourcing", "vacancy_id": str(vacancy.id)},
        actor_user_id=actor_user_id, company_id=company_id, actor_type=actor_type,
    )


# ── Автозакрытие при найме всех позиций (вызывается из move_application) ──────
async def maybe_autoclose_request_for_vacancy(
    session: AsyncSession, *, company_id: UUID, vacancy: Vacancy,
    actor_user_id: UUID | None, actor_type: str,
) -> None:
    """Если вакансия создана из заявки и нанято >= positions_count → закрыть заявку.

    Единственная точка автозакрытия — покрывает ВСЕ пути найма (ручной/bulk/AI), т.к. все
    идут через move_application. Идемпотентно: заявка уже 'done' → выход без действий.
    """
    if not vacancy.request_id:
        return
    st = await get_or_create_settings(session, company_id)
    if not st.autoclose_on:
        return
    req = (await session.execute(
        select(HiringRequest).where(
            HiringRequest.id == vacancy.request_id, HiringRequest.company_id == company_id
        )
    )).scalar_one_or_none()
    if req is None or req.status in TERMINAL_REQUEST_STAGE_KEYS:
        return
    hired = await compute_hired(session, company_id, vacancy.id)
    if hired < vacancy.positions_count:
        return
    before = req.status
    req.status = "done"
    req.closed_note = f"Нанято {hired} из {vacancy.positions_count} — заявка закрыта автоматически"
    req.closed_at = datetime.now(timezone.utc)
    await _write_event(
        session, company_id=company_id, request_id=req.id,
        text=f"Нанято {hired} из {vacancy.positions_count} — заявка закрыта автоматически",
        actor_type=(actor_type or "system"), actor_user_id=actor_user_id, vacancy_id=vacancy.id,
    )
    await audit(
        session, action="close", entity_type="request", entity_id=req.id,
        before={"status": before}, after={"status": "done", "auto": True},
        actor_user_id=actor_user_id, company_id=company_id, actor_type=(actor_type or "system"),
    )
    await _notify_manager_stage_change(session, company_id, req, "Закрыта")


# ── Сайдбар-счётчики ──────────────────────────────────────────────────────────
async def sidebar_counts(session: AsyncSession, company_id: UUID, user: User) -> dict:
    conds = [HiringRequest.company_id == company_id]
    if not _is_staff(user):
        conds.append(HiringRequest.author_user_id == user.id)
    active = (await session.execute(
        select(func.count(HiringRequest.id)).where(
            *conds, HiringRequest.status.notin_(list(TERMINAL_REQUEST_STAGE_KEYS))
        )
    )).scalar_one()
    new = (await session.execute(
        select(func.count(HiringRequest.id)).where(*conds, HiringRequest.status == "new")
    )).scalar_one()
    return {"active": active, "new": new}


# ── Воронка заявок: CRUD кастомных этапов (admin) ────────────────────────────
def _slugify(label: str, existing: set[str]) -> str:
    base = "custom_" + "".join(ch if ch.isalnum() else "_" for ch in label.lower())[:24].strip("_")
    key = base or "custom_stage"
    i = 1
    while key in existing or key in PROTECTED_REQUEST_STAGE_KEYS:
        key = f"{base}_{i}"
        i += 1
    return key


async def add_stage(session: AsyncSession, company_id: UUID, label: str, description: str | None) -> RequestFunnelStage:
    label = (label or "").strip()
    if not label:
        raise ValidationError("Название этапа обязательно")
    existing = {cs["stage_key"] for cs in await _custom_stage_dicts(session, company_id)}
    key = _slugify(label, existing)
    max_order = (await session.execute(
        select(func.coalesce(func.max(RequestFunnelStage.order_index), 0)).where(
            RequestFunnelStage.company_id == company_id
        )
    )).scalar_one()
    stage = RequestFunnelStage(
        company_id=company_id, stage_key=key, label=label,
        order_index=int(max_order) + 1, description=(description or None),
    )
    session.add(stage)
    await session.flush()
    return stage


async def update_stage(session: AsyncSession, company_id: UUID, stage_key: str, label, description) -> RequestFunnelStage:
    if stage_key in PROTECTED_REQUEST_STAGE_KEYS:
        raise ValidationError("Фиксированный этап нельзя изменить")
    stage = (await session.execute(
        select(RequestFunnelStage).where(
            RequestFunnelStage.company_id == company_id,
            RequestFunnelStage.stage_key == stage_key,
        )
    )).scalar_one_or_none()
    if stage is None:
        raise NotFoundError("Этап")
    if label is not None:
        stage.label = label.strip()
    if description is not None:
        stage.description = description or None
    await session.flush()
    return stage


async def delete_stage(session: AsyncSession, company_id: UUID, stage_key: str) -> None:
    if stage_key in PROTECTED_REQUEST_STAGE_KEYS:
        raise ValidationError("Фиксированный этап нельзя удалить")
    stage = (await session.execute(
        select(RequestFunnelStage).where(
            RequestFunnelStage.company_id == company_id,
            RequestFunnelStage.stage_key == stage_key,
        )
    )).scalar_one_or_none()
    if stage is None:
        raise NotFoundError("Этап")
    # Заявки на этом кастомном этапе откатываем на «В работе» (не осиротить статус).
    reqs = (await session.execute(
        select(HiringRequest).where(
            HiringRequest.company_id == company_id, HiringRequest.status == stage_key
        )
    )).scalars().all()
    for r in reqs:
        r.status = "work"
    await session.delete(stage)
    await session.flush()


async def reorder_stages(session: AsyncSession, company_id: UUID, stage_keys: list[str]) -> None:
    rows = (await session.execute(
        select(RequestFunnelStage).where(RequestFunnelStage.company_id == company_id)
    )).scalars().all()
    by_key = {r.stage_key: r for r in rows}
    order = 1
    for key in stage_keys:
        if key in by_key:
            by_key[key].order_index = order
            order += 1
    await session.flush()


# ── Публичная форма: токен/ротация ────────────────────────────────────────────
async def ensure_form_token(session: AsyncSession, company_id: UUID) -> tuple[str, bool]:
    """Гарантирует наличие СВОЕГО токена формы у компании (создаёт при первом обращении,
    НЕ включая приём). Каждый инстанс Глафиры получает свою уникальную ссылку /apply/<token>."""
    st = await get_or_create_settings(session, company_id)
    if not st.form_token:
        st.form_token = secrets.token_urlsafe(32)
        await session.flush()
    return st.form_token, st.form_enabled


async def rotate_form_token(session: AsyncSession, company_id: UUID) -> tuple[str, bool]:
    """Перегенерировать токен (старая ссылка мгновенно мертва). Приём заявок НЕ трогаем —
    им управляет отдельный тумблер form_enabled (иначе «Обновить» молча включал бы форму,
    а UI показывал бы «выключено» — §0 молчаливая активация)."""
    st = await get_or_create_settings(session, company_id)
    st.form_token = secrets.token_urlsafe(32)
    await session.flush()
    return st.form_token, st.form_enabled


def form_url(token: str | None) -> str | None:
    if not token:
        return None
    return f"{settings.FRONTEND_BASE_URL}/apply/{token}"
