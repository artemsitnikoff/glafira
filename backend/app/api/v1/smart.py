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
    SmartVacancyFilters,
    SmartCountRequest,
    SmartCountResponse,
    SmartAreaSuggestItem,
    SmartInviteRequest,
    SmartInviteResponse
)
from ...schemas.base_search import (
    BaseSearchRequest,
    BaseSearchResponse,
    BaseSearchRunResponse,
    BaseSearchCountResponse,
    MarkAddedRequest,
    BaseSearchCriteria,
    BaseSearchCandidate
)
from ...services.smart_search import (
    check_access,
    get_smart_vacancies,
    start_search,
    get_run_status,
    get_run_history,
    derive_vacancy_filters,
    preview_found_count,
    suggest_areas,
    invite_selected
)
from ...services.base_search import (
    parse_query_to_criteria,
    search_base,
    search_by_vacancy,
    create_search_run,
    increment_added_to_funnel,
    get_search_runs,
    get_candidates_count
)
from ...core.errors import NotFoundError, ForbiddenError, ValidationError

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

    # Преобразуем scored_candidates в список объектов
    scored_candidates = []
    for candidate_data in getattr(run, 'scored_candidates', []) or []:
        scored_candidates.append(InvitedCandidate(**candidate_data))

    return SmartRunStatus(
        id=run.id,
        status=run.status,
        stage=run.stage,
        found=run.found,
        scan_n=(run.params or {}).get('scan_n', 0),
        scanned=run.scanned,
        evaluated=run.evaluated,
        invited=run.invited,
        error=run.error,
        invites_skipped=getattr(run, 'invites_skipped', False),
        invited_candidates=invited_candidates,
        scored_candidates=scored_candidates,
        passed_threshold=getattr(run, 'passed_threshold', 0),
        note=getattr(run, 'note', None),
        log=getattr(run, 'log', [])
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
            # Прошедшие порог — живой счёт по scored_candidates (passed_threshold бывает 0
            # у старых/недофинализированных прогонов).
            passed=sum(1 for c in (run.scored_candidates or []) if c.get('passed')),
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


@router.post("/preview-count", response_model=SmartCountResponse)
async def smart_preview_count(
    request: SmartCountRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить предварительное количество резюме по фильтрам"""
    found = await preview_found_count(session, company_id, request)
    return SmartCountResponse(found=found)


@router.get("/area-suggest", response_model=list[SmartAreaSuggestItem])
async def smart_area_suggest(
    text: str = "",
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить подсказки регионов/городов из справочника hh.ru"""
    items = await suggest_areas(session, company_id, text)
    return [SmartAreaSuggestItem(id=str(i.get("id")), text=str(i.get("text", "")))
            for i in items if i.get("id")]


@router.post("/runs/{run_id}/invite", response_model=SmartInviteResponse)
async def smart_invite(
    run_id: UUID,
    request: SmartInviteRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Отправить приглашения выбранным кандидатам"""
    data = await invite_selected(session, company_id, current_user.id, run_id, request.resume_ids)
    return SmartInviteResponse(**data)


# === ПОИСК ПО СОБСТВЕННОЙ БАЗЕ ===

@router.post("/base/search", response_model=BaseSearchResponse)
async def base_search_candidates(
    request: BaseSearchRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Поиск кандидатов в собственной базе"""
    # RBAC: manager запрещён
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    # Дополнительная валидация запроса
    if request.search_type == "prompt" and (not request.query or len(request.query.strip()) < 3):
        raise ValidationError("Для поиска по запросу нужно минимум 3 символа")

    if request.search_type == "vacancy" and not request.vacancy_id:
        raise ValidationError("Для поиска по вакансии нужно указать vacancy_id")

    if request.search_type == "prompt":
        # Парсим запрос через LLM
        criteria = await parse_query_to_criteria(request.query)

        # Выполняем поиск
        search_result = await search_base(
            session,
            company_id,
            role=criteria.get("role", ""),
            skills=criteria.get("skills", []),
            city=criteria.get("city", ""),
            salary_from=criteria.get("salary_from"),
            salary_to=criteria.get("salary_to")
        )

        query_echo = request.query
        vacancy_title = None

    elif request.search_type == "vacancy":
        # Поиск по критериям вакансии
        search_result = await search_by_vacancy(session, company_id, request.vacancy_id)
        criteria = search_result.pop("criteria")
        query_echo = search_result.pop("vacancy_title")
        vacancy_title = query_echo

    else:
        raise ValidationError("Неверный тип поиска")

    # Создаём запись истории
    search_run = await create_search_run(
        session,
        company_id,
        request.search_type,
        query_echo,
        request.vacancy_id,
        search_result["total"]
    )
    await session.commit()

    return BaseSearchResponse(
        found=len(search_result["results"]),
        total=search_result["total"],
        results=[BaseSearchCandidate(**candidate) for candidate in search_result["results"]],
        criteria=BaseSearchCriteria(**criteria),
        query_echo=query_echo,
        vacancy_title=vacancy_title,
        run_id=search_run.id
    )


@router.get("/base/runs", response_model=list[BaseSearchRunResponse])
async def get_base_search_runs(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """История поиска по собственной базе"""
    # RBAC: manager запрещён
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    runs = await get_search_runs(session, company_id)
    return [BaseSearchRunResponse.model_validate(run) for run in runs]


@router.get("/base/count", response_model=BaseSearchCountResponse)
async def get_base_candidates_count(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Количество кандидатов в собственной базе"""
    # RBAC: manager запрещён
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    count = await get_candidates_count(session, company_id)
    return BaseSearchCountResponse(count=count)


@router.post("/base/runs/{run_id}/mark-added", status_code=204)
async def mark_candidate_added_to_funnel(
    run_id: UUID,
    request: MarkAddedRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Отметить добавление кандидата в воронку"""
    # RBAC: manager запрещён
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    await increment_added_to_funnel(session, company_id, run_id)
    await session.commit()