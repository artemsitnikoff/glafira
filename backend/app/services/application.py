from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, asc, func, or_
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from datetime import datetime, timezone
import math

from ..models import Application, StageHistory, Candidate, Vacancy, User
from ..schemas.application import ApplicationRow, MoveRequest, RejectRequest, BulkMoveRequest, BulkRejectRequest, StageHistoryItem
from ..schemas.base import Paginated
from ..core.errors import NotFoundError, ValidationError
from ..services.audit import audit


async def get_applications_for_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    company_id: UUID,
    stage: str | None = None,
    search: str | None = None,
    score_min: int | None = None,
    salary_max: int | None = None,
    source: str | None = None,
    city: str | None = None,
    sort: str | None = None,
    order: str = "desc"
) -> list[ApplicationRow]:
    """Get applications for vacancy with filters"""
    # Build base query with joins
    query = (
        select(
            Application.id,
            Application.candidate_id,
            Application.stage,
            Application.ai_score,
            Application.selected_at,
            Candidate.display_number,
            Candidate.full_name,
            Candidate.avatar_url,
            Candidate.phone,
            Candidate.salary_expectation,
            Candidate.currency,
            Candidate.city,
            Candidate.last_position,
            # TODO: add computed age, has_pdn, messengers, stage_color
        )
        .select_from(Application)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(
            Application.vacancy_id == vacancy_id,
            Application.company_id == company_id
        )
    )

    # Apply filters
    if stage:
        query = query.where(Application.stage == stage)

    if search:
        query = query.where(
            or_(
                Candidate.full_name.ilike(f"%{search}%"),
                Candidate.phone.ilike(f"%{search}%"),
                Candidate.email.ilike(f"%{search}%")
            )
        )

    if score_min:
        query = query.where(Application.ai_score >= score_min)

    if salary_max and salary_max > 0:
        query = query.where(
            or_(
                Candidate.salary_expectation.is_(None),
                Candidate.salary_expectation <= salary_max
            )
        )

    if source:
        query = query.where(Candidate.source == source)

    if city:
        query = query.where(Candidate.city.ilike(f"%{city}%"))

    # Apply sorting
    sort_column = Application.created_at  # default
    if sort == "score":
        sort_column = Application.ai_score
    elif sort == "name":
        sort_column = Candidate.full_name
    elif sort == "salary":
        sort_column = Candidate.salary_expectation
    elif sort == "city":
        sort_column = Candidate.city
    elif sort == "date":
        sort_column = Application.created_at

    if order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    result = await session.execute(query)
    rows = result.fetchall()

    # Convert to response models
    applications = []
    for row in rows:
        # Calculate age (simplified)
        age = None  # TODO: calculate from birth_date

        # Get messengers (simplified)
        messengers = []  # TODO: get from candidate

        # Get stage color from stages.py
        from ..core.stages import STAGES
        stage_colors = {key: stage.color for key, stage in STAGES.items()}

        applications.append(ApplicationRow(
            id=row.id,
            candidate_id=row.candidate_id,
            display_number=row.display_number,
            full_name=row.full_name,
            avatar_url=row.avatar_url,
            age=age,
            last_position=row.last_position,
            ai_score=row.ai_score,
            has_pdn=False,  # TODO: check consent
            phone=row.phone,
            messengers=messengers,
            salary_expectation=row.salary_expectation,
            currency=row.currency or "RUB",
            city=row.city,
            stage=row.stage,
            stage_color=stage_colors.get(row.stage, "#9AA3AE"),
            selected_at=row.selected_at
        ))

    return applications


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
    sort: str | None = None,
    order: str = "desc"
) -> Paginated[ApplicationRow]:
    """Get paginated applications for vacancy with filters"""
    # Base query for counting
    count_query = (
        select(func.count(Application.id))
        .select_from(Application)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(
            Application.vacancy_id == vacancy_id,
            Application.company_id == company_id
        )
    )

    # Apply filters to count query
    if stage:
        count_query = count_query.where(Application.stage == stage)

    if search:
        count_query = count_query.where(
            or_(
                Candidate.full_name.ilike(f"%{search}%"),
                Candidate.phone.ilike(f"%{search}%"),
                Candidate.email.ilike(f"%{search}%")
            )
        )

    if score_min:
        count_query = count_query.where(Application.ai_score >= score_min)

    if salary_max and salary_max > 0:
        count_query = count_query.where(
            or_(
                Candidate.salary_expectation.is_(None),
                Candidate.salary_expectation <= salary_max
            )
        )

    if source:
        count_query = count_query.where(Candidate.source == source)

    if city:
        count_query = count_query.where(Candidate.city.ilike(f"%{city}%"))

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Build main query with pagination
    query = (
        select(
            Application.id,
            Application.candidate_id,
            Application.stage,
            Application.ai_score,
            Application.selected_at,
            Candidate.display_number,
            Candidate.full_name,
            Candidate.avatar_url,
            Candidate.phone,
            Candidate.salary_expectation,
            Candidate.currency,
            Candidate.city,
            Candidate.last_position,
        )
        .select_from(Application)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(
            Application.vacancy_id == vacancy_id,
            Application.company_id == company_id
        )
    )

    # Apply same filters to main query
    if stage:
        query = query.where(Application.stage == stage)

    if search:
        query = query.where(
            or_(
                Candidate.full_name.ilike(f"%{search}%"),
                Candidate.phone.ilike(f"%{search}%"),
                Candidate.email.ilike(f"%{search}%")
            )
        )

    if score_min:
        query = query.where(Application.ai_score >= score_min)

    if salary_max and salary_max > 0:
        query = query.where(
            or_(
                Candidate.salary_expectation.is_(None),
                Candidate.salary_expectation <= salary_max
            )
        )

    if source:
        query = query.where(Candidate.source == source)

    if city:
        query = query.where(Candidate.city.ilike(f"%{city}%"))

    # Apply sorting
    sort_column = Application.created_at  # default
    if sort == "score":
        sort_column = Application.ai_score
    elif sort == "name":
        sort_column = Candidate.full_name
    elif sort == "salary":
        sort_column = Candidate.salary_expectation
    elif sort == "city":
        sort_column = Candidate.city
    elif sort == "date":
        sort_column = Application.created_at

    if order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await session.execute(query)
    rows = result.fetchall()

    # Convert to response models
    from ..core.stages import STAGES
    stage_colors = {key: stage.color for key, stage in STAGES.items()}

    applications = []
    for row in rows:
        applications.append(ApplicationRow(
            id=row.id,
            candidate_id=row.candidate_id,
            display_number=row.display_number,
            full_name=row.full_name,
            avatar_url=row.avatar_url,
            age=None,  # TODO: calculate from birth_date
            last_position=row.last_position,
            ai_score=row.ai_score,
            has_pdn=False,  # TODO: check consent
            phone=row.phone,
            messengers=[],  # TODO: get from candidate
            salary_expectation=row.salary_expectation,
            currency=row.currency or "RUB",
            city=row.city,
            stage=row.stage,
            stage_color=stage_colors.get(row.stage, "#9AA3AE"),
            selected_at=row.selected_at
        ))

    pages = math.ceil(total / page_size) if total > 0 else 0

    return Paginated[ApplicationRow](
        items=applications,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages
    )


async def get_application(session: AsyncSession, application_id: UUID, company_id: UUID) -> Application:
    """Get application by ID"""
    result = await session.execute(
        select(Application)
        .options(selectinload(Application.candidate))
        .where(Application.id == application_id, Application.company_id == company_id)
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise NotFoundError("Заявка")
    return application


async def move_application(
    session: AsyncSession,
    application_id: UUID,
    move_data: MoveRequest,
    company_id: UUID,
    actor_user_id: UUID
) -> Application:
    """Move application to another stage"""
    application = await get_application(session, application_id, company_id)

    # Save current stage for history
    from_stage = application.stage
    to_stage = move_data.to_stage

    if from_stage == to_stage:
        raise ValidationError("Заявка уже на этом этапе")

    # Update application
    application.stage = to_stage
    application.stage_changed_at = datetime.now(timezone.utc)

    # Create stage history entry
    history = StageHistory(
        application_id=application.id,
        from_stage=from_stage,
        to_stage=to_stage,
        actor_type="human",
        actor_user_id=actor_user_id,
        created_at=datetime.now(timezone.utc)
    )
    session.add(history)

    await session.flush()

    # TODO(phase 2.2): создание Employee при переходе в hired — инвариант #5 (TZ-0 §5)

    # Audit log
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

    return application


async def reject_application(
    session: AsyncSession,
    application_id: UUID,
    reject_data: RejectRequest,
    company_id: UUID,
    actor_user_id: UUID
) -> Application:
    """Reject application"""
    application = await get_application(session, application_id, company_id)

    # Save current stage for history
    from_stage = application.stage

    if from_stage == "rejected":
        raise ValidationError("Заявка уже отклонена")

    # Update application
    application.stage = "rejected"
    application.reject_reason = reject_data.reason
    application.reject_side = reject_data.side
    application.stage_changed_at = datetime.now(timezone.utc)

    # Create stage history entry
    history = StageHistory(
        application_id=application.id,
        from_stage=from_stage,
        to_stage="rejected",
        actor_type="human",
        actor_user_id=actor_user_id,
        reason=reject_data.reason,
        created_at=datetime.now(timezone.utc)
    )
    session.add(history)

    await session.flush()

    # Audit log
    await audit(
        session,
        action="reject",
        entity_type="application",
        entity_id=application.id,
        before={"stage": from_stage},
        after={
            "stage": "rejected",
            "reject_reason": reject_data.reason,
            "reject_side": reject_data.side
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return application


async def restore_application(
    session: AsyncSession,
    application_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> Application:
    """Restore application from rejected state"""
    application = await get_application(session, application_id, company_id)

    if application.stage != "rejected":
        raise ValidationError("Можно восстановить только отклоненную заявку")

    # Find previous stage from history
    previous_stage_result = await session.execute(
        select(StageHistory.from_stage)
        .where(
            StageHistory.application_id == application_id,
            StageHistory.to_stage == "rejected"
        )
        .order_by(desc(StageHistory.created_at))
        .limit(1)
    )
    previous_stage = previous_stage_result.scalar_one_or_none()

    # If no previous stage found, default to 'response'
    restore_to_stage = previous_stage or "response"

    # Update application
    application.stage = restore_to_stage
    application.reject_reason = None
    application.reject_side = None
    application.stage_changed_at = datetime.now(timezone.utc)

    # Create stage history entry
    history = StageHistory(
        application_id=application.id,
        from_stage="rejected",
        to_stage=restore_to_stage,
        actor_type="human",
        actor_user_id=actor_user_id,
        reason="Восстановлено",
        created_at=datetime.now(timezone.utc)
    )
    session.add(history)

    await session.flush()

    # Audit log
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

    return application


async def bulk_move_applications(
    session: AsyncSession,
    move_data: BulkMoveRequest,
    company_id: UUID,
    actor_user_id: UUID
) -> list[Application]:
    """Move multiple applications to a stage"""
    applications = []

    for app_id in move_data.application_ids:
        try:
            app = await move_application(
                session,
                app_id,
                MoveRequest(to_stage=move_data.to_stage),
                company_id,
                actor_user_id
            )
            applications.append(app)
        except Exception:
            # Continue with other applications if one fails
            continue

    return applications


async def bulk_reject_applications(
    session: AsyncSession,
    reject_data: BulkRejectRequest,
    company_id: UUID,
    actor_user_id: UUID
) -> list[Application]:
    """Reject multiple applications"""
    applications = []

    for app_id in reject_data.application_ids:
        try:
            app = await reject_application(
                session,
                app_id,
                RejectRequest(reason=reject_data.reason, side=reject_data.side),
                company_id,
                actor_user_id
            )
            applications.append(app)
        except Exception:
            # Continue with other applications if one fails
            continue

    return applications


async def get_application_history(
    session: AsyncSession,
    application_id: UUID,
    company_id: UUID
) -> list[StageHistoryItem]:
    """Get stage history for application"""
    # Verify application exists and belongs to company
    await get_application(session, application_id, company_id)

    # Get history with user names
    query = (
        select(
            StageHistory.from_stage,
            StageHistory.to_stage,
            StageHistory.actor_type,
            StageHistory.reason,
            StageHistory.created_at,
            User.full_name.label("actor_name")
        )
        .select_from(StageHistory)
        .outerjoin(User, StageHistory.actor_user_id == User.id)
        .where(StageHistory.application_id == application_id)
        .order_by(desc(StageHistory.created_at))
    )

    result = await session.execute(query)
    rows = result.fetchall()

    history = []
    for row in rows:
        history.append(StageHistoryItem(
            from_stage=row.from_stage,
            to_stage=row.to_stage,
            actor_type=row.actor_type,
            actor_name=row.actor_name,
            reason=row.reason,
            created_at=row.created_at
        ))

    return history