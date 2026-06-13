from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...schemas.base import MessageResult
from ...schemas.settings import (
    MessageTemplateOut,
    MessageTemplateCreate,
    MessageTemplateUpdate,
)
from ...services.settings import message_templates
from ...core.permissions import require_recruiter_or_admin

router = APIRouter()


@router.get("", response_model=list[MessageTemplateOut])
async def list_message_templates(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Список всех шаблонов сообщений компании."""
    templates = await message_templates.list_message_templates(session, company_id)
    return [MessageTemplateOut.model_validate(template) for template in templates]


@router.post("", response_model=MessageTemplateOut, status_code=201, dependencies=[Depends(require_recruiter_or_admin)])
async def create_message_template(
    data: MessageTemplateCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Создать шаблон сообщения."""
    template = await message_templates.create_message_template(
        session,
        company_id,
        current_user.id,
        name=data.name,
        body=data.body,
        order_index=data.order_index,
    )
    await session.commit()
    return MessageTemplateOut.model_validate(template)


@router.patch("/{template_id}", response_model=MessageTemplateOut, dependencies=[Depends(require_recruiter_or_admin)])
async def update_message_template(
    template_id: UUID,
    data: MessageTemplateUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Обновить шаблон сообщения."""
    template = await message_templates.update_message_template(
        session,
        company_id,
        current_user.id,
        template_id,
        name=data.name,
        body=data.body,
        order_index=data.order_index,
    )
    await session.commit()
    return MessageTemplateOut.model_validate(template)


@router.delete("/{template_id}", response_model=MessageResult, dependencies=[Depends(require_recruiter_or_admin)])
async def delete_message_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Удалить шаблон сообщения."""
    await message_templates.delete_message_template(
        session,
        company_id,
        current_user.id,
        template_id,
    )
    await session.commit()
    return {"message": "Шаблон сообщения удалён"}