from fastapi import APIRouter, Depends, Query, Path
from uuid import UUID

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...database import get_db
from ...schemas.comment import CommentOut, CommentCreate
from ...services.comment import get_candidate_comments, create_comment
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/candidates/{candidate_id}/comments", response_model=list[CommentOut])
async def get_comments(
    candidate_id: UUID,
    application_id: UUID | None = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    return await get_candidate_comments(session, candidate_id, company_id, application_id)


@router.post("/candidates/{candidate_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment_route(
    candidate_id: UUID,
    data: CommentCreate,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    result = await create_comment(session, candidate_id, data, company_id, user.id)
    await session.commit()
    return result