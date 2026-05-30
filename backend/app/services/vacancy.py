from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc, case
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from datetime import date, datetime, timedelta, timezone
import math

from ..models import Vacancy, VacancyTeam, VacancyStage, User, Application, Client
from ..schemas.vacancy import VacancyCreate, VacancyUpdate, VacancyArchive, VacancySidebar, VacancySidebarItem, VacancyStageCount, VacancyDetail
from ..schemas.base import Paginated
from ..schemas.user import UserShort
from ..core.stages import get_stages_for_template
from ..core.errors import NotFoundError, ForbiddenError
from ..services.audit import audit


async def get_vacancy_sidebar(session: AsyncSession, company_id: UUID) -> VacancySidebar:
    """Get sidebar data with counts"""
    # Active vacancies with counts
    query = (
        select(
            Vacancy.id,
            Vacancy.name,
            func.count(Application.id).label("count"),
            func.count(
                case(
                    (
                        and_(
                            Application.stage == "response",
                            Application.created_at >= datetime.now(timezone.utc) - timedelta(days=1)
                        ),
                        1
                    ),
                    else_=None
                )
            ).label("new_count")
        )
        .select_from(Vacancy)
        .outerjoin(Application, and_(
            Application.vacancy_id == Vacancy.id,
            Application.stage != "rejected"
        ))
        .where(
            Vacancy.company_id == company_id,
            Vacancy.status == "active"
        )
        .group_by(Vacancy.id, Vacancy.name, Vacancy.sort_order)
        .order_by(Vacancy.sort_order, Vacancy.name)
    )

    result = await session.execute(query)
    rows = result.fetchall()

    items = []
    for row in rows:
        items.append(VacancySidebarItem(
            id=row.id,
            name=row.name,
            count=row.count,
            new_count=row.new_count
        ))

    # Count archived vacancies
    archived_result = await session.execute(
        select(func.count(Vacancy.id))
        .where(
            Vacancy.company_id == company_id,
            Vacancy.status == "archived"
        )
    )
    archived_count = archived_result.scalar_one()

    return VacancySidebar(items=items, archived_count=archived_count)


async def get_vacancies(
    session: AsyncSession,
    company_id: UUID,
    status: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    order: str = "desc"
) -> list[Vacancy]:
    """Get list of vacancies"""
    query = select(Vacancy).where(Vacancy.company_id == company_id)

    if status:
        query = query.where(Vacancy.status == status)

    if search:
        query = query.where(Vacancy.name.ilike(f"%{search}%"))

    # Apply sorting
    sort_column = Vacancy.created_at  # default
    if sort == "name":
        sort_column = Vacancy.name
    elif sort == "deadline":
        sort_column = Vacancy.deadline

    if order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    result = await session.execute(query)
    return result.scalars().all()


async def get_vacancies_paginated(
    session: AsyncSession,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24,
    status: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    order: str = "desc"
) -> Paginated[VacancyDetail]:
    """Get paginated list of vacancies with full VacancyDetail"""
    # Base query with all needed joins
    base_query = (
        select(Vacancy)
        .options(
            selectinload(Vacancy.team).selectinload(VacancyTeam.user),
            selectinload(Vacancy.responsible_user),
            selectinload(Vacancy.client),
            selectinload(Vacancy.stages)
        )
        .where(Vacancy.company_id == company_id)
    )

    if status:
        base_query = base_query.where(Vacancy.status == status)

    if search:
        base_query = base_query.where(Vacancy.name.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count(Vacancy.id)).where(Vacancy.company_id == company_id)
    if status:
        count_query = count_query.where(Vacancy.status == status)
    if search:
        count_query = count_query.where(Vacancy.name.ilike(f"%{search}%"))

    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Apply sorting
    sort_column = Vacancy.created_at  # default
    if sort == "name":
        sort_column = Vacancy.name
    elif sort == "deadline":
        sort_column = Vacancy.deadline

    if order == "asc":
        base_query = base_query.order_by(asc(sort_column))
    else:
        base_query = base_query.order_by(desc(sort_column))

    # Apply pagination
    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)

    result = await session.execute(base_query)
    vacancies = result.scalars().all()

    # Convert to VacancyDetail schemas
    items = []
    for vacancy in vacancies:
        # Build VacancyDetail - field validator handles team conversion automatically
        data = VacancyDetail.model_validate(vacancy)

        # Set client name manually as it's computed field
        data.client_name = vacancy.client.name if vacancy.client else None

        items.append(data)

    pages = math.ceil(total / page_size) if total > 0 else 0

    return Paginated[VacancyDetail](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages
    )


async def get_vacancy(session: AsyncSession, vacancy_id: UUID, company_id: UUID) -> Vacancy:
    """Get vacancy by ID with team and stages"""
    result = await session.execute(
        select(Vacancy)
        .options(
            selectinload(Vacancy.team).selectinload(VacancyTeam.user),
            selectinload(Vacancy.responsible_user),
            selectinload(Vacancy.client),
            selectinload(Vacancy.stages)
        )
        .where(Vacancy.id == vacancy_id, Vacancy.company_id == company_id)
    )
    vacancy = result.scalar_one_or_none()
    if vacancy is None:
        raise NotFoundError("Вакансия")
    return vacancy


async def create_vacancy(
    session: AsyncSession,
    vacancy_data: VacancyCreate,
    company_id: UUID,
    actor_user_id: UUID
) -> Vacancy:
    """Create new vacancy with stages and team"""
    # Create vacancy
    vacancy = Vacancy(
        company_id=company_id,
        name=vacancy_data.name,
        sort_order=vacancy_data.sort_order,
        client_id=vacancy_data.client_id,
        city=vacancy_data.city,
        deadline=vacancy_data.deadline,
        positions_count=vacancy_data.positions_count,
        department=vacancy_data.department,
        employment_type=vacancy_data.employment_type,
        is_confidential=vacancy_data.is_confidential,
        salary_from=vacancy_data.salary_from,
        salary_to=vacancy_data.salary_to,
        currency=vacancy_data.currency,
        description=vacancy_data.description,
        funnel_template=vacancy_data.funnel_template,
        glafira_mode=vacancy_data.glafira_mode,
    )

    session.add(vacancy)
    await session.flush()

    # Set responsible user (first in team list)
    if vacancy_data.team:
        vacancy.responsible_user_id = vacancy_data.team[0]

    # Create team members
    for i, user_id in enumerate(vacancy_data.team):
        team_member = VacancyTeam(
            company_id=company_id,
            vacancy_id=vacancy.id,
            user_id=user_id,
            is_responsible=(i == 0)
        )
        session.add(team_member)

    # Create stages - either custom or from template
    if vacancy_data.stages is not None and len(vacancy_data.stages) > 0:
        # Use custom stages
        for stage_input in vacancy_data.stages:
            stage = VacancyStage(
                company_id=company_id,
                vacancy_id=vacancy.id,
                stage_key=stage_input.stage_key,
                label=stage_input.label,
                order_index=stage_input.order_index,
                is_terminal=stage_input.is_terminal
            )
            session.add(stage)
    else:
        # Use template stages for backward compatibility
        stages = get_stages_for_template(vacancy_data.funnel_template)
        for stage_def in stages:
            stage = VacancyStage(
                company_id=company_id,
                vacancy_id=vacancy.id,
                stage_key=stage_def.key,
                label=stage_def.label,
                order_index=stage_def.order_index,
                is_terminal=stage_def.is_terminal
            )
            session.add(stage)

    await session.flush()

    # Audit log
    await audit(
        session,
        action="create",
        entity_type="vacancy",
        entity_id=vacancy.id,
        after={
            "name": vacancy.name,
            "status": vacancy.status,
            "funnel_template": vacancy.funnel_template,
            "team": [str(uid) for uid in vacancy_data.team],
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return vacancy


async def update_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    vacancy_data: VacancyUpdate,
    company_id: UUID,
    actor_user_id: UUID
) -> Vacancy:
    """Update vacancy"""
    vacancy = await get_vacancy(session, vacancy_id, company_id)

    # Save old values for audit
    before = {
        "name": vacancy.name,
        "status": vacancy.status,
        "glafira_mode": vacancy.glafira_mode,
        "archive_result": vacancy.archive_result,
        "closed_at": vacancy.closed_at.isoformat() if vacancy.closed_at else None,
    }

    # Detect restore from archive (archived → active)
    is_restore = (vacancy.status == "archived" and
                  hasattr(vacancy_data, 'status') and
                  vacancy_data.status == "active")

    # Update fields
    if vacancy_data.name is not None:
        vacancy.name = vacancy_data.name
    if vacancy_data.sort_order is not None:
        vacancy.sort_order = vacancy_data.sort_order
    if vacancy_data.city is not None:
        vacancy.city = vacancy_data.city
    if vacancy_data.deadline is not None:
        vacancy.deadline = vacancy_data.deadline
    if vacancy_data.positions_count is not None:
        vacancy.positions_count = vacancy_data.positions_count
    if vacancy_data.department is not None:
        vacancy.department = vacancy_data.department
    if vacancy_data.employment_type is not None:
        vacancy.employment_type = vacancy_data.employment_type
    if vacancy_data.is_confidential is not None:
        vacancy.is_confidential = vacancy_data.is_confidential
    if vacancy_data.salary_from is not None:
        vacancy.salary_from = vacancy_data.salary_from
    if vacancy_data.salary_to is not None:
        vacancy.salary_to = vacancy_data.salary_to
    if vacancy_data.currency is not None:
        vacancy.currency = vacancy_data.currency
    if vacancy_data.description is not None:
        vacancy.description = vacancy_data.description
    if vacancy_data.glafira_mode is not None:
        vacancy.glafira_mode = vacancy_data.glafira_mode

    # Handle status update with restore logic
    if hasattr(vacancy_data, 'status') and vacancy_data.status is not None:
        vacancy.status = vacancy_data.status

        # If restoring from archive, clear archive fields in same transaction
        if is_restore:
            vacancy.archive_result = None
            vacancy.closed_at = None

    # Handle team updates
    if vacancy_data.team is not None:
        # Remove existing team members
        await session.execute(
            VacancyTeam.__table__.delete().where(VacancyTeam.vacancy_id == vacancy.id)
        )

        # Add new team members
        if vacancy_data.team:
            vacancy.responsible_user_id = vacancy_data.team[0]
            for i, user_id in enumerate(vacancy_data.team):
                team_member = VacancyTeam(
                    company_id=company_id,
                    vacancy_id=vacancy.id,
                    user_id=user_id,
                    is_responsible=(i == 0)
                )
                session.add(team_member)

    await session.flush()

    # Audit log - use different action for restore
    audit_action = "vacancy_restore" if is_restore else "vacancy_update"
    after_data = {
        "name": vacancy.name,
        "status": vacancy.status,
        "glafira_mode": vacancy.glafira_mode,
    }
    if is_restore:
        after_data.update({
            "archive_result": vacancy.archive_result,
            "closed_at": vacancy.closed_at.isoformat() if vacancy.closed_at else None,
        })

    await audit(
        session,
        action=audit_action,
        entity_type="vacancy",
        entity_id=vacancy.id,
        before=before,
        after=after_data,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return vacancy


async def archive_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    archive_data: VacancyArchive,
    company_id: UUID,
    actor_user_id: UUID
) -> Vacancy:
    """Archive vacancy"""
    vacancy = await get_vacancy(session, vacancy_id, company_id)

    if vacancy.status == "archived":
        raise ForbiddenError("Вакансия уже в архиве")

    # Save old status
    before = {"status": vacancy.status}

    # Update status
    vacancy.status = "archived"
    vacancy.archive_result = archive_data.result
    vacancy.closed_at = date.today()

    await session.flush()

    # Audit log
    await audit(
        session,
        action="archive",
        entity_type="vacancy",
        entity_id=vacancy.id,
        before=before,
        after={
            "status": vacancy.status,
            "archive_result": vacancy.archive_result,
            "closed_at": vacancy.closed_at.isoformat(),
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return vacancy


async def get_vacancy_stages(session: AsyncSession, vacancy_id: UUID, company_id: UUID) -> list[VacancyStageCount]:
    """Get stages with counts for vacancy funnel"""
    # Get stages with application counts
    query = (
        select(
            VacancyStage.stage_key,
            VacancyStage.label,
            VacancyStage.is_terminal,
            func.count(Application.id).label("count")
        )
        .select_from(VacancyStage)
        .outerjoin(
            Application,
            and_(
                Application.vacancy_id == VacancyStage.vacancy_id,
                Application.stage == VacancyStage.stage_key
            )
        )
        .where(
            VacancyStage.vacancy_id == vacancy_id,
            VacancyStage.company_id == company_id
        )
        .group_by(
            VacancyStage.stage_key,
            VacancyStage.label,
            VacancyStage.order_index,
            VacancyStage.is_terminal
        )
        .order_by(VacancyStage.order_index)
    )

    result = await session.execute(query)
    rows = result.fetchall()

    # Map stage keys to colors from stages.py
    from ..core.stages import STAGES
    stage_colors = {key: stage.color for key, stage in STAGES.items()}

    stages = []
    for row in rows:
        stages.append(VacancyStageCount(
            stage_key=row.stage_key,
            label=row.label,
            color=stage_colors.get(row.stage_key, "#9AA3AE"),
            count=row.count,
            is_terminal=row.is_terminal
        ))

    return stages