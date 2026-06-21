from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...deps import get_current_company_id, get_current_user
from ...models import User, Application
from ...core.errors import ForbiddenError, NotFoundError
from ...core.permissions import is_user_assigned_to_vacancy
from ...schemas.application import (
    ApplicationRow,
    BulkMoveRequest,
    BulkRejectRequest,
    BulkMoveResult,
    BulkRejectResult,
    MoveRequest,
    RejectRequest,
    StageActionResult,
    StageHistoryItem,
)
from ...schemas.base import Paginated
from ...services.application import (
    bulk_move_applications,
    bulk_reject_applications,
    get_application_history,
    get_applications_for_vacancy_paginated,
    move_application,
    reject_application,
    restore_application,
)

router = APIRouter()


async def _get_application_vacancy_id(
    session: AsyncSession,
    application_id: UUID,
    company_id: UUID,
) -> UUID:
    """Получить vacancy_id заявки (company-scoped). NotFoundError если не найдено."""
    result = await session.execute(
        select(Application.vacancy_id).where(
            Application.id == application_id,
            Application.company_id == company_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("Заявка не найдена")
    return row


@router.get(
    "/vacancies/{vacancy_id}/applications",
    response_model=Paginated[ApplicationRow],
)
async def get_applications_for_vacancy_funnel(
    vacancy_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    stage: str | None = Query(None),
    search: str | None = Query(None),
    score_min: int | None = Query(None),
    salary_max: int | None = Query(None),
    source: list[str] | None = Query(None),
    city: str | None = Query(None),
    messenger: list[str] | None = Query(None),
    ready_relocate: bool | None = Query(None),
    added_period: str | None = Query(None),
    repeat: bool | None = Query(None),
    tags: list[str] | None = Query(None),
    sort: str | None = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    candidate_id: UUID | None = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Check manager access to vacancy
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
        messenger=messenger,
        ready_relocate=ready_relocate,
        added_period=added_period,
        repeat=repeat,
        tags=tags,
        sort=sort,
        order=order,
        candidate_id=candidate_id,
    )


# Bulk endpoints are registered BEFORE /{application_id}/* so the path
# parameter does not capture the literal "bulk".
@router.post("/applications/bulk/move", response_model=BulkMoveResult)
async def bulk_move_applications_endpoint(
    move_data: BulkMoveRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Менеджер: проверить, что ВСЕ заявки принадлежат его вакансиям
    if current_user.role == "manager":
        for app_id in move_data.application_ids:
            vacancy_id = await _get_application_vacancy_id(session, app_id, company_id)
            if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
                raise ForbiddenError("Нет доступа к одной или нескольким заявкам")

    applications = await bulk_move_applications(
        session, move_data, company_id, current_user.id
    )
    await session.commit()
    return {"moved_count": len(applications)}


@router.post("/applications/bulk/reject", response_model=BulkRejectResult)
async def bulk_reject_applications_endpoint(
    reject_data: BulkRejectRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Менеджер: проверить, что ВСЕ заявки принадлежат его вакансиям
    if current_user.role == "manager":
        for app_id in reject_data.application_ids:
            vacancy_id = await _get_application_vacancy_id(session, app_id, company_id)
            if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
                raise ForbiddenError("Нет доступа к одной или нескольким заявкам")

    applications = await bulk_reject_applications(
        session, reject_data, company_id, current_user.id
    )
    await session.commit()
    return {
        "rejected_count": len(applications),
        "skipped_count": len(reject_data.application_ids) - len(applications),
    }


@router.post("/applications/{application_id}/move", response_model=StageActionResult)
async def move_application_endpoint(
    application_id: UUID,
    move_data: MoveRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Менеджер: только заявки из своих вакансий
    if current_user.role == "manager":
        vacancy_id = await _get_application_vacancy_id(session, application_id, company_id)
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной заявке")

    application = await move_application(
        session, application_id, move_data, company_id, current_user.id
    )
    await session.commit()
    return {"new_stage": application.stage}


@router.post("/applications/{application_id}/reject", response_model=StageActionResult)
async def reject_application_endpoint(
    application_id: UUID,
    reject_data: RejectRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Менеджер: только заявки из своих вакансий
    if current_user.role == "manager":
        vacancy_id = await _get_application_vacancy_id(session, application_id, company_id)
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной заявке")

    application = await reject_application(
        session, application_id, reject_data, company_id, current_user.id
    )
    await session.commit()
    return {"new_stage": application.stage}


@router.post("/applications/{application_id}/restore", response_model=StageActionResult)
async def restore_application_endpoint(
    application_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Менеджер: только заявки из своих вакансий
    if current_user.role == "manager":
        vacancy_id = await _get_application_vacancy_id(session, application_id, company_id)
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной заявке")

    application = await restore_application(
        session, application_id, company_id, current_user.id
    )
    await session.commit()
    return {"new_stage": application.stage}


@router.get(
    "/applications/{application_id}/history",
    response_model=list[StageHistoryItem],
)
async def get_application_stage_history(
    application_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Менеджер: только заявки из своих вакансий
    if current_user.role == "manager":
        vacancy_id = await _get_application_vacancy_id(session, application_id, company_id)
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной заявке")

    return await get_application_history(session, application_id, company_id)
