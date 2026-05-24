from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...schemas.vacancy import (
    VacancyDetail,
    VacancyCreate,
    VacancyUpdate,
    VacancyArchive,
    VacancySidebar,
    VacancyStageCount
)
from ...schemas.base import Paginated
from ...services.vacancy import (
    get_vacancies,
    get_vacancy,
    create_vacancy,
    update_vacancy,
    archive_vacancy,
    get_vacancy_sidebar,
    get_vacancy_stages
)
from ...models import User

router = APIRouter()


@router.get("/sidebar", response_model=VacancySidebar)
async def get_sidebar_data(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get sidebar data with counts"""
    return await get_vacancy_sidebar(session, company_id)


@router.get("", response_model=Paginated[VacancyDetail])
async def list_vacancies(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    sort: str | None = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get list of vacancies with pagination"""
    from ...services.vacancy import get_vacancies_paginated
    result = await get_vacancies_paginated(
        session, company_id, page, page_size, status, search, sort, order
    )
    return result


@router.get("/{vacancy_id}", response_model=VacancyDetail)
async def get_vacancy_by_id(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get vacancy by ID"""
    vacancy = await get_vacancy(session, vacancy_id, company_id)

    # Convert team and responsible user to UserShort format
    from ...schemas.user import UserShort

    # Build team list
    team = []
    for team_member in vacancy.team:
        team.append(UserShort.model_validate(team_member.user))

    # Build response
    data = VacancyDetail.model_validate(vacancy)
    data.team = team
    if vacancy.responsible_user:
        data.responsible_user = UserShort.model_validate(vacancy.responsible_user)

    # Add client name if exists
    data.client_name = vacancy.client.name if vacancy.client else None

    return data


@router.post("", response_model=VacancyDetail, status_code=201)
async def create_new_vacancy(
    vacancy_data: VacancyCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Create new vacancy"""
    vacancy = await create_vacancy(session, vacancy_data, company_id, current_user.id)
    await session.commit()

    # Reload with joins to get full data
    from ...services.vacancy import get_vacancy
    vacancy = await get_vacancy(session, vacancy.id, company_id)

    # Convert to VacancyDetail schema with all required fields
    from ...schemas.user import UserShort

    # Build team list
    team = []
    for team_member in vacancy.team:
        team.append(UserShort.model_validate(team_member.user))

    # Build response
    data = VacancyDetail.model_validate(vacancy)
    data.team = team
    if vacancy.responsible_user:
        data.responsible_user = UserShort.model_validate(vacancy.responsible_user)

    # Add client name if exists
    data.client_name = vacancy.client.name if vacancy.client else None

    return data


@router.patch("/{vacancy_id}", response_model=VacancyDetail)
async def update_vacancy_by_id(
    vacancy_id: UUID,
    vacancy_data: VacancyUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Update vacancy"""
    vacancy = await update_vacancy(session, vacancy_id, vacancy_data, company_id, current_user.id)
    await session.commit()

    return VacancyDetail.model_validate(vacancy)


@router.post("/{vacancy_id}/archive", response_model=VacancyDetail)
async def archive_vacancy_by_id(
    vacancy_id: UUID,
    archive_data: VacancyArchive,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Archive vacancy"""
    vacancy = await archive_vacancy(session, vacancy_id, archive_data, company_id, current_user.id)
    await session.commit()

    return VacancyDetail.model_validate(vacancy)


@router.get("/{vacancy_id}/stages", response_model=list[VacancyStageCount])
async def get_vacancy_stages_with_counts(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get vacancy stages with application counts"""
    return await get_vacancy_stages(session, vacancy_id, company_id)