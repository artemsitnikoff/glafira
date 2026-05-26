from fastapi import APIRouter, Depends, Query
from uuid import UUID
from typing import Annotated

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...core.pagination import PageParams
from ...database import get_db
from ...schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateDetail,
    CandidateGridItem,
    ApplicationHistoryItem,
    AddTagRequest
)
from ...schemas.base import Paginated, StatusResult
from ...services.candidate import (
    get_candidates_paginated,
    get_candidate_detail,
    create_candidate,
    update_candidate,
    delete_candidate,
    get_candidate_applications,
    add_candidate_tag,
    remove_candidate_tag
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=Paginated[CandidateGridItem])
async def get_candidates(
    page_params: Annotated[PageParams, Depends()],
    search: str | None = Query(None),
    city: str | None = Query(None),
    exp: int | None = Query(None),
    score_min: int | None = Query(None),
    score_max: int | None = Query(None),
    source: str | None = Query(None),
    vacancy_id: UUID | None = Query(None),
    stage: str | None = Query(None),
    tags: list[UUID] | None = Query(None),
    added_period: str | None = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    return await get_candidates_paginated(
        session=session,
        company_id=company_id,
        page=page_params.page,
        page_size=page_params.page_size,
        search=search,
        city=city,
        exp=exp,
        score_min=score_min,
        score_max=score_max,
        source=source,
        vacancy_id=vacancy_id,
        stage=stage,
        tags=tags,
        added_period=added_period,
        sort=page_params.sort,
        order=page_params.order
    )


@router.get("/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(
    candidate_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    return await get_candidate_detail(session, candidate_id, company_id)


@router.post("", response_model=CandidateDetail, status_code=201)
async def create_candidate_route(
    data: CandidateCreate,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    result = await create_candidate(session, data, company_id, user.id)
    await session.commit()
    return result


@router.patch("/{candidate_id}", response_model=CandidateDetail)
async def update_candidate_route(
    candidate_id: UUID,
    data: CandidateUpdate,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    result = await update_candidate(session, candidate_id, data, company_id, user.id)
    await session.commit()
    return result


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate_route(
    candidate_id: UUID,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    await delete_candidate(session, candidate_id, company_id, user.id)
    await session.commit()


@router.get("/{candidate_id}/applications", response_model=list[ApplicationHistoryItem])
async def get_candidate_applications_route(
    candidate_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    return await get_candidate_applications(session, candidate_id, company_id)


@router.post("/{candidate_id}/tags", status_code=201, response_model=StatusResult)
async def add_candidate_tag_route(
    candidate_id: UUID,
    data: AddTagRequest,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    await add_candidate_tag(session, candidate_id, data.tag_id, company_id, user.id)
    await session.commit()
    return {"status": "success"}


@router.delete("/{candidate_id}/tags/{tag_id}", status_code=204)
async def remove_candidate_tag_route(
    candidate_id: UUID,
    tag_id: UUID,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    await remove_candidate_tag(session, candidate_id, tag_id, company_id, user.id)
    await session.commit()