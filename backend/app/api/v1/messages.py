from fastapi import APIRouter, Depends, Path
from uuid import UUID
from typing import Annotated

from sqlalchemy import select

from ...deps import get_current_user, get_current_company_id
from ...models import User, Candidate
from ...core.pagination import PageParams
from ...core.errors import ForbiddenError, NotFoundError
from ...core.permissions import can_manager_access_candidate
from ...database import get_db
from ...schemas.message import MessageOut, MessageCreate
from ...schemas.chat import MarkReadOut
from ...schemas.base import Paginated
from ...services.message import get_messages_paginated, send_message
from ...services.chats import mark_read, sync_candidate_hh_inbound
from ...services.integrations.telegram import service as tg_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def _ensure_candidate_in_company(
    session: AsyncSession, candidate_id: UUID, company_id: UUID
) -> None:
    """Кандидат существует в компании и не удалён — иначе 404 (company-изоляция)."""
    exists = await session.execute(
        select(Candidate.id).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
        )
    )
    if exists.scalar_one_or_none() is None:
        raise NotFoundError("Кандидат")


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


@router.post(
    "/candidates/{candidate_id}/messages/read",
    response_model=MarkReadOut,
    summary="Пометить диалог с кандидатом прочитанным (пер-юзер)",
)
async def mark_dialog_read(
    candidate_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
) -> MarkReadOut:
    """Сдвигает last_read_at ЭТОГО юзера по кандидату → его unread обнуляется.

    Пер-юзер: у других юзеров непрочитанные остаются. Зовётся попапом И вкладкой
    при открытии диалога. Не бизнес-действие (личная отметка) — audit не пишем.
    """
    # Менеджер: только кандидаты из своих вакансий.
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    await _ensure_candidate_in_company(session, candidate_id, company_id)

    await mark_read(
        session,
        company_id=company_id,
        user_id=current_user.id,
        candidate_id=candidate_id,
    )
    await session.commit()
    return MarkReadOut(ok=True, unread=0)


@router.post(
    "/candidates/{candidate_id}/messages/hh/sync",
    summary="Синхронизировать входящие hh-сообщения для кандидата (on-demand)",
)
async def sync_hh_messages(
    candidate_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Тянет новые входящие hh по всем откликам кандидата с hh_chat_id (зеркало
    telegram/sync). Дедуп по external_id (повторный вызов не плодит). Нет
    hh_chat_id → {"imported": 0} (не ошибка)."""
    # Менеджер: только кандидаты из своих вакансий.
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    await _ensure_candidate_in_company(session, candidate_id, company_id)

    result = await sync_candidate_hh_inbound(
        session, company_id=company_id, candidate_id=candidate_id, user_id=current_user.id
    )
    await session.commit()
    return result