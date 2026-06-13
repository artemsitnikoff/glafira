"""API умного подбора кандидатов"""

import asyncio
import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

logger = logging.getLogger(__name__)

from ...database import get_db, AsyncSessionLocal
from ...deps import get_current_user, get_current_company_id
from ...models import User, BaseSearchRun
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
    BaseSearchRetrieveResponse,
    BaseEvaluateRequest,
    BaseSearchRunResponse,
    BaseSearchRunStatus,
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
    increment_added_to_funnel,
    get_search_runs,
    get_candidates_count,
    reindex_all_embeddings,
    get_embeddings_index_status,
    retrieve_base,
    _run_base_evaluate,
    _active_tasks,
    get_base_search_run_status,
    GLAFIRA_MAX_EVALUATE
)
from ...core.errors import NotFoundError, ForbiddenError, ValidationError, ConflictError

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

@router.post("/base/search", response_model=BaseSearchRetrieveResponse)
async def base_search_candidates(
    request: BaseSearchRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Поиск кандидатов в собственной базе (фаза RETRIEVE - синхронно)"""
    # RBAC: manager запрещён
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    # Дополнительная валидация запроса
    if request.search_type == "prompt" and (not request.query or len(request.query.strip()) < 3):
        raise ValidationError("Для поиска по запросу нужно минимум 3 символа")

    if request.search_type == "vacancy" and not request.vacancy_id:
        raise ValidationError("Для поиска по вакансии нужно указать vacancy_id")

    # Определяем override критерии (если фронт прислал отредактированные автофильтры)
    override = None
    if request.search_type == "vacancy" and request.role is not None:
        override = {
            "role": request.role,
            "skills": request.skills or [],
            "city": request.city or "",
            "salary_from": request.salary_from,
            "salary_to": request.salary_to,
        }

    # Запускаем синхронный retrieve
    result = await retrieve_base(
        session,
        company_id,
        request.search_type,
        request.query or "",
        request.vacancy_id,
        override
    )

    return BaseSearchRetrieveResponse(
        run_id=result["run_id"],
        total=result["total"]
    )


@router.get("/base/runs/{run_id}", response_model=BaseSearchRunStatus)
async def get_base_search_run_status_endpoint(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить статус выполнения поиска по базе"""
    # RBAC: manager запрещён
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    run = await get_base_search_run_status(session, run_id, company_id)
    if not run:
        raise NotFoundError("Поиск")

    # Формируем результаты
    results = []
    for result_data in (run.results or []):
        results.append(BaseSearchCandidate(**result_data))

    criteria = None
    if run.criteria:
        criteria = BaseSearchCriteria(**run.criteria)

    return BaseSearchRunStatus(
        id=run.id,
        status=run.status,
        stage=run.stage,
        found=run.found,
        to_evaluate=run.to_evaluate,
        evaluated=run.evaluated,
        results=results,
        criteria=criteria,
        query_echo=run.query_echo,
        vacancy_title=run.vacancy_title,
        error=run.error
    )


@router.post("/base/runs/{run_id}/evaluate", response_model=BaseSearchResponse)
async def evaluate_base_search_candidates(
    run_id: UUID,
    request: BaseEvaluateRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Запуск фазы EVALUATE: AI-оценка топ-N кандидатов (асинхронно)"""
    # RBAC: manager запрещён
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    # Загружаем run (company-scoped)
    run = await get_base_search_run_status(session, run_id, company_id)
    if not run:
        raise NotFoundError("Поиск")

    # Разрешаем при status in ('retrieved','done') (повторная оценка ок)
    if run.status not in ('retrieved', 'done'):
        raise ValidationError("Поиск должен быть в статусе 'retrieved' или 'done'")

    # Предохранитель расхода: N ≤ максимума (косинус по всей базе вернёт ≤ доступного).
    n = min(request.evaluate_n, GLAFIRA_MAX_EVALUATE)
    if request.evaluate_n > GLAFIRA_MAX_EVALUATE:
        logger.info(f"[base] evaluate_n {request.evaluate_n} урезан до максимума {GLAFIRA_MAX_EVALUATE}")

    # ФИКС TOCTOU: атомарный conditional UPDATE на сессии запроса + commit. Коммит
    # делает флип видимым фоновой задаче (она откроет свой AsyncSessionLocal). Отдельная
    # сессия тут не нужна (и ломала бы изоляцию в тестах — конкурентные операции).
    result = await session.execute(
        update(BaseSearchRun)
        .where(
            BaseSearchRun.id == run_id,
            BaseSearchRun.company_id == company_id,
            BaseSearchRun.status.in_(['retrieved', 'done']),
        )
        .values(status='running', stage='rerank', to_evaluate=n, evaluated=0)
        .returning(BaseSearchRun.id)
    )
    flipped = result.first()
    await session.commit()

    if flipped is None:
        raise ConflictError("Оценка по этому прогону уже выполняется")

    # Спавн async-задачи
    task = asyncio.create_task(_run_base_evaluate(run_id, company_id, n))
    _active_tasks.add(task)
    task.add_done_callback(lambda t: _active_tasks.discard(t))

    return BaseSearchResponse(run_id=run_id)


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


@router.post("/base/reindex", status_code=202)
async def start_embeddings_reindex(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Запустить переиндексацию эмбеддингов для семантического поиска"""
    # RBAC: только admin
    if current_user.role != "admin":
        raise ForbiddenError("Доступ запрещён")

    # Запускаем фоновую задачу переиндексации
    await reindex_all_embeddings(company_id)

    return {"message": "Переиндексация запущена"}


@router.get("/base/index-status")
async def get_embeddings_index_status_endpoint(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить статус индексации эмбеддингов"""
    # RBAC: admin/recruiter (как основной поиск)
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    status = await get_embeddings_index_status(session, company_id)

    # Добавляем процент готовности
    if status["total_candidates"] > 0:
        status["progress_percent"] = round(
            (status["indexed_candidates"] / status["total_candidates"]) * 100
        )
    else:
        status["progress_percent"] = 100

    return status