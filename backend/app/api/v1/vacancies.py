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
    VacancyStageCount,
    VacancyStageCreate,
    VacancyStageUpdate,
    VacancyStageReorder
)
from ...schemas.base import Paginated
from ...schemas.settings import RejectReasonOut, RejectReasonCreate, RejectReasonUpdate
from ...services.settings.reject_reasons import (
    ensure_vacancy_reject_reasons,
    create_reject_reason,
    update_reject_reason,
    delete_reject_reason,
)
from ...services.vacancy import (
    get_vacancies,
    get_vacancy,
    create_vacancy,
    update_vacancy,
    archive_vacancy,
    get_vacancy_sidebar,
    get_vacancy_stages,
    add_vacancy_stage,
    rename_vacancy_stage,
    delete_vacancy_stage,
    reorder_vacancy_stages
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

    # Build response - field validator handles team conversion automatically
    data = VacancyDetail.model_validate(vacancy)

    # Set client name manually as it's computed
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

    # Build response - field validator handles team conversion automatically
    data = VacancyDetail.model_validate(vacancy)

    # Set client name manually as it's computed
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

    # Build response - field validator handles team conversion automatically
    data = VacancyDetail.model_validate(vacancy)

    # Set client name manually as it's computed
    data.client_name = vacancy.client.name if vacancy.client else None

    return data


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

    # Build response - field validator handles team conversion automatically
    data = VacancyDetail.model_validate(vacancy)

    # Set client name manually as it's computed
    data.client_name = vacancy.client.name if vacancy.client else None

    return data


@router.get("/{vacancy_id}/stages", response_model=list[VacancyStageCount])
async def get_vacancy_stages_with_counts(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get vacancy stages with application counts"""
    return await get_vacancy_stages(session, vacancy_id, company_id)


@router.post("/{vacancy_id}/stages", status_code=201)
async def add_stage_to_vacancy(
    vacancy_id: UUID,
    stage_data: VacancyStageCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Add new stage to vacancy"""
    await add_vacancy_stage(session, vacancy_id, stage_data, company_id, current_user.id)
    await session.commit()
    return {"message": "Этап создан"}


@router.patch("/{vacancy_id}/stages/{stage_key}")
async def rename_stage(
    vacancy_id: UUID,
    stage_key: str,
    stage_data: VacancyStageUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Rename stage (update only label)"""
    await rename_vacancy_stage(session, vacancy_id, stage_key, stage_data, company_id, current_user.id)
    await session.commit()
    return {"message": "Этап переименован"}


@router.delete("/{vacancy_id}/stages/{stage_key}", status_code=204)
async def delete_stage_from_vacancy(
    vacancy_id: UUID,
    stage_key: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Delete stage (only if not protected and empty)"""
    await delete_vacancy_stage(session, vacancy_id, stage_key, company_id, current_user.id)
    await session.commit()


@router.put("/{vacancy_id}/stages/reorder")
async def reorder_stages(
    vacancy_id: UUID,
    reorder_data: VacancyStageReorder,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Reorder stages"""
    await reorder_vacancy_stages(session, vacancy_id, reorder_data, company_id, current_user.id)
    await session.commit()
    return {"message": "Этапы переупорядочены"}


# ---- Причины отказа, привязанные к вакансии ----

@router.get("/{vacancy_id}/reject-reasons", response_model=list[RejectReasonOut])
async def get_vacancy_reject_reasons(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Причины отказа вакансии. Если их нет — копируются из дефолтов компании (инвариант непустоты)."""
    await get_vacancy(session, vacancy_id, company_id)  # проверка владения (NotFound при чужой/несущ.)
    reasons = await ensure_vacancy_reject_reasons(session, company_id, vacancy_id)
    out = [RejectReasonOut.model_validate(r) for r in reasons]  # собрать ДО commit (greenlet)
    await session.commit()
    return out


@router.post("/{vacancy_id}/reject-reasons", response_model=RejectReasonOut, status_code=201)
async def add_vacancy_reject_reason(
    vacancy_id: UUID,
    data: RejectReasonCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Добавить причину отказа в вакансию"""
    await get_vacancy(session, vacancy_id, company_id)
    reason = await create_reject_reason(session, company_id, data, current_user.id, vacancy_id=vacancy_id)
    out = RejectReasonOut.model_validate(reason)
    await session.commit()
    return out


@router.patch("/{vacancy_id}/reject-reasons/{reason_id}", response_model=RejectReasonOut)
async def update_vacancy_reject_reason(
    vacancy_id: UUID,
    reason_id: UUID,
    data: RejectReasonUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Переименовать причину отказа вакансии"""
    await get_vacancy(session, vacancy_id, company_id)
    reason = await update_reject_reason(session, reason_id, company_id, data, current_user.id, vacancy_id=vacancy_id)
    out = RejectReasonOut.model_validate(reason)
    await session.commit()
    return out


@router.delete("/{vacancy_id}/reject-reasons/{reason_id}", status_code=204)
async def delete_vacancy_reject_reason(
    vacancy_id: UUID,
    reason_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Удалить причину отказа вакансии (системную нельзя)"""
    await get_vacancy(session, vacancy_id, company_id)
    await delete_reject_reason(session, reason_id, company_id, current_user.id, vacancy_id=vacancy_id)
    await session.commit()