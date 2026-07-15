import asyncio
import logging
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

logger = logging.getLogger(__name__)

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...core.errors import ForbiddenError, ValidationError
from ...core.permissions import is_user_assigned_to_vacancy
from ...services.integrations.hh import service as hh_service
from ...schemas.vacancy import (
    VacancyDetail,
    ArchivedVacancyItem,
    VacancyCreate,
    VacancyUpdate,
    VacancyArchive,
    VacancySidebar,
    VacancyStageCount,
    VacancyStageCreate,
    VacancyStageUpdate,
    VacancyStageReorder,
    ParseVacancyResponse,
    GenerateRubricRequest,
    GenerateRubricResponse,
)
from ...schemas.base import Paginated
from ...schemas.settings import RejectReasonOut, RejectReasonCreate, RejectReasonUpdate
from ...services.settings.reject_reasons import (
    ensure_vacancy_reject_reasons,
    create_reject_reason,
    update_reject_reason,
    delete_reject_reason,
)
from ...services.settings.glafira import get_company_openrouter_key, get_company_llm_model
from ...services.glafira.vacancy_parse import parse_vacancy_to_dict
from ...services.glafira.scoring_rubric import generate_scoring_rubric
from ...services.glafira.scoring import _strip_html
from ...services.vacancy import (
    get_vacancy,
    create_vacancy,
    update_vacancy,
    archive_vacancy,
    duplicate_vacancy,
    get_vacancy_sidebar,
    get_archived_vacancies,
    get_vacancy_stages,
    add_vacancy_stage,
    rename_vacancy_stage,
    delete_vacancy_stage,
    reorder_vacancy_stages
)
from ...models import User

router = APIRouter()


@router.post("/parse-file", response_model=ParseVacancyResponse)
async def parse_vacancy_file_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Parse vacancy description file and return structured fields for form (PDF, DOCX, TXT).
    Does NOT create a vacancy — only returns extracted fields."""
    # RBAC: manager forbidden
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут парсить файлы вакансий")

    content = await file.read()
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    if len(content) > MAX_FILE_SIZE:
        return ParseVacancyResponse(
            parsed=False,
            reason="Размер файла превышает 10 МБ",
            fields={},
        )

    # OpenRouter ключ компании (кидает OpenRouterNotConfiguredError → глобальный хендлер → 400)
    api_key = await get_company_openrouter_key(session, company_id)

    parsed_data = await parse_vacancy_to_dict(content, file.filename or "unknown", api_key)
    if parsed_data is None:
        return ParseVacancyResponse(
            parsed=False,
            reason="Формат не поддержан или текст не распознан (PDF, DOCX, TXT)",
            fields={},
        )

    return ParseVacancyResponse(
        parsed=True,
        reason=None,
        fields=parsed_data,
    )


@router.post("/generate-rubric", response_model=GenerateRubricResponse)
async def generate_rubric_endpoint(
    body: GenerateRubricRequest,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Генерирует взвешенный рубрикатор критериев оценки из полей вакансии (stateless).
    Описание должно быть непустым. Возвращает текст для поля recruiter_scoring_instructions."""
    # RBAC: manager forbidden
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут генерировать рубрикатор")

    # Снимаем HTML-теги ПЕРЕД проверкой пустоты (RichTextField шлёт '<p><br></p>' и т.п.)
    desc_stripped = _strip_html(body.description or "").strip()
    logger.info(
        "[generate-rubric] company=%s name_len=%d desc_raw_len=%d desc_stripped_len=%d",
        company_id, len(body.name or ""), len(body.description or ""), len(desc_stripped),
    )
    if not desc_stripped:
        logger.info("[generate-rubric] company=%s → generated=false: пустое описание", company_id)
        return GenerateRubricResponse(
            generated=False,
            reason="Заполните описание вакансии",
            rubric=None,
        )

    # OpenRouter ключ + модель компании (кидает OpenRouterNotConfiguredError → глобальный хендлер → 400)
    api_key = await get_company_openrouter_key(session, company_id)
    company_model = await get_company_llm_model(session, company_id)
    logger.info("[generate-rubric] company=%s model=%s", company_id, company_model)

    vacancy_fields = {
        "name": body.name,
        "description": body.description,
        "city": body.city,
        "department": body.department,
        "employment_type": body.employment_type,
        "salary_from": body.salary_from,
        "salary_to": body.salary_to,
    }

    # Таймаут < nginx proxy_read_timeout (~60с): иначе шлюз отдаёт 504 вместо ответа.
    try:
        rubric = await asyncio.wait_for(
            generate_scoring_rubric(vacancy_fields, api_key, model=company_model),
            timeout=50,
        )
    except asyncio.TimeoutError:
        logger.warning("[generate-rubric] company=%s → таймаут 50с (модель %s медленная)", company_id, company_model)
        return GenerateRubricResponse(
            generated=False,
            reason="Глафира не успела составить критерии — модель долго отвечает. Попробуйте ещё раз или выберите более быструю модель в Настройки → AI.",
            rubric=None,
        )
    if rubric is None:
        logger.warning("[generate-rubric] company=%s → generated=false: generate_scoring_rubric вернул None", company_id)
        return GenerateRubricResponse(
            generated=False,
            reason="Не удалось сгенерировать рубрикатор (ошибка LLM)",
            rubric=None,
        )

    logger.info("[generate-rubric] company=%s → generated=true (rubric_len=%d)", company_id, len(rubric))
    return GenerateRubricResponse(
        generated=True,
        reason=None,
        rubric=rubric,
    )


@router.get("/sidebar", response_model=VacancySidebar)
async def get_sidebar_data(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get sidebar data with counts"""
    return await get_vacancy_sidebar(session, company_id, current_user.role, current_user.id)


@router.get("/archived", response_model=list[ArchivedVacancyItem])
async def get_archived_vacancies_list(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Архивные вакансии с агрегатами (кандидаты/нанято) — для страницы Архив."""
    return await get_archived_vacancies(session, company_id, current_user.role, current_user.id)


@router.get("", response_model=Paginated[VacancyDetail])
async def list_vacancies(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    sort: str | None = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get list of vacancies with pagination"""
    from ...services.vacancy import get_vacancies_paginated
    result = await get_vacancies_paginated(
        session, company_id, page, page_size, status, search, sort, order,
        current_user.role, current_user.id
    )
    return result


@router.get("/{vacancy_id}", response_model=VacancyDetail)
async def get_vacancy_by_id(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get vacancy by ID"""
    vacancy = await get_vacancy(session, vacancy_id, company_id)

    # Check manager access
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Check manager access
    if current_user.role == "manager":
        raise ForbiddenError("Менеджеры не могут создавать вакансии")

    # Заказчик обязателен: его название Глафира называет кандидату во всех сообщениях.
    # ⚠️ Валидация ТОЛЬКО здесь (в HTTP-роуте), НЕ в схеме и НЕ в БД: импорт вакансий с
    # hh зовёт create_vacancy напрямую, без клиента, и ломаться не должен; старые
    # вакансии без заказчика работают через фолбэк на компанию-арендатора.
    if vacancy_data.client_id is None:
        raise ValidationError("Укажите заказчика вакансии — его название Глафира называет кандидату.")

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


@router.post("/{vacancy_id}/duplicate", response_model=VacancyDetail, status_code=201)
async def duplicate_vacancy_by_id(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Дублировать вакансию (копия полей+этапов+причин+команды, без заявок)."""
    if current_user.role == "manager":
        raise ForbiddenError("Менеджеры не могут создавать вакансии")

    new_vacancy = await duplicate_vacancy(session, vacancy_id, company_id, current_user.id)
    await session.commit()

    vacancy = await get_vacancy(session, new_vacancy.id, company_id)
    data = VacancyDetail.model_validate(vacancy)
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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

    # Заказчика нельзя снять в None ЯВНЫМ PATCH (см. create). Поле НЕ прислано —
    # не трогаем: старые вакансии без заказчика продолжают редактироваться.
    if 'client_id' in vacancy_data.model_fields_set and vacancy_data.client_id is None:
        raise ValidationError("Укажите заказчика вакансии — его название Глафира называет кандидату.")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get vacancy stages with application counts"""
    # Check manager access
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

    await reorder_vacancy_stages(session, vacancy_id, reorder_data, company_id, current_user.id)
    await session.commit()
    return {"message": "Этапы переупорядочены"}


# ---- Причины отказа, привязанные к вакансии ----

@router.get("/{vacancy_id}/reject-reasons", response_model=list[RejectReasonOut])
async def get_vacancy_reject_reasons(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Причины отказа вакансии. Если их нет — копируются из дефолтов компании (инвариант непустоты)."""
    # Check manager access
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

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
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

    await get_vacancy(session, vacancy_id, company_id)
    await delete_reject_reason(session, reason_id, company_id, current_user.id, vacancy_id=vacancy_id)
    await session.commit()


# ---- Интеграция с hh.ru ----

from pydantic import BaseModel

class HhVacancyLinkRequest(BaseModel):
    hh_vacancy_id: str

@router.post("/{vacancy_id}/hh/link")
async def link_vacancy_to_hh(
    vacancy_id: UUID,
    data: HhVacancyLinkRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Привязать вакансию Глафиры к вакансии hh.ru"""
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

    await hh_service.link_vacancy(
        session, vacancy_id, data.hh_vacancy_id, company_id, current_user.id
    )
    await session.commit()

    return {"message": "Вакансия привязана к hh.ru"}


@router.delete("/{vacancy_id}/hh/link")
async def unlink_vacancy_from_hh(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Отвязать вакансию Глафиры от hh.ru"""
    # Менеджер: только свои вакансии
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

    await hh_service.unlink_vacancy(session, vacancy_id, company_id, current_user.id)
    await session.commit()

    return {"message": "Вакансия отвязана от hh.ru"}


@router.post("/{vacancy_id}/hh/publish")
async def publish_vacancy_to_hh(
    vacancy_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """
    Опубликовать вакансию Глафиры на hh.ru

    ⚠️  НЕ проверено без реального токена hh.ru
    ⚠️  Требует маппинга города → hh area_id (TODO)
    """
    # Менеджер: только свои вакансии (платное действие!)
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(session, current_user.id, vacancy_id, company_id):
            raise ForbiddenError("Нет доступа к данной вакансии")

    hh_vacancy_id = await hh_service.publish_vacancy_to_hh(
        session, vacancy_id, company_id, current_user.id
    )
    await session.commit()

    return {"hh_vacancy_id": hh_vacancy_id}