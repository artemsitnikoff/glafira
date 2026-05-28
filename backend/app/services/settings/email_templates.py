from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from ...models import EmailTemplate
from ...core.errors import NotFoundError, ValidationError
from ...services.audit import audit


async def list_email_templates(session: AsyncSession, company_id: UUID) -> list[EmailTemplate]:
    """List email templates for company"""
    result = await session.execute(
        select(EmailTemplate)
        .where(EmailTemplate.company_id == company_id)
        .order_by(EmailTemplate.name)
    )
    return list(result.scalars().all())


async def get_email_template(session: AsyncSession, template_id: UUID, company_id: UUID) -> EmailTemplate:
    """Get email template by ID"""
    result = await session.execute(
        select(EmailTemplate)
        .where(EmailTemplate.id == template_id)
        .where(EmailTemplate.company_id == company_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise NotFoundError("Шаблон письма")

    return template


async def create_email_template(
    session: AsyncSession, company_id: UUID, data, actor_user_id: UUID
) -> EmailTemplate:
    """Create new email template"""
    if not data.name or not data.name.strip():
        raise ValidationError("name не может быть пустым")

    if not data.event_type or not data.event_type.strip():
        raise ValidationError("event_type не может быть пустым")

    if not data.subject or not data.subject.strip():
        raise ValidationError("subject не может быть пустым")

    if not data.body or not data.body.strip():
        raise ValidationError("body не может быть пустым")

    template = EmailTemplate(
        company_id=company_id,
        name=data.name.strip(),
        event_type=data.event_type.strip(),
        subject=data.subject.strip(),
        body=data.body.strip(),
        is_enabled=data.is_enabled if data.is_enabled is not None else True,
    )

    session.add(template)
    await session.flush()
    await session.refresh(template)

    # Audit log
    await audit(
        session,
        action="create_email_template",
        entity_type="email_template",
        entity_id=template.id,
        after={
            "name": template.name,
            "event_type": template.event_type,
            "subject": template.subject,
            "is_enabled": template.is_enabled,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return template


async def update_email_template(
    session: AsyncSession, template_id: UUID, company_id: UUID, data, actor_user_id: UUID
) -> EmailTemplate:
    """Update email template"""
    template = await get_email_template(session, template_id, company_id)

    # Store original values for audit
    before = {
        "name": template.name,
        "event_type": template.event_type,
        "subject": template.subject,
        "body": template.body,
        "is_enabled": template.is_enabled,
    }

    # Update fields
    if data.name is not None:
        if not data.name.strip():
            raise ValidationError("name не может быть пустым")
        template.name = data.name.strip()

    if data.event_type is not None:
        if not data.event_type.strip():
            raise ValidationError("event_type не может быть пустым")
        template.event_type = data.event_type.strip()

    if data.subject is not None:
        if not data.subject.strip():
            raise ValidationError("subject не может быть пустым")
        template.subject = data.subject.strip()

    if data.body is not None:
        if not data.body.strip():
            raise ValidationError("body не может быть пустым")
        template.body = data.body.strip()

    if data.is_enabled is not None:
        template.is_enabled = data.is_enabled

    await session.flush()
    await session.refresh(template)

    # Audit log
    after = {
        "name": template.name,
        "event_type": template.event_type,
        "subject": template.subject,
        "body": template.body,
        "is_enabled": template.is_enabled,
    }

    await audit(
        session,
        action="update_email_template",
        entity_type="email_template",
        entity_id=template.id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return template


async def delete_email_template(
    session: AsyncSession, template_id: UUID, company_id: UUID, actor_user_id: UUID
) -> None:
    """Delete email template"""
    template = await get_email_template(session, template_id, company_id)

    # Store original values for audit
    before = {
        "name": template.name,
        "event_type": template.event_type,
        "is_enabled": template.is_enabled,
    }

    # Hard delete
    await session.delete(template)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="email_template_delete",
        entity_type="email_template",
        entity_id=template_id,
        before=before,
        after=None,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )