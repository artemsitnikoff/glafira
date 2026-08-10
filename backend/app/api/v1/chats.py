"""Роутер модуля «Чаты» (фаза 2) — АГРЕГАТЫ поверх единой ленты сообщений.

Тонкий слой: валидация роли → вызов сервиса `services/chats.py` → схема.
Лента и отправка сообщений живут в messages_router (`GET/POST
/candidates/{id}/messages`) — здесь их НЕТ (единый источник, без дублей).
Роутер монтируется под `_deny_hm` (hiring_manager → 403); роль `manager` видит
только свои вакансии (manager_user_id, как в home/messages).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.errors import ForbiddenError, NotFoundError
from ...core.permissions import can_manager_access_candidate
from ...database import get_db
from ...deps import get_current_company_id, get_current_user
from ...models import User
from ...schemas.chat import ChatDialogOut, ChatMetaOut, ChatReadAllOut, ChatUnreadTotal
from ...services.chats import (
    get_candidate_chat_meta,
    list_dialogs,
    mark_all_read,
    total_unread,
)

router = APIRouter()


@router.get("/dialogs", response_model=list[ChatDialogOut])
async def get_dialogs(
    q: str | None = Query(default=None, description="Поиск по имени кандидата / названию вакансии"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Список диалогов для попапа сайдбара (диалог = кандидат, пер-юзер unread)."""
    manager_user_id = current_user.id if current_user.role == "manager" else None
    return await list_dialogs(
        session,
        company_id=company_id,
        user_id=current_user.id,
        manager_user_id=manager_user_id,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-total", response_model=ChatUnreadTotal)
async def get_unread_total(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Суммарно непрочитанных для бейджа сайдбара (лёгкий поллинг, пер-юзер)."""
    manager_user_id = current_user.id if current_user.role == "manager" else None
    total = await total_unread(
        session,
        company_id=company_id,
        user_id=current_user.id,
        manager_user_id=manager_user_id,
    )
    return ChatUnreadTotal(total=total)


@router.post("/read-all", response_model=ChatReadAllOut)
async def read_all(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """«Прочитать всё»: разом пометить прочитанными ВСЕ диалоги текущего юзера.

    Один bulk-upsert MessageRead (сервис mark_all_read, без цикла). Пер-юзер: не
    трогает чужие ReadState. Роль manager — только кандидаты своих вакансий. Это
    личная отметка прочтения (как mark_read), не бизнес-действие → audit не пишем.
    """
    manager_user_id = current_user.id if current_user.role == "manager" else None
    marked = await mark_all_read(
        session,
        company_id=company_id,
        user_id=current_user.id,
        manager_user_id=manager_user_id,
    )
    await session.commit()
    return ChatReadAllOut(ok=True, marked=marked)


@router.get("/candidate/{candidate_id}/meta", response_model=ChatMetaOut)
async def get_candidate_meta(
    candidate_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Мета доступных каналов кандидата для композера/шапки чата (обоих UI)."""
    # Менеджер: только кандидаты из своих вакансий.
    if current_user.role == "manager":
        if not await can_manager_access_candidate(
            session, current_user.id, candidate_id, company_id
        ):
            raise ForbiddenError("Нет доступа к данному кандидату")

    meta = await get_candidate_chat_meta(
        session, company_id=company_id, candidate_id=candidate_id
    )
    if meta is None:
        raise NotFoundError("Кандидат")
    return meta
