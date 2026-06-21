from fastapi import APIRouter, Depends, Path
from uuid import UUID
from typing import Annotated

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...core.pagination import PageParams
from ...core.errors import ForbiddenError
from ...core.permissions import can_manager_access_candidate
from ...database import get_db
from ...schemas.message import MessageOut, MessageCreate
from ...schemas.base import Paginated
from ...services.message import get_messages_paginated, send_message
from ...services.integrations.telegram import service as tg_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/candidates/{candidate_id}/messages", response_model=Paginated[MessageOut])
async def get_messages(
    candidate_id: UUID = Path(...),
    page_params: Annotated[PageParams, Depends(PageParams)] = ...,
    channel: str | None = None,
    application_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Менеджер: только кандидаты из своих вакансий
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    return await get_messages_paginated(
        session=session,
        candidate_id=candidate_id,
        company_id=company_id,
        page=page_params.page,
        page_size=page_params.page_size,
        channel=channel,
        application_id=application_id
    )


@router.post("/candidates/{candidate_id}/messages", response_model=MessageOut, status_code=201)
async def send_message_route(
    candidate_id: UUID = Path(...),
    data: MessageCreate = ...,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Менеджер: только кандидаты из своих вакансий
    if user.role == "manager":
        if not await can_manager_access_candidate(session, user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    result = await send_message(session, candidate_id, data, company_id, user.id)
    await session.commit()
    return result


@router.post(
    "/candidates/{candidate_id}/messages/telegram/sync",
    summary="Синхронизировать входящие Telegram-сообщения для кандидата",
)
async def sync_telegram_messages(
    candidate_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Импортирует входящие Telegram-сообщения от конкретного кандидата.

    Возвращает {"imported": int, "connected": bool}.
    Если интеграция не подключена — {"imported": 0, "connected": false} (без ошибки).
    Идемпотентен: повторный вызов с теми же данными вернёт imported=0 (дедуп).
    """
    # Менеджер: только кандидаты из своих вакансий
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    result = await tg_service.sync_inbound(
        session,
        company_id,
        candidate_id=candidate_id,
    )
    await session.commit()
    return result