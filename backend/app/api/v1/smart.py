"""API умного подбора кандидатов"""

import asyncio
import logging
import types
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, Response
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
    SmartSkillSuggestItem,
    SmartRoleSuggestItem,
    SmartRoleCategory,
    SmartInviteRequest,
    SmartInviteResponse,
    SmartTakeRequest,
    SmartTakeResponse,
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
    suggest_skills,
    suggest_professional_roles,
    get_professional_role_categories,
    invite_selected,
    take_selected,
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
from ...models.smart_search import SmartSearchRun
from ...services.resume_export import build_resume_pdf, build_resume_docx
from ...schemas.auto_search import (
    AutoSearchItem,
    AutoAccessResponse,
    AutoCandidatesResponse,
    AutoBasisRequest,
    AutoEvaluateRequest,
    AutoRunStatus,
    AutoEvaluateResponse,
    AutoEvalToggleRequest,
    AutoTakeRequest,
    AutoTakeResponse,
)
from ...services.auto_search import (
    get_auto_access,
    sync_saved_searches,
    list_auto_searches,
    get_auto_candidates,
    set_basis,
    set_auto_eval,
    start_auto_evaluate,
    get_auto_run_status,
    take_auto_contact,
)

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
    """Получить предварительное количество резюме по фильтрам.

    Возвращает found (число резюме от hh) и debug_params (реальные hh-параметры
    запроса без page/per_page — видно какие фильтры реально ушли в hh).
    """
    found, debug_params = await preview_found_count(session, company_id, request)
    return SmartCountResponse(found=found, debug_params=debug_params)


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


@router.get("/skill-suggest", response_model=list[SmartSkillSuggestItem])
async def smart_skill_suggest(
    text: str = "",
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить подсказки навыков из справочника hh.ru (skill_set).

    Возвращает [{id, text}]. id можно передавать как skill_chips в запросе поиска
    для структурного фильтра skill= (режим exact).
    Требует минимум 2 символа; пустой/короткий text → [].
    """
    items = await suggest_skills(session, company_id, text)
    return [SmartSkillSuggestItem(id=i["id"], text=i["text"]) for i in items]


@router.get("/role-suggest", response_model=list[SmartRoleSuggestItem])
async def smart_role_suggest(
    text: str = "",
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить подсказки профессиональных ролей из справочника hh.ru.

    Справочник загружается один раз и кэшируется на уровне модуля.
    Пустой text или < 2 символов → [].
    """
    items = await suggest_professional_roles(session, company_id, text)
    return [
        SmartRoleSuggestItem(
            id=i["id"],
            name=i["name"],
            category=i.get("category"),
        )
        for i in items
    ]


@router.get("/role-categories", response_model=list[SmartRoleCategory])
async def smart_role_categories(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Получить сгруппированный справочник профессиональных ролей hh.ru.

    Возвращает список категорий (профобластей), каждая с вложенными ролями —
    для двухуровневой выпадашки: категория → роль.
    Справочник кэшируется на уровне модуля (тот же кэш, что у role-suggest).
    При ошибке (hh не подключён, недоступен) возвращает [].
    """
    items = await get_professional_role_categories(session, company_id)
    return [
        SmartRoleCategory(
            category_id=i["category_id"],
            category=i["category"],
            roles=[{"id": r["id"], "name": r["name"]} for r in i["roles"]],
        )
        for i in items
    ]


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


@router.post("/runs/{run_id}/take", response_model=SmartTakeResponse)
async def smart_take(
    run_id: UUID,
    request: SmartTakeRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Забрать выбранных кандидатов в базу компании без приглашения на hh.

    Открывает контакт hh (платно), создаёт Candidate (source='smart') + Application
    (stage='added', без negotiation) в воронке вакансии прогона.
    При дедупе (кандидат уже в базе) — привязывает существующего к воронке.
    Требует платного доступа к базе резюме hh.
    """
    # RBAC: manager запрещён (как у invite)
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    data = await take_selected(session, company_id, current_user.id, run_id, request.resume_ids)
    return SmartTakeResponse(**data)


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

    # Разрешаем при status in ('retrieved','done') (повторная оценка ок).
    # Если оценка уже идёт (status='running') — это конфликт конкуренции, а не
    # ошибка валидации: отдаём ConflictError (см. атомарный UPDATE ниже), чтобы
    # повторный вызов не маскировался как ValidationError до TOCTOU-флипа.
    if run.status == 'running':
        raise ConflictError("Оценка по этому прогону уже выполняется")
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


@router.get("/runs/{run_id}/candidates/{hh_resume_id}/resume")
async def export_smart_candidate_resume(
    run_id: UUID,
    hh_resume_id: str,
    format: str = Query("pdf", description="Формат: pdf или docx"),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Экспорт резюме кандидата из умного подбора (hh) с AI-разбором Глафиры.

    Рендерит данные из SmartSearchRun.scored_candidates (БД не пишет, hh не дёргает).
    RBAC: manager запрещён (как у invite/take).
    """
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")

    if format not in ["pdf", "docx"]:
        raise ValidationError("Допустимые форматы: pdf, docx")

    # Загружаем run company-scoped
    result = await session.execute(
        select(SmartSearchRun).where(
            SmartSearchRun.id == run_id,
            SmartSearchRun.company_id == company_id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundError("Поиск")

    # Ищем scored_candidate по hh_resume_id
    scored = None
    for c in (run.scored_candidates or []):
        if c.get("hh_resume_id") == hh_resume_id:
            scored = c
            break
    if scored is None:
        raise NotFoundError("Кандидат")

    # Разбираем сжатое резюме из scored_candidate
    resume_dict = scored.get("resume") or {}
    exp_list = resume_dict.get("experience") or []
    skills_list = resume_dict.get("skills") or []

    # Первая позиция как «желаемая должность»
    last_position = None
    if exp_list and isinstance(exp_list[0], dict):
        last_position = exp_list[0].get("position")

    # Формируем shim-объект (duck-typing, без ORM и без записи в БД)
    name_raw = scored.get("name") or ""
    name_tokens = name_raw.strip().split() if name_raw.strip() else []
    if not name_tokens or name_raw.strip().lower() in ("неизвестно", ""):
        first_name = ""
        last_name = "Кандидат"
    elif len(name_tokens) == 1:
        first_name = ""
        last_name = name_tokens[0]
    else:
        first_name = name_tokens[0]
        last_name = " ".join(name_tokens[1:])

    shim_experience = [
        types.SimpleNamespace(
            period=e.get("period", "") if isinstance(e, dict) else "",
            company=e.get("company", "") if isinstance(e, dict) else "",
            position=e.get("position", "") if isinstance(e, dict) else "",
            description=e.get("description", "") if isinstance(e, dict) else "",
        )
        for e in exp_list
    ]

    shim_skills = [
        types.SimpleNamespace(skill=s)
        for s in skills_list
        if isinstance(s, str)
    ]

    shim = types.SimpleNamespace(
        first_name=first_name,
        last_name=last_name,
        middle_name=None,
        gender=None,
        phone=None,
        email=None,
        city=scored.get("city"),
        region=None,
        last_position=last_position,
        salary_expectation=None,
        currency="RUB",
        extra={},
        resume_summary=None,
        experience=shim_experience,
        skills=shim_skills,
        education=[],
    )

    # AI-анализ из scored_candidate
    ai_analysis = {
        "score": scored.get("score"),
        "verdict": scored.get("verdict", ""),
        "summary": scored.get("summary", ""),
        "strengths": scored.get("strengths") or [],
        "risks": scored.get("risks") or [],
        "requirements_match": scored.get("requirements_match") or [],
        "forecast": scored.get("forecast", ""),
    }

    # Генерируем файл
    if format == "pdf":
        content = build_resume_pdf(shim, ai_analysis=ai_analysis)
        media_type = "application/pdf"
        extension = "pdf"
    else:
        content = build_resume_docx(shim, ai_analysis=ai_analysis)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"

    # Имя файла (ФИО или «Кандидат»), суффикс «_Глафира»
    display_name = " ".join(filter(None, [first_name, last_name])).strip() or "Кандидат"
    filename = f"{display_name}_Глафира.{extension}"

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
    }

    return Response(content=content, media_type=media_type, headers=headers)


# === АВТОПОДБОР (saved searches hh) ===

@router.get("/auto/access", response_model=AutoAccessResponse)
async def get_auto_search_access(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Доступ к Автоподбору (hh подключён + остаток пула)."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    data = await get_auto_access(session, company_id)
    return AutoAccessResponse(**data)


@router.get("/auto/searches", response_model=list[AutoSearchItem])
async def get_auto_searches(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Список сохранённых автопоисков hh. Свежий кэш (<1ч) отдаём без обращения к hh."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    cached = await list_auto_searches(session, company_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fresh = any(
        s.last_synced_at is not None and (now - s.last_synced_at) < timedelta(hours=1)
        for s in cached
    )
    if fresh:
        return cached
    try:
        return await sync_saved_searches(session, company_id)
    except Exception as e:
        if cached:
            logger.warning("[auto] sync failed, serving cache: %s", e)
            return cached
        raise


@router.post("/auto/searches/sync", response_model=list[AutoSearchItem])
async def sync_auto_searches(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Принудительная синхронизация автопоисков с hh."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    return await sync_saved_searches(session, company_id)


@router.get("/auto/searches/{auto_search_id}/candidates", response_model=AutoCandidatesResponse)
async def get_auto_search_candidates(
    auto_search_id: UUID,
    segment: str = Query("all"),
    page: int = Query(0, ge=0),
    sort: str = Query("updated"),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Кандидаты автопоиска на бесплатных полях hh (пагинация 10, сегмент Все/Новые)."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    if segment not in ("all", "new"):
        segment = "all"
    data = await get_auto_candidates(session, company_id, auto_search_id, segment=segment, page=page, sort=sort)
    return AutoCandidatesResponse(**data)


@router.post(
    "/auto/searches/{auto_search_id}/basis",
    response_model=AutoSearchItem,
    summary="Задать основу оценки автопоиска",
)
async def set_auto_basis(
    auto_search_id: UUID,
    request: AutoBasisRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Задать основу оценки (vacancy по company-scoped ID или prompt ≥3 символов)."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    basis = request.model_dump(mode="json", exclude_none=True)
    return await set_basis(session, company_id, auto_search_id, basis)


@router.patch(
    "/auto/searches/{auto_search_id}/auto-eval",
    response_model=AutoSearchItem,
    summary="Включить/выключить AI-оценку автопоиска",
)
async def patch_auto_eval(
    auto_search_id: UUID,
    request: AutoEvalToggleRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Включить/выключить флаг auto_eval для автопоиска."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    return await set_auto_eval(session, company_id, auto_search_id, request.enabled)


@router.post(
    "/auto/searches/{auto_search_id}/evaluate",
    response_model=AutoEvaluateResponse,
    summary="Запустить AI-оценку кандидатов автопоиска",
    status_code=202,
)
async def evaluate_auto_search(
    auto_search_id: UUID,
    request: AutoEvaluateRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Запустить фоновую AI-оценку кандидатов автопоиска по бесплатным полям hh."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    run_id = await start_auto_evaluate(
        session, company_id, auto_search_id, segment=request.segment, n=request.n
    )
    return AutoEvaluateResponse(run_id=run_id)


@router.get(
    "/auto/runs/{run_id}",
    response_model=AutoRunStatus,
    summary="Статус прогона AI-оценки автопоиска",
)
async def get_auto_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Поллинг статуса прогона AI-оценки автопоиска."""
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    run = await get_auto_run_status(session, company_id, run_id)
    return AutoRunStatus.model_validate(run)


@router.post(
    "/auto/searches/{auto_search_id}/take",
    response_model=AutoTakeResponse,
    summary="Забрать контакт / Перевести (ПЛАТНО открыть контакт hh)",
)
async def take_auto_search(
    auto_search_id: UUID,
    request: AutoTakeRequest,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Открыть контакт hh (ПЛАТНО) и создать кандидата:
    target='pool' → только в общую базу; target='vacancy' → + в воронку вакансии.

    Требует платного доступа к базе резюме hh. Дедуп не списывает контакт повторно.
    """
    if current_user.role == "manager":
        raise ForbiddenError("Доступ запрещён")
    data = await take_auto_contact(
        session,
        company_id,
        current_user.id,
        auto_search_id,
        request.resume_ids,
        target=request.target,
        vacancy_id=request.vacancy_id,
    )
    return AutoTakeResponse(**data)