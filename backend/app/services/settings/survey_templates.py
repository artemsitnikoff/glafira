from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from ...models import SurveyTemplate
from ...core.errors import NotFoundError, ValidationError
from ...services.audit import audit


async def list_survey_templates(session: AsyncSession, company_id: UUID) -> list[SurveyTemplate]:
    """List survey templates for company"""
    result = await session.execute(
        select(SurveyTemplate)
        .where(SurveyTemplate.company_id == company_id)
        .order_by(SurveyTemplate.name)
    )
    return list(result.scalars().all())


async def get_survey_template(session: AsyncSession, template_id: UUID, company_id: UUID) -> SurveyTemplate:
    """Get survey template by ID"""
    result = await session.execute(
        select(SurveyTemplate)
        .where(SurveyTemplate.id == template_id)
        .where(SurveyTemplate.company_id == company_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise NotFoundError("Шаблон опроса")

    return template


async def create_survey_template(
    session: AsyncSession, company_id: UUID, data, actor_user_id: UUID
) -> SurveyTemplate:
    """Create new survey template"""
    if not data.name or not data.name.strip():
        raise ValidationError("name не может быть пустым")

    if not data.questions:
        raise ValidationError("questions не может быть пустым")

    if not data.channels:
        raise ValidationError("channels не может быть пустым")

    template = SurveyTemplate(
        company_id=company_id,
        name=data.name.strip(),
        trigger_day=data.trigger_day,
        interval_days=data.interval_days,
        channels=data.channels,
        questions=data.questions,
        is_enabled=data.is_enabled if data.is_enabled is not None else True,
    )

    session.add(template)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="create_survey_template",
        entity_type="survey_template",
        entity_id=template.id,
        after={
            "name": template.name,
            "trigger_day": template.trigger_day,
            "interval_days": template.interval_days,
            "is_enabled": template.is_enabled,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return template


async def update_survey_template(
    session: AsyncSession, template_id: UUID, company_id: UUID, data, actor_user_id: UUID
) -> SurveyTemplate:
    """Update survey template"""
    template = await get_survey_template(session, template_id, company_id)

    # Store original values for audit
    before = {
        "name": template.name,
        "trigger_day": template.trigger_day,
        "interval_days": template.interval_days,
        "channels": template.channels,
        "questions": template.questions,
        "is_enabled": template.is_enabled,
    }

    # Update fields
    if data.name is not None:
        if not data.name.strip():
            raise ValidationError("name не может быть пустым")
        template.name = data.name.strip()

    if data.trigger_day is not None:
        template.trigger_day = data.trigger_day

    if data.interval_days is not None:
        template.interval_days = data.interval_days

    if data.channels is not None:
        if not data.channels:
            raise ValidationError("channels не может быть пустым")
        template.channels = data.channels

    if data.questions is not None:
        if not data.questions:
            raise ValidationError("questions не может быть пустым")
        template.questions = data.questions

    if data.is_enabled is not None:
        template.is_enabled = data.is_enabled

    await session.flush()

    # Audit log
    after = {
        "name": template.name,
        "trigger_day": template.trigger_day,
        "interval_days": template.interval_days,
        "channels": template.channels,
        "questions": template.questions,
        "is_enabled": template.is_enabled,
    }

    await audit(
        session,
        action="update_survey_template",
        entity_type="survey_template",
        entity_id=template.id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return template