from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc, case
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from datetime import date, datetime, timedelta, timezone
import math

from ..models import Vacancy, VacancyTeam, VacancyStage, User, Application, Client, RejectReason
from ..schemas.vacancy import (
    VacancyCreate, VacancyUpdate, VacancyArchive, VacancySidebar, VacancySidebarItem,
    VacancyStageCount, VacancyDetail, VacancyStageCreate, VacancyStageUpdate, VacancyStageReorder
)
from ..schemas.base import Paginated
from ..schemas.user import UserShort
from ..core.stages import get_stages_for_template, PROTECTED_STAGE_KEYS
from ..core.errors import NotFoundError, ForbiddenError, ValidationError, ConflictError
from ..services.audit import audit


async def get_vacancy_sidebar(session: AsyncSession, company_id: UUID, user_role: str = None, user_id: UUID = None) -> VacancySidebar:
    """Get sidebar data with counts"""
    # Active vacancies with counts
    query = (
        select(
            Vacancy.id,
            Vacancy.name,
            func.count(Application.id).label("count"),
            func.count(
                case(
                    # «Новые» (синий бейдж +N): этапы «Отклик» + «Добавлен» —
                    # кандидаты, с которыми ещё не было работы.
                    (Application.stage.in_(["response", "added"]), 1),
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
    )

    # Apply role-based filtering for managers
    if user_role == "manager" and user_id:
        # Manager can only see assigned vacancies
        query = query.outerjoin(
            VacancyTeam,
            and_(
                VacancyTeam.vacancy_id == Vacancy.id,
                VacancyTeam.user_id == user_id
            )
        ).where(
            # User is assigned via VacancyTeam OR responsible_user_id
            (VacancyTeam.user_id == user_id) | (Vacancy.responsible_user_id == user_id)
        )

    query = query.group_by(Vacancy.id, Vacancy.name, Vacancy.sort_order).order_by(Vacancy.sort_order, Vacancy.name)

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


async def get_archived_vacancies(
    session: AsyncSession, company_id: UUID, user_role: str = None, user_id: UUID = None
) -> list[dict]:
    """Архивные вакансии с агрегатами (всего кандидатов / нанято) для страницы Архив."""
    query = (
        select(
            Vacancy.id,
            Vacancy.name,
            Client.name.label("client_name"),
            User.full_name.label("recruiter_name"),
            Vacancy.archive_result,
            Vacancy.closed_at,
            Vacancy.created_at,
            func.count(Application.id).label("candidates"),
            func.count(
                case((Application.stage == "hired", 1), else_=None)
            ).label("hired"),
        )
        .select_from(Vacancy)
        .outerjoin(Application, Application.vacancy_id == Vacancy.id)
        .outerjoin(Client, Client.id == Vacancy.client_id)
        .outerjoin(User, User.id == Vacancy.responsible_user_id)
        .where(Vacancy.company_id == company_id, Vacancy.status == "archived")
    )

    # Менеджер видит только назначенные вакансии
    if user_role == "manager" and user_id:
        query = query.outerjoin(
            VacancyTeam,
            and_(VacancyTeam.vacancy_id == Vacancy.id, VacancyTeam.user_id == user_id),
        ).where((VacancyTeam.user_id == user_id) | (Vacancy.responsible_user_id == user_id))

    query = query.group_by(
        Vacancy.id, Vacancy.name, Client.name, User.full_name,
        Vacancy.archive_result, Vacancy.closed_at, Vacancy.created_at,
    ).order_by(Vacancy.closed_at.desc(), Vacancy.name)

    rows = (await session.execute(query)).fetchall()
    return [
        {
            "id": r.id,
            "name": r.name,
            "client_name": r.client_name,
            "recruiter_name": r.recruiter_name,
            "archive_result": r.archive_result,
            "closed_at": r.closed_at,
            "created_at": r.created_at,
            "candidates": r.candidates,
            "hired": r.hired,
        }
        for r in rows
    ]




async def get_vacancies_paginated(
    session: AsyncSession,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24,
    status: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    order: str = "desc",
    user_role: str = None,
    user_id: UUID = None
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

    # Apply role-based filtering for managers
    if user_role == "manager" and user_id:
        # Manager can only see assigned vacancies
        base_query = base_query.outerjoin(
            VacancyTeam,
            and_(
                VacancyTeam.vacancy_id == Vacancy.id,
                VacancyTeam.user_id == user_id
            )
        ).where(
            Vacancy.company_id == company_id,
            # User is assigned via VacancyTeam OR responsible_user_id
            (VacancyTeam.user_id == user_id) | (Vacancy.responsible_user_id == user_id)
        )

    if status:
        base_query = base_query.where(Vacancy.status == status)

    if search:
        base_query = base_query.where(Vacancy.name.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count(Vacancy.id)).where(Vacancy.company_id == company_id)

    # Apply role-based filtering for managers in count query too
    if user_role == "manager" and user_id:
        count_query = count_query.outerjoin(
            VacancyTeam,
            and_(
                VacancyTeam.vacancy_id == Vacancy.id,
                VacancyTeam.user_id == user_id
            )
        ).where(
            Vacancy.company_id == company_id,
            # User is assigned via VacancyTeam OR responsible_user_id
            (VacancyTeam.user_id == user_id) | (Vacancy.responsible_user_id == user_id)
        )

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

    # If client_id provided, ensure client exists and belongs to company
    if vacancy_data.client_id:
        client_result = await session.execute(
            select(Client).where(Client.id == vacancy_data.client_id, Client.company_id == company_id)
        )
        if not client_result.scalar_one_or_none():
            raise NotFoundError("Клиент")

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
        recruiter_scoring_instructions=vacancy_data.recruiter_scoring_instructions,
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

    # Create stages with new priority order:
    # 1. Custom from form (if specified)
    # 2. Company default stages (if exist)
    # 3. Template stages (fallback for backward compatibility)
    if vacancy_data.stages is not None and len(vacancy_data.stages) > 0:
        # 1. Use custom stages from form
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
        # 2. Try to use company default stages
        from ..models import CompanyDefaultStage
        company_stages_result = await session.execute(
            select(CompanyDefaultStage)
            .where(CompanyDefaultStage.company_id == company_id)
            .order_by(CompanyDefaultStage.order_index)
        )
        company_stages = list(company_stages_result.scalars().all())

        if company_stages:
            # Use company default stages
            for company_stage in company_stages:
                stage = VacancyStage(
                    company_id=company_id,
                    vacancy_id=vacancy.id,
                    stage_key=company_stage.stage_key,
                    label=company_stage.label,
                    order_index=company_stage.order_index,
                    is_terminal=company_stage.is_terminal
                )
                session.add(stage)
        else:
            # 3. Fallback to template stages for backward compatibility
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

    # Reject reasons (привязанные к вакансии), как и этапы:
    # 1. из формы (если переданы) → привязать к вакансии;
    # 2. иначе — копия дефолтов компании (с сохранением системных).
    from ..models import RejectReason
    from .settings.reject_reasons import copy_default_reasons_to_vacancy
    if vacancy_data.reject_reasons:
        for r in vacancy_data.reject_reasons:
            session.add(
                RejectReason(
                    company_id=company_id,
                    vacancy_id=vacancy.id,
                    side=r.side,
                    label=r.label.strip()[:120],
                    order_index=r.order_index,
                    is_system=r.is_system,
                    is_active=True,
                )
            )
        await session.flush()
    else:
        await copy_default_reasons_to_vacancy(session, company_id, vacancy.id)

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
    if vacancy_data.recruiter_scoring_instructions is not None:
        vacancy.recruiter_scoring_instructions = vacancy_data.recruiter_scoring_instructions
    if vacancy_data.glafira_mode is not None:
        vacancy.glafira_mode = vacancy_data.glafira_mode

    # client_id: обновляем явно, если поле РЕАЛЬНО прислано (model_fields_set) —
    # это позволяет и сменить заказчика, и сбросить его в None. Раньше client_id
    # вообще не обрабатывался → смена заказчика молча терялась.
    if 'client_id' in vacancy_data.model_fields_set:
        if vacancy_data.client_id is not None:
            client_result = await session.execute(
                select(Client).where(
                    Client.id == vacancy_data.client_id,
                    Client.company_id == company_id,
                )
            )
            if not client_result.scalar_one_or_none():
                raise NotFoundError("Клиент")
        vacancy.client_id = vacancy_data.client_id

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


async def duplicate_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> Vacancy:
    """Создать копию вакансии: поля + этапы + причины отказа + команда. БЕЗ заявок."""
    src = await get_vacancy(session, vacancy_id, company_id)

    new_v = Vacancy(
        company_id=company_id,
        name=f"{src.name} (копия)",
        sort_order=src.sort_order,
        client_id=src.client_id,
        city=src.city,
        deadline=src.deadline,
        positions_count=src.positions_count,
        department=src.department,
        employment_type=src.employment_type,
        is_confidential=src.is_confidential,
        salary_from=src.salary_from,
        salary_to=src.salary_to,
        currency=src.currency,
        description=src.description,
        funnel_template=src.funnel_template,
        glafira_mode=src.glafira_mode,
        responsible_user_id=src.responsible_user_id,
        # status='active' (default); archive_result/closed_at/external_*/hh_* — не копируем
    )
    session.add(new_v)
    await session.flush()

    # Этапы воронки
    src_stages = (await session.execute(
        select(VacancyStage)
        .where(VacancyStage.vacancy_id == vacancy_id, VacancyStage.company_id == company_id)
        .order_by(VacancyStage.order_index)
    )).scalars().all()
    for s in src_stages:
        session.add(VacancyStage(
            company_id=company_id, vacancy_id=new_v.id,
            stage_key=s.stage_key, label=s.label,
            order_index=s.order_index, is_terminal=s.is_terminal,
        ))

    # Причины отказа (per-vacancy)
    src_reasons = (await session.execute(
        select(RejectReason).where(
            RejectReason.vacancy_id == vacancy_id,
            RejectReason.company_id == company_id,
        )
    )).scalars().all()
    for r in src_reasons:
        session.add(RejectReason(
            company_id=company_id, vacancy_id=new_v.id,
            side=r.side, label=r.label, order_index=r.order_index,
            is_active=r.is_active, is_system=r.is_system,
        ))

    # Команда
    src_team = (await session.execute(
        select(VacancyTeam).where(
            VacancyTeam.vacancy_id == vacancy_id,
            VacancyTeam.company_id == company_id,
        )
    )).scalars().all()
    for t in src_team:
        session.add(VacancyTeam(
            company_id=company_id, vacancy_id=new_v.id,
            user_id=t.user_id, is_responsible=t.is_responsible,
        ))

    await session.flush()
    await audit(
        session, action="duplicate", entity_type="vacancy",
        entity_id=new_v.id,
        after={"name": new_v.name, "source_id": str(vacancy_id)},
        actor_user_id=actor_user_id, company_id=company_id,
    )
    return new_v


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


async def add_vacancy_stage(
    session: AsyncSession,
    vacancy_id: UUID,
    stage_data: VacancyStageCreate,
    company_id: UUID,
    actor_user_id: UUID
) -> VacancyStage:
    """Add new stage to vacancy"""
    # Get vacancy to ensure it exists and belongs to company
    vacancy = await get_vacancy(session, vacancy_id, company_id)

    # Check stage_key uniqueness within vacancy
    existing_stage = await session.execute(
        select(VacancyStage).where(
            VacancyStage.vacancy_id == vacancy_id,
            VacancyStage.stage_key == stage_data.stage_key
        )
    )
    if existing_stage.scalar_one_or_none() is not None:
        raise ConflictError(f"Этап с ключом '{stage_data.stage_key}' уже существует")

    # Create new stage
    stage = VacancyStage(
        company_id=company_id,
        vacancy_id=vacancy_id,
        stage_key=stage_data.stage_key,
        label=stage_data.label,
        order_index=stage_data.order_index,
        is_terminal=stage_data.is_terminal
    )

    session.add(stage)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="stage_create",
        entity_type="vacancy_stage",
        entity_id=stage.id,
        after={
            "vacancy_id": str(vacancy_id),
            "stage_key": stage.stage_key,
            "label": stage.label,
            "order_index": stage.order_index,
            "is_terminal": stage.is_terminal,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return stage


async def rename_vacancy_stage(
    session: AsyncSession,
    vacancy_id: UUID,
    stage_key: str,
    stage_data: VacancyStageUpdate,
    company_id: UUID,
    actor_user_id: UUID
) -> VacancyStage:
    """Rename stage (update only label, stage_key is immutable)"""
    # Get vacancy to ensure it exists and belongs to company
    await get_vacancy(session, vacancy_id, company_id)

    # Get stage
    result = await session.execute(
        select(VacancyStage).where(
            VacancyStage.vacancy_id == vacancy_id,
            VacancyStage.company_id == company_id,
            VacancyStage.stage_key == stage_key
        )
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise NotFoundError("Этап")

    # Save old value for audit
    before = {"label": stage.label}

    # Update label only
    stage.label = stage_data.label
    await session.flush()

    # Audit log
    await audit(
        session,
        action="stage_rename",
        entity_type="vacancy_stage",
        entity_id=stage.id,
        before=before,
        after={
            "label": stage.label,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return stage


async def delete_vacancy_stage(
    session: AsyncSession,
    vacancy_id: UUID,
    stage_key: str,
    company_id: UUID,
    actor_user_id: UUID
) -> None:
    """Delete stage with guards: must not be protected and must be empty"""
    # Get vacancy to ensure it exists and belongs to company
    await get_vacancy(session, vacancy_id, company_id)

    # Check if stage is protected
    if stage_key in PROTECTED_STAGE_KEYS:
        raise ValidationError("Системный этап нельзя удалить")

    # Get stage with count (reuse existing function)
    stages_with_counts = await get_vacancy_stages(session, vacancy_id, company_id)
    stage_to_delete = None
    for stage_count in stages_with_counts:
        if stage_count.stage_key == stage_key:
            stage_to_delete = stage_count
            break

    if stage_to_delete is None:
        raise NotFoundError("Этап")

    # Check if stage is empty
    if stage_to_delete.count > 0:
        raise ValidationError("Переместите кандидатов с этапа перед удалением")

    # Get the actual stage record for deletion and audit
    result = await session.execute(
        select(VacancyStage).where(
            VacancyStage.vacancy_id == vacancy_id,
            VacancyStage.company_id == company_id,
            VacancyStage.stage_key == stage_key
        )
    )
    stage = result.scalar_one()

    # Save for audit before deletion
    stage_data = {
        "vacancy_id": str(vacancy_id),
        "stage_key": stage.stage_key,
        "label": stage.label,
        "order_index": stage.order_index,
        "is_terminal": stage.is_terminal,
    }

    # Delete stage
    await session.delete(stage)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="stage_delete",
        entity_type="vacancy_stage",
        entity_id=stage.id,
        before=stage_data,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )


async def reorder_vacancy_stages(
    session: AsyncSession,
    vacancy_id: UUID,
    reorder_data: VacancyStageReorder,
    company_id: UUID,
    actor_user_id: UUID
) -> list[VacancyStage]:
    """Reorder stages by updating order_index"""
    # Get vacancy to ensure it exists and belongs to company
    await get_vacancy(session, vacancy_id, company_id)

    # Get all existing stages
    result = await session.execute(
        select(VacancyStage).where(
            VacancyStage.vacancy_id == vacancy_id,
            VacancyStage.company_id == company_id
        ).order_by(VacancyStage.order_index)
    )
    existing_stages = result.scalars().all()

    # Validate that provided order matches existing stage_keys
    existing_keys = {stage.stage_key for stage in existing_stages}
    provided_keys = set(reorder_data.order)

    if existing_keys != provided_keys:
        raise ValidationError("Переданные этапы не соответствуют этапам вакансии")

    # Save old order for audit
    before = {stage.stage_key: stage.order_index for stage in existing_stages}

    # Update order_index based on position in new order
    stages_by_key = {stage.stage_key: stage for stage in existing_stages}
    updated_stages = []

    for i, stage_key in enumerate(reorder_data.order, 1):
        stage = stages_by_key[stage_key]
        stage.order_index = i
        updated_stages.append(stage)

    await session.flush()

    # Save new order for audit
    after = {stage.stage_key: stage.order_index for stage in updated_stages}

    # Audit log
    await audit(
        session,
        action="stage_reorder",
        entity_type="vacancy",
        entity_id=vacancy_id,
        before={"stages_order": before},
        after={"stages_order": after},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return updated_stages