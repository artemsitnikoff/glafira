from fastapi import APIRouter, Depends, Query, Path
from uuid import UUID

from sqlalchemy import select

from ...deps import get_current_user, get_current_company_id
from ...models import User, Candidate
from ...core.errors import ForbiddenError, NotFoundError
from ...core.permissions import can_manager_access_candidate
from ...database import get_db
from ...schemas.comment import CommentOut, CommentCreate
from ...services.comment import get_candidate_comments, create_comment
from ...services.integrations.hh.comments import sync_candidate_hh_comments
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


@router.get("/candidates/{candidate_id}/comments", response_model=list[CommentOut])
async def get_comments(
    candidate_id: UUID,
    application_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Менеджер: только кандидаты из своих вакансий
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    return await get_candidate_comments(session, candidate_id, company_id, application_id)


@router.post("/candidates/{candidate_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment_route(
    candidate_id: UUID,
    data: CommentCreate,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Менеджер: только кандидаты из своих вакансий
    if user.role == "manager":
        if not await can_manager_access_candidate(session, user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    result = await create_comment(session, candidate_id, data, company_id, user.id)
    await session.commit()
    return result


@router.post(
    "/candidates/{candidate_id}/comments/hh/sync",
    summary="Импортировать комментарии работодателя с hh для кандидата (on-demand)",
)
async def sync_hh_comments(
    candidate_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Тянет заметки работодателя к резюме кандидата с hh в блок «Комментарии»
    (source='hh', read-only). Дедуп по external_id (повторный вызов не плодит).
    Нет hh-резюме / нет токена / нет applicant_id → {"imported": 0} (не ошибка)."""
    # Менеджер: только кандидаты из своих вакансий (как в GET/POST comments).
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    await _ensure_candidate_in_company(session, candidate_id, company_id)

    result = await sync_candidate_hh_comments(
        session, company_id=company_id, candidate_id=candidate_id
    )
    await session.commit()
    return result