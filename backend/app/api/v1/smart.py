"""API умного подбора кандидатов"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...schemas.smart import (
    SmartAccessResponse,
    SmartVacancyItem,
    SmartSearchRequest,
    SmartSearchResponse,
    SmartRunStatus,
    SmartRunHistoryItem,
    InvitedCandidate,
    SmartVacancyFilters
)
from ...services.smart_search import (
    check_access,
    get_smart_vacancies,
    start_search,
    get_run_status,
    get_run_history,
    derive_vacancy_filters
)
from ...core.errors import NotFoundError

router = APIRouter()


@router.get("/access", response_model=SmartAccessResponse)
async def get_smart_access(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Проверка доступа к умному подбору"""
    has_access, has_paid_access, reason = await check_access(session, company_id)
    return SmartAccessResponse(
        has_access=has_access,
        has_paid_access=has_paid_access,
        reason=reason
    )


@router.get("/vacancies", response_model=list[SmartVacancyItem])
async def get_smart_vacancies_list(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить список активных вакансий с предзаполненными фильтрами"""
    return await get_smart_vacancies(session, company_id)


@router.post("/search", response_model=SmartSearchResponse)
async def start_smart_search(
    request: SmartSearchRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Запустить умный поиск кандидатов"""
    run_id = await start_search(session, company_id, current_user.id, request)
    return SmartSearchResponse(run_id=run_id)


@router.get("/runs/{run_id}", response_model=SmartRunStatus)
async def get_smart_run_status(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить статус выполнения умного поиска"""
    run = await get_run_status(session, run_id, company_id)
    if not run:
        raise NotFoundError("Поиск")

    # Преобразуем invited_candidates в список объектов
    invited_candidates = []
    for candidate_data in run.invited_candidates or []:
        invited_candidates.append(InvitedCandidate(**candidate_data))

    return SmartRunStatus(
        id=run.id,
        status=run.status,
        stage=run.stage,
        found=run.found,
        scanned=run.scanned,
        evaluated=run.evaluated,
        invited=run.invited,
        error=run.error,
        invites_skipped=getattr(run, 'invites_skipped', False),
        invited_candidates=invited_candidates
    )


@router.get("/runs", response_model=list[SmartRunHistoryItem])
async def get_smart_runs_history(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить историю умных поисков"""
    runs = await get_run_history(session, company_id)

    history = []
    for run in runs:
        history.append(SmartRunHistoryItem(
            id=run.id,
            vacancy_id=run.vacancy_id,
            vacancy_title=run.vacancy.name if run.vacancy else "Удаленная вакансия",
            created_at=run.created_at,
            found=run.found,
            evaluated=run.evaluated,
            invited=run.invited
        ))

    return history


@router.get("/vacancy-filters/{vacancy_id}", response_model=SmartVacancyFilters)
async def get_vacancy_filters(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить AI-фильтры для умного подбора по вакансии"""
    filters = await derive_vacancy_filters(session, company_id, vacancy_id)
    return SmartVacancyFilters(**filters)