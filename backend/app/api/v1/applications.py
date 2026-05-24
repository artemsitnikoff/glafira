from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...schemas.application import (
    ApplicationRow,
    MoveRequest,
    RejectRequest,
    BulkMoveRequest,
    BulkRejectRequest,
    StageHistoryItem
)
from ...schemas.base import Paginated
from ...services.application import (
    get_applications_for_vacancy_paginated,
    move_application,
    reject_application,
    restore_application,
    bulk_move_applications,
    bulk_reject_applications,
    get_application_history,
)
from ...models import User

router = APIRouter()


@router.get("/vacancies/{vacancy_id}/applications", response_model=Paginated[ApplicationRow])
async def get_applications_for_vacancy_funnel(
    vacancy_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    stage: str | None = Query(None),
    search: str | None = Query(None),
    score_min: int | None = Query(None),
    salary_max: int | None = Query(None),
    source: str | None = Query(None),
    city: str | None = Query(None),
    sort: str | None = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    return await get_applications_for_vacancy_paginated(
        session,
        vacancy_id,
        company_id,
        page=page,
        page_size=page_size,
        stage=stage,
        search=search,
        score_min=score_min,
        salary_max=salary_max,
        source=source,
        city=city,
        sort=sort,
        order=order
    )


@router.post("/applications/{application_id}/move", response_model=dict)
async def move_application_to_stage(
    application_id: UUID,
    move_data: MoveRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Move application to another stage"""
    application = await move_application(
        session,
        application_id,
        move_data,
        company_id,
        current_user.id
    )
    await session.commit()

    return {"message": "Application moved successfully", "new_stage": application.stage}


@router.post("/applications/{application_id}/reject", response_model=dict)
async def reject_application_by_id(
    application_id: UUID,
    reject_data: RejectRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Reject application"""
    application = await reject_application(
        session,
        application_id,
        reject_data,
        company_id,
        current_user.id
    )
    await session.commit()

    return {"message": "Application rejected successfully"}


@router.post("/applications/{application_id}/restore", response_model=dict)
async def restore_application_by_id(
    application_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Restore application from rejected state"""
    application = await restore_application(
        session,
        application_id,
        company_id,
        current_user.id
    )
    await session.commit()

    return {"message": "Application restored successfully", "new_stage": application.stage}


@router.post("/applications/bulk/move", response_model=dict)
async def bulk_move_applications_to_stage(
    move_data: BulkMoveRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Move multiple applications to a stage"""
    applications = await bulk_move_applications(
        session,
        move_data,
        company_id,
        current_user.id
    )
    await session.commit()

    return {
        "message": f"Successfully moved {len(applications)} applications",
        "moved_count": len(applications)
    }


@router.post("/applications/bulk/reject", response_model=dict)
async def bulk_reject_applications_by_ids(
    reject_data: BulkRejectRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Reject multiple applications"""
    applications = await bulk_reject_applications(
        session,
        reject_data,
        company_id,
        current_user.id
    )
    await session.commit()

    return {
        "message": f"Successfully rejected {len(applications)} applications",
        "rejected_count": len(applications)
    }


@router.get("/applications/{application_id}/history", response_model=list[StageHistoryItem])
async def get_application_stage_history(
    application_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get stage history for application"""
    return await get_application_history(session, application_id, company_id)