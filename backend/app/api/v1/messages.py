from fastapi import APIRouter, Depends, Query
from uuid import UUID
from typing import Annotated

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...core.pagination import PageParams
from ...database import get_db
from ...schemas.message import MessageOut, MessageCreate
from ...schemas.base import Paginated
from ...services.message import get_messages_paginated, send_message
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=Paginated[MessageOut])
async def get_messages(
    page_params: Annotated[PageParams, Depends()],
    candidate_id: UUID = Query(...),
    channel: str | None = Query(None),
    application_id: UUID | None = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    return await get_messages_paginated(
        session=session,
        candidate_id=candidate_id,
        company_id=company_id,
        page=page_params.page,
        page_size=page_params.page_size,
        channel=channel,
        application_id=application_id
    )


@router.post("", response_model=MessageOut, status_code=201)
async def send_message_route(
    data: MessageCreate,
    candidate_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    result = await send_message(session, candidate_id, data, company_id, user.id)
    await session.commit()
    return result