"""Сервис для управления опросами пульса"""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...models import Employee, PulseSurvey
from ...schemas.pulse import SurveyCreate
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