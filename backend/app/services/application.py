import math
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import and_, asc, desc, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.errors import NotFoundError, ValidationError
from ..core.stages import STAGES
from ..models import Application, Candidate, Consent, Event, StageHistory, User
from ..schemas.application import (
    ApplicationRow,
    BulkMoveRequest,
    BulkRejectRequest,
    MoveRequest,
    RejectRequest,
    StageHistoryItem,
)
from ..schemas.base import Paginated
from .audit import audit


_STAGE_COLORS = {key: stage.color for key, stage in STAGES.items()}


def _compute_age(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


async def get_applications_for_vacancy_paginated(
    session: AsyncSession,
    vacancy_id: UUID,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24,
    stage: str | None = None,
    search: str | None = None,
    score_min: int | None = None,
    salary_max: int | None = None,
    source: str | None = None,
    city: str | None = None,
    messenger: list[str] | None = None,
    ready_relocate: bool | None = None,
    added_period: str | None = None,
    repeat: bool | None = None,
    sort: str | None = None,
    order: str = "desc",
    candidate_id: UUID | None = None,
) -> Paginated[ApplicationRow]:
    has_pdn_subq = (
        select(Consent.id)
        .where(Consent.candidate_id == Candidate.id, Consent.status == "signed")
        .exists()
    )

    base_filters = [
        Application.vacancy_id == vacancy_id,
        Application.company_id == company_id,
    ]

    if candidate_id:
        base_filters.append(Application.candidate_id == candidate_id)

    if stage and stage != "all":
        base_filters.append(Application.stage == stage)
    if search:
        like = f"%{search}%"
        base_filters.append(
            or_(
                Candidate.last_name.ilike(like),
                Candidate.first_name.ilike(like),
                Candidate.phone.ilike(like),
                Candidate.email.ilike(like),
            )
        )
    if score_min is not None:
        base_filters.append(Application.ai_score >= score_min)
    if salary_max is not None and salary_max > 0:
        base_filters.append(
            or_(
                Candidate.salary_expectation.is_(None),
                Candidate.salary_expectation <= salary_max,
            )
        )
    if source:
        base_filters.append(Candidate.source == source)
    if city:
        base_filters.append(Candidate.city.ilike(f"%{city}%"))
    if messenger:
        base_filters.append(Candidate.preferred_channel.in_(messenger))
    if ready_relocate is not None:
        # JSONB predicate for Postgres: extra->'relocation' casted to boolean
        from sqlalchemy import Boolean
        base_filters.append(
            Candidate.extra['relocation'].astext.cast(Boolean) == ready_relocate
        )
    if added_period and added_period != 'all':
        period_days = {'7d': 7, '30d': 30, '90d': 90}.get(added_period)
        if period_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
            base_filters.append(Application.created_at >= cutoff)
    if repeat is not None:
        base_filters.append(Application.is_repeat == repeat)

    count_stmt = (
        select(func.count(Application.id))
        .select_from(Application)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(and_(*base_filters))
    )
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(
            Application.id,
            Application.candidate_id,
            Application.stage,
            Application.ai_score,
            Application.selected_at,
            Candidate.display_number,
            Candidate.last_name,
            Candidate.first_name,
            Candidate.middle_name,
            Candidate.phone,
            Candidate.salary_expectation,
            Candidate.currency,
            Candidate.city,
            Candidate.last_position,
            Candidate.birth_date,
            Candidate.messengers,
            has_pdn_subq.label("has_pdn"),
        )
        .select_from(Application)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(and_(*base_filters))
    )

    sort_column = Application.created_at
    if sort == "score":
        sort_column = Application.ai_score
    elif sort == "name":
        sort_column = Candidate.last_name
    elif sort == "salary":
        sort_column = Candidate.salary_expectation
    elif sort == "city":
        sort_column = Candidate.city
    elif sort == "date":
        sort_column = Application.created_at

    stmt = stmt.order_by(asc(sort_column) if order == "asc" else desc(sort_column))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = (await session.execute(stmt)).all()

    items = [
        ApplicationRow(
            id=row.id,
            candidate_id=row.candidate_id,
            display_number=row.display_number,
            full_name=" ".join(p for p in (row.last_name, row.first_name, row.middle_name) if p),
            avatar_url=None,
            age=_compute_age(row.birth_date),
            last_position=row.last_position,
            ai_score=row.ai_score,
            has_pdn=bool(row.has_pdn),
            phone=row.phone,
            messengers=row.messengers or [],
            salary_expectation=row.salary_expectation,
            currency=row.currency or "RUB",
            city=row.city,
            stage=row.stage,
            stage_color=_STAGE_COLORS.get(row.stage, "#9AA3AE"),
            selected_at=row.selected_at,
        )
        for row in rows
    ]

    pages = math.ceil(total / page_size) if total > 0 else 0

    return Paginated[ApplicationRow](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


async def get_application(session: AsyncSession, application_id: UUID, company_id: UUID) -> Application:
    result = await session.execute(
        select(Application)
        .options(selectinload(Application.candidate))
        .where(Application.id == application_id, Application.company_id == company_id)
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise NotFoundError("Заявка")
    return application


async def _write_move_event(
    session: AsyncSession,
    *,
    application: Application,
    from_stage: str,
    to_stage: str,
    actor_user_id: UUID,
    company_id: UUID,
    reason: str | None = None,
) -> None:
    text = (
        f"Переведён с этапа «{from_stage}» на «{to_stage}»"
        if reason is None
        else f"Отказ ({to_stage}): {reason}"
    )
    session.add(
        Event(
            company_id=company_id,
            type="move",
            actor_type="human",
            actor_user_id=actor_user_id,
            text=text,
            candidate_id=application.candidate_id,
            vacancy_id=application.vacancy_id,
        )
    )


async def move_application(
    session: AsyncSession,
    application_id: UUID,
    move_data: MoveRequest,
    company_id: UUID,
    actor_user_id: UUID,
) -> Application:
    application = await get_application(session, application_id, company_id)

    from_stage = application.stage
    to_stage = move_data.to_stage

    if from_stage == to_stage:
        raise ValidationError("Заявка уже на этом этапе")

    now = datetime.now(timezone.utc)
    application.stage = to_stage
    application.stage_changed_at = now

    session.add(
        StageHistory(
            application_id=application.id,
            from_stage=from_stage,
            to_stage=to_stage,
            actor_type="human",
            actor_user_id=actor_user_id,
            created_at=now,
        )
    )

    await _write_move_event(
        session,
        application=application,
        from_stage=from_stage,
        to_stage=to_stage,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    if to_stage == "hired":
        from app.services.pulse.employee import create_employee_from_hire
        await create_employee_from_hire(
            session,
            application=application,
            company_id=company_id,
            actor_user_id=actor_user_id,
        )

    await audit(
        session,
        action="move",
        entity_type="application",
        entity_id=application.id,
        before={"stage": from_stage},
        after={"stage": to_stage},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return application


async def reject_application(
    session: AsyncSession,
    application_id: UUID,
    reject_data: RejectRequest,
    company_id: UUID,
    actor_user_id: UUID,
) -> Application:
    application = await get_application(session, application_id, company_id)

    from_stage = application.stage
    if from_stage == "rejected":
        raise ValidationError("Заявка уже отклонена")

    now = datetime.now(timezone.utc)
    application.stage = "rejected"
    application.reject_reason = reject_data.reason
    application.reject_side = reject_data.side
    application.stage_changed_at = now

    session.add(
        StageHistory(
            application_id=application.id,
            from_stage=from_stage,
            to_stage="rejected",
            actor_type="human",
            actor_user_id=actor_user_id,
            reason=reject_data.reason,
            created_at=now,
        )
    )

    await _write_move_event(
        session,
        application=application,
        from_stage=from_stage,
        to_stage="rejected",
        actor_user_id=actor_user_id,
        company_id=company_id,
        reason=reject_data.reason,
    )

    await audit(
        session,
        action="reject",
        entity_type="application",
        entity_id=application.id,
        before={"stage": from_stage},
        after={
            "stage": "rejected",
            "reject_reason": reject_data.reason,
            "reject_side": reject_data.side,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return application


async def restore_application(
    session: AsyncSession,
    application_id: UUID,
    company_id: UUID,
    actor_user_id: UUID,
) -> Application:
    application = await get_application(session, application_id, company_id)

    if application.stage != "rejected":
        raise ValidationError("Можно восстановить только отклонённую заявку")

    previous = (
        await session.execute(
            select(StageHistory.from_stage)
            .where(
                StageHistory.application_id == application_id,
                StageHistory.to_stage == "rejected",
            )
            .order_by(desc(StageHistory.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    restore_to_stage = previous or "response"

    now = datetime.now(timezone.utc)
    application.stage = restore_to_stage
    application.reject_reason = None
    application.reject_side = None
    application.stage_changed_at = now

    session.add(
        StageHistory(
            application_id=application.id,
            from_stage="rejected",
            to_stage=restore_to_stage,
            actor_type="human",
            actor_user_id=actor_user_id,
            reason="Восстановлено",
            created_at=now,
        )
    )

    await _write_move_event(
        session,
        application=application,
        from_stage="rejected",
        to_stage=restore_to_stage,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await audit(
        session,
        action="restore",
        entity_type="application",
        entity_id=application.id,
        before={"stage": "rejected"},
        after={"stage": restore_to_stage},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return application


async def bulk_move_applications(
    session: AsyncSession,
    move_data: BulkMoveRequest,
    company_id: UUID,
    actor_user_id: UUID,
) -> list[Application]:
    return [
        await move_application(
            session,
            app_id,
            MoveRequest(to_stage=move_data.to_stage),
            company_id,
            actor_user_id,
        )
        for app_id in move_data.application_ids
    ]


async def bulk_reject_applications(
    session: AsyncSession,
    reject_data: BulkRejectRequest,
    company_id: UUID,
    actor_user_id: UUID,
) -> list[Application]:
    return [
        await reject_application(
            session,
            app_id,
            RejectRequest(reason=reject_data.reason, side=reject_data.side),
            company_id,
            actor_user_id,
        )
        for app_id in reject_data.application_ids
    ]


async def get_application_history(
    session: AsyncSession,
    application_id: UUID,
    company_id: UUID,
) -> list[StageHistoryItem]:
    await get_application(session, application_id, company_id)

    stmt = (
        select(
            StageHistory.from_stage,
            StageHistory.to_stage,
            StageHistory.actor_type,
            StageHistory.reason,
            StageHistory.created_at,
            User.full_name.label("actor_name"),
        )
        .select_from(StageHistory)
        .outerjoin(User, StageHistory.actor_user_id == User.id)
        .where(StageHistory.application_id == application_id)
        .order_by(desc(StageHistory.created_at))
    )

    rows = (await session.execute(stmt)).all()

    return [
        StageHistoryItem(
            from_stage=row.from_stage,
            to_stage=row.to_stage,
            actor_type=row.actor_type,
            actor_name=row.actor_name,
            reason=row.reason,
            created_at=row.created_at,
        )
        for row in rows
    ]
