"""Сервис для управления сотрудниками в адаптации"""

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
import json

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...models import Application, Candidate, Employee, Event, Vacancy, User, PulseSurvey
from ...services.audit import audit
from ...schemas.base import Paginated
from ...schemas.pulse import EmployeeListItem
from ...core.errors import NotFoundError
from .plan import generate_plan_items


def compute_adapt_day(start_date: date, today: date | None = None) -> int:
    """Вычисляет количество дней адаптации"""
    if today is None:
        today = date.today()
    return (today - start_date).days


async def compute_risk_level(session: AsyncSession, employee: Employee) -> Literal['low', 'mid', 'high']:
    """Вычисляет уровень риска увольнения сотрудника"""
    from ...models import PulseSurvey

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Подсчёт пропущенных опросов за последнюю неделю
    skipped_query = select(PulseSurvey).where(
        PulseSurvey.employee_id == employee.id,
        PulseSurvey.sent_at >= week_ago,
        PulseSurvey.answered_at.is_(None)
    )
    skipped_result = await session.execute(skipped_query)
    skipped_count = len(skipped_result.scalars().all())

    # Подсчёт опросов с низкой оценкой за последнюю неделю
    low_score_query = select(PulseSurvey).where(
        PulseSurvey.employee_id == employee.id,
        PulseSurvey.sent_at >= week_ago,
        PulseSurvey.overall_score < 3
    )
    low_score_result = await session.execute(low_score_query)
    low_score_count = len(low_score_result.scalars().all())

    signals = skipped_count + low_score_count

    if signals >= 2:
        return 'high'
    elif signals == 1:
        return 'mid'
    else:
        return 'low'


async def create_employee_from_hire(
    session: AsyncSession,
    *,
    application: Application,
    company_id: UUID,
    actor_user_id: UUID,
) -> Employee:
    """Создаёт сотрудника при переходе application в hired с идемпотентностью"""

    # 1. Проверка идемпотентности
    existing_query = select(Employee).where(Employee.application_id == application.id)
    existing_result = await session.execute(existing_query)
    existing_employee = existing_result.scalar_one_or_none()

    if existing_employee:
        return existing_employee

    # 2. Загрузка кандидата и вакансии
    candidate_query = select(Candidate).options(
        selectinload(Candidate.experience)
    ).where(Candidate.id == application.candidate_id)
    candidate_result = await session.execute(candidate_query)
    candidate = candidate_result.scalar_one()

    vacancy_query = select(Vacancy).where(Vacancy.id == application.vacancy_id)
    vacancy_result = await session.execute(vacancy_query)
    vacancy = vacancy_result.scalar_one()

    # 3. Формирование ФИО
    full_name_parts = [
        candidate.last_name,
        candidate.first_name,
        candidate.middle_name
    ]
    full_name = " ".join(part for part in full_name_parts if part)

    # 4. Определение источника найма
    hire_source = vacancy.external_source or 'direct'

    # 5. Создание сотрудника
    employee = Employee(
        company_id=company_id,
        candidate_id=candidate.id,
        application_id=application.id,
        full_name=full_name,
        position=vacancy.name,
        department=vacancy.department,
        manager_user_id=vacancy.responsible_user_id,
        recruiter_user_id=actor_user_id,
        hire_source=hire_source,
        start_date=date.today(),
        status='onboarding',
        risk_level='low',
        # probation_days использует значение по умолчанию из БД
    )

    session.add(employee)
    await session.flush()

    # 6. Генерация плана адаптации
    await generate_plan_items(
        session,
        employee_id=employee.id,
        position=employee.position,
        department=employee.department,
        probation_days=employee.probation_days,
        company_id=company_id,
    )

    # 7. Создание события
    event = Event(
        company_id=company_id,
        type='qual',
        actor_type='ai',
        actor_user_id=None,
        text='Сотрудник создан, план адаптации сгенерирован',
        entities=[
            {'type': 'employee', 'id': str(employee.id), 'label': full_name},
            {'type': 'candidate', 'id': str(candidate.id), 'label': full_name},
        ],
        candidate_id=candidate.id,
        vacancy_id=vacancy.id,
    )
    session.add(event)

    # 8. Аудит
    await audit(
        session,
        action='employee_hired',
        entity_type='employee',
        entity_id=employee.id,
        after={'full_name': full_name, 'position': employee.position, 'status': 'onboarding'},
        actor_user_id=actor_user_id,
        company_id=company_id,
        actor_type='ai',
    )

    await session.flush()
    return employee


async def list_employees_paginated(
    session: AsyncSession,
    company_id: UUID,
    *,
    page: int,
    page_size: int,
    manager_user_id: UUID | None = None,
    department: str | None = None,
    risk_level: str | None = None,
    status_filter: str | None = None,
    q: str | None = None,
) -> Paginated[EmployeeListItem]:
    """Получает список сотрудников с пагинацией и фильтрами"""

    # Base query with joins for computed fields
    query = select(Employee).options(
        selectinload(Employee.manager_user)
    ).where(Employee.company_id == company_id)

    # Filters
    if manager_user_id:
        query = query.where(Employee.manager_user_id == manager_user_id)
    if department:
        query = query.where(Employee.department == department)
    if risk_level:
        query = query.where(Employee.risk_level == risk_level)
    if status_filter:
        query = query.where(Employee.status == status_filter)
    if q:
        query = query.where(Employee.full_name.ilike(f"%{q}%"))

    # Count total
    count_query = select(func.count(Employee.id)).where(Employee.company_id == company_id)
    if manager_user_id:
        count_query = count_query.where(Employee.manager_user_id == manager_user_id)
    if department:
        count_query = count_query.where(Employee.department == department)
    if risk_level:
        count_query = count_query.where(Employee.risk_level == risk_level)
    if status_filter:
        count_query = count_query.where(Employee.status == status_filter)
    if q:
        count_query = count_query.where(Employee.full_name.ilike(f"%{q}%"))

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(Employee.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(query)
    employees = result.scalars().all()

    # Get employee IDs for batch queries
    employee_ids = [emp.id for emp in employees]

    # Batch query for latest surveys per employee
    surveys_stmt = (
        select(
            PulseSurvey.employee_id,
            PulseSurvey.sent_at,
            PulseSurvey.overall_score
        )
        .where(PulseSurvey.employee_id.in_(employee_ids))
        .order_by(PulseSurvey.employee_id, PulseSurvey.sent_at.desc())
    )
    surveys_result = await session.execute(surveys_stmt)
    surveys_rows = surveys_result.all()

    # Group surveys by employee_id (first = latest)
    from collections import defaultdict
    surveys_by_employee = defaultdict(list)
    for survey_row in surveys_rows:
        surveys_by_employee[survey_row.employee_id].append(survey_row)

    # Batch query for candidate avatar_urls
    candidate_ids = [emp.candidate_id for emp in employees if emp.candidate_id]
    candidates_stmt = (
        select(Candidate.id, Candidate.avatar_url)
        .where(Candidate.id.in_(candidate_ids))
    )
    candidates_result = await session.execute(candidates_stmt)
    candidates_data = {row.id: row.avatar_url for row in candidates_result}

    # Convert to response format with computed fields
    items = []
    for employee in employees:
        # Compute risk level if needed
        risk_level = await compute_risk_level(session, employee)
        adapt_day = compute_adapt_day(employee.start_date)
        manager_full_name = employee.manager_user.full_name if employee.manager_user else None

        # Get latest survey info
        employee_surveys = surveys_by_employee[employee.id]
        last_survey_date = None
        last_survey_mood = None
        if employee_surveys:
            latest_survey = employee_surveys[0]  # first = latest
            last_survey_date = latest_survey.sent_at
            last_survey_mood = latest_survey.overall_score

        # Get avatar_url from candidate
        avatar_url = candidates_data.get(employee.candidate_id) if employee.candidate_id else None

        item = EmployeeListItem(
            id=employee.id,
            full_name=employee.full_name,
            position=employee.position,
            department=employee.department,
            avatar_url=avatar_url,
            probation_days=employee.probation_days,
            start_date=employee.start_date,
            adapt_day=adapt_day,
            status=employee.status,
            risk_level=risk_level,
            enps=employee.enps,
            manager_full_name=manager_full_name,
            last_survey_date=last_survey_date,
            last_survey_mood=last_survey_mood,
        )
        items.append(item)

    pages = (total + page_size - 1) // page_size
    return Paginated(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


async def get_employee(session: AsyncSession, employee_id: UUID, company_id: UUID) -> Employee:
    """Получает сотрудника со всеми связанными данными"""
    query = select(Employee).options(
        selectinload(Employee.manager_user),
        selectinload(Employee.recruiter_user),
        selectinload(Employee.plan_items),
        selectinload(Employee.surveys),
        selectinload(Employee.alerts),
    ).where(
        Employee.id == employee_id,
        Employee.company_id == company_id
    )

    result = await session.execute(query)
    employee = result.scalar_one_or_none()

    if not employee:
        raise NotFoundError("Сотрудник")

    return employee


async def add_note(
    session: AsyncSession,
    *,
    employee_id: UUID,
    text: str,
    company_id: UUID,
    actor_user_id: UUID,
) -> Employee:
    """Добавляет заметку к сотруднику"""
    # Find employee
    query = select(Employee).where(
        Employee.id == employee_id,
        Employee.company_id == company_id
    )
    result = await session.execute(query)
    employee = result.scalar_one_or_none()

    if not employee:
        raise NotFoundError("Сотрудник")

    # Prepare new note
    new_note = {
        "text": text,
        "author_user_id": str(actor_user_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Add to existing notes
    current_notes = employee.notes if employee.notes else []
    current_notes.append(new_note)

    # Update notes field
    update_stmt = update(Employee).where(
        Employee.id == employee_id
    ).values(notes=current_notes)

    await session.execute(update_stmt)

    # Audit
    await audit(
        session,
        action="note_added",
        entity_type="employee",
        entity_id=employee_id,
        after={"note": text},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()

    # Reload employee to return updated data
    updated_result = await session.execute(
        select(Employee).options(
            selectinload(Employee.manager_user),
            selectinload(Employee.recruiter_user),
            selectinload(Employee.plan_items),
            selectinload(Employee.surveys),
            selectinload(Employee.alerts),
        ).where(Employee.id == employee_id)
    )
    return updated_result.scalar_one()