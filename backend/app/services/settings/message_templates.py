"""CRUD шаблонов сообщений компании.

Общие быстрые шаблоны сообщений для чата.
Создание/правка/удаление — admin+recruiter; чтение — все роли.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import MessageTemplate
from ...core.errors import ValidationError, NotFoundError
from ..audit import audit


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Название шаблона обязательно")
    if len(name) > 200:
        raise ValidationError("Название шаблона — не больше 200 символов")
    return name


def _clean_body(body: str) -> str:
    body = (body or "").strip()
    if not body:
        raise ValidationError("Текст шаблона обязателен")
    if len(body) > 5000:
        raise ValidationError("Текст шаблона — не больше 5000 символов")
    return body


async def _get(session: AsyncSession, template_id: UUID, company_id: UUID) -> MessageTemplate:
    template = (
        await session.execute(
            select(MessageTemplate).where(
                MessageTemplate.id == template_id,
                MessageTemplate.company_id == company_id
            )
        )
    ).scalar_one_or_none()
    if not template:
        raise NotFoundError("Шаблон сообщения")
    return template


async def list_message_templates(session: AsyncSession, company_id: UUID) -> list[MessageTemplate]:
    """Все шаблоны сообщений компании."""
    result = await session.execute(
        select(MessageTemplate)
        .where(MessageTemplate.company_id == company_id)
        .order_by(MessageTemplate.order_index, MessageTemplate.created_at)
    )
    return result.scalars().all()


async def create_message_template(
    session: AsyncSession,
    company_id: UUID,
    actor_user_id: UUID,
    *,
    name: str,
    body: str,
    order_index: int = 0
) -> MessageTemplate:
    name = _clean_name(name)
    body = _clean_body(body)

    template = MessageTemplate(
        company_id=company_id,
        name=name,
        body=body,
        order_index=order_index
    )
    session.add(template)
    await session.flush()
    await session.refresh(template)

    await audit(
        session,
        action="create_message_template",
        entity_type="message_template",
        entity_id=template.id,
        after={"name": name, "body": body, "order_index": order_index},
        actor_user_id=actor_user_id,
        actor_type="human",
        company_id=company_id,
    )
    return template


async def update_message_template(
    session: AsyncSession,
    company_id: UUID,
    actor_user_id: UUID,
    template_id: UUID,
    *,
    name: str | None = None,
    body: str | None = None,
    order_index: int | None = None,
) -> MessageTemplate:
    template = await _get(session, template_id, company_id)
    before = {"name": template.name, "body": template.body, "order_index": template.order_index}

    if name is not None:
        template.name = _clean_name(name)
    if body is not None:
        template.body = _clean_body(body)
    if order_index is not None:
        template.order_index = order_index

    await session.flush()
    await session.refresh(template)

    await audit(
        session,
        action="update_message_template",
        entity_type="message_template",
        entity_id=template.id,
        before=before,
        after={"name": template.name, "body": template.body, "order_index": template.order_index},
        actor_user_id=actor_user_id,
        actor_type="human",
        company_id=company_id,
    )
    return template


async def delete_message_template(
    session: AsyncSession,
    company_id: UUID,
    actor_user_id: UUID,
    template_id: UUID,
) -> None:
    template = await _get(session, template_id, company_id)
    before = {"name": template.name, "body": template.body, "order_index": template.order_index}

    await session.delete(template)
    await session.flush()

    await audit(
        session,
        action="delete_message_template",
        entity_type="message_template",
        entity_id=template_id,
        before=before,
        actor_user_id=actor_user_id,
        actor_type="human",
        company_id=company_id,
    )