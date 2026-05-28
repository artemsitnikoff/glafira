"""Сервис для управления опросами пульса"""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...models import Employee, PulseSurvey
from ...schemas.pulse import SurveyCreate, BulkRunSurveyRequest, BulkRunSurveyResult
from ...core.errors import NotFoundError
from ...services.audit import audit


async def list_employee_surveys(
    session: AsyncSession,
    employee_id: UUID,
    company_id: UUID,
) -> list[PulseSurvey]:
    """Получает список опросов сотрудника"""

    # Verify employee exists and belongs to company
    employee_query = select(Employee).where(
        Employee.id == employee_id,
        Employee.company_id == company_id
    )
    employee_result = await session.execute(employee_query)
    employee = employee_result.scalar_one_or_none()

    if not employee:
        raise NotFoundError("Сотрудник")

    # Get surveys
    query = select(PulseSurvey).where(
        PulseSurvey.employee_id == employee_id,
        PulseSurvey.company_id == company_id
    ).order_by(PulseSurvey.sent_at.desc())

    result = await session.execute(query)
    return result.scalars().all()


async def submit_employee_survey(
    session: AsyncSession,
    employee_id: UUID,
    data: SurveyCreate,
    company_id: UUID,
    actor_user_id: UUID,
) -> PulseSurvey:
    """Создает новый опрос для сотрудника"""

    # Verify employee exists and belongs to company
    employee_query = select(Employee).where(
        Employee.id == employee_id,
        Employee.company_id == company_id
    )
    employee_result = await session.execute(employee_query)
    employee = employee_result.scalar_one_or_none()

    if not employee:
        raise NotFoundError("Сотрудник")

    # Create survey
    survey = PulseSurvey(
        company_id=company_id,
        employee_id=employee_id,
        type=data.type,
        template_key=data.template_key,
        sent_at=datetime.now(timezone.utc),
        answers=[],
    )

    session.add(survey)
    await session.flush()

    # Audit
    await audit(
        session,
        action="survey_created",
        entity_type="pulse_survey",
        entity_id=survey.id,
        after={"type": data.type, "employee_id": str(employee_id)},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return survey


async def bulk_run_survey(
    session: AsyncSession,
    data: BulkRunSurveyRequest,
    company_id: UUID,
    actor_user_id: UUID,
) -> BulkRunSurveyResult:
    """Atomic bulk survey creation for multiple employees"""

    # First, validate all employee IDs exist and belong to company in one query
    if not data.employee_ids:
        return BulkRunSurveyResult(launched_count=0)

    employees_query = select(Employee).where(
        Employee.id.in_(data.employee_ids),
        Employee.company_id == company_id
    )
    employees_result = await session.execute(employees_query)
    found_employees = employees_result.scalars().all()

    # Check if all requested employees were found
    found_employee_ids = {emp.id for emp in found_employees}
    requested_employee_ids = set(data.employee_ids)

    if found_employee_ids != requested_employee_ids:
        missing_ids = requested_employee_ids - found_employee_ids
        raise NotFoundError(f"Сотрудники с ID {list(missing_ids)} не найдены")

    # Now create surveys for all validated employees
    send_at = data.send_at or datetime.now(timezone.utc)
    launched_count = 0

    for employee in found_employees:
        # Create survey
        survey = PulseSurvey(
            company_id=company_id,
            employee_id=employee.id,
            type="weekly",  # Default type for bulk surveys
            template_key=data.template_key,
            sent_at=send_at,
            answers=[],
        )
        session.add(survey)
        launched_count += 1

        # Create audit entry for each survey
        await audit(
            session,
            action="survey_run",
            entity_type="pulse_survey",
            entity_id=survey.id,
            after={
                "template_key": data.template_key,
                "employee_id": str(employee.id),
                "bulk_operation": True,
            },
            actor_user_id=actor_user_id,
            company_id=company_id,
        )

    await session.flush()

    return BulkRunSurveyResult(launched_count=launched_count)