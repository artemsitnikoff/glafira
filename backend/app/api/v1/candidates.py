from fastapi import APIRouter, Depends, Query, Response, File, UploadFile
from uuid import UUID
from typing import Annotated
from urllib.parse import quote

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...core.pagination import PageParams
from ...core.errors import ForbiddenError, ValidationError
from ...core.permissions import can_manager_access_candidate
from ...database import get_db
from ...schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateDetail,
    CandidateGridItem,
    ApplicationHistoryItem,
    AddTagRequest,
    AssignToVacancyRequest,
    ParseResumeResponse,
    DuplicateCheckResponse
)
from ...schemas.base import Paginated, StatusResult
from ...schemas.application import ApplicationRow
from ...services.candidate import (
    get_candidates_paginated,
    get_candidate_detail,
    create_candidate,
    update_candidate,
    delete_candidate,
    get_candidate_applications,
    add_candidate_tag,
    remove_candidate_tag,
    assign_candidate_to_vacancy,
    check_candidate_duplicates
)
from ...services.resume_export import (
    load_candidate_for_export,
    build_resume_pdf,
    build_resume_docx,
    _full_name
)
from ...services.glafira.resume_parse import parse_resume_to_dict
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
    vacancy_id: str | None = Query(None),
    stage: str | None = Query(None),
    tags: str | None = Query(None),
    added_period: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Managers cannot access general candidate pool
    if current_user.role == "manager":
        raise ForbiddenError("Менеджеры не имеют доступа к общей базе кандидатов")

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


# ВАЖНО: статический роут /check-duplicate ОБЯЗАН быть объявлен ДО динамического
# /{candidate_id} — иначе FastAPI матчит "check-duplicate" как candidate_id (UUID) → 422,
# и эндпоинт недостижим. Порядок объявления = порядок матчинга.
@router.get("/check-duplicate", response_model=DuplicateCheckResponse)
async def check_candidate_duplicate(
    phone: str | None = Query(None),
    email: str | None = Query(None),
    first_name: str | None = Query(None),
    last_name: str | None = Query(None),
    middle_name: str | None = Query(None),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
) -> DuplicateCheckResponse:
    """Проверка дубликатов кандидата по контактным данным"""
    # Managers cannot create candidates, so they can't check duplicates
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут создавать кандидатов")

    # Если нет ни телефона, ни email - возвращаем пустой результат
    if not phone and not email:
        return DuplicateCheckResponse(found=False, match_count=0, matches=[])

    return await check_candidate_duplicates(
        session, company_id, phone, email, first_name, last_name, middle_name
    )


@router.get("/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Check manager access to candidate
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    return await get_candidate_detail(session, candidate_id, company_id)


@router.post("/parse-resume", response_model=ParseResumeResponse)
async def parse_resume_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Parse resume file and return structured data for form"""
    # RBAC: manager forbidden
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут парсить резюме")

    # Validate file size (same as documents)
    content = await file.read()
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    if len(content) > MAX_FILE_SIZE:
        return ParseResumeResponse(
            parsed=False,
            reason="Размер файла превышает 10 МБ",
            fields={}
        )

    # Parse resume
    try:
        parsed_data = await parse_resume_to_dict(content, file.filename or "unknown")
        if parsed_data is None:
            return ParseResumeResponse(
                parsed=False,
                reason="Формат не поддержан или текст не распознан (поддерживаются PDF, DOCX, TXT)",
                fields={}
            )

        return ParseResumeResponse(
            parsed=True,
            reason=None,
            fields=parsed_data
        )
    except Exception:
        return ParseResumeResponse(
            parsed=False,
            reason="Ошибка при обработке файла",
            fields={}
        )


@router.post("", response_model=CandidateDetail, status_code=201)
async def create_candidate_route(
    data: CandidateCreate,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Managers cannot create candidates
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут создавать кандидатов")

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
    # Менеджеры не редактируют данные кандидата (как и не создают — см. POST выше)
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут редактировать кандидатов")

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
    # Менеджеры не удаляют кандидатов
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут удалять кандидатов")

    await delete_candidate(session, candidate_id, company_id, user.id)
    await session.commit()


@router.get("/{candidate_id}/applications", response_model=list[ApplicationHistoryItem])
async def get_candidate_applications_route(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Check manager access to candidate
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    return await get_candidate_applications(session, candidate_id, company_id)


@router.post("/{candidate_id}/tags", status_code=201, response_model=StatusResult)
async def add_candidate_tag_route(
    candidate_id: UUID,
    data: AddTagRequest,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Managers cannot add tags
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут добавлять теги кандидатам")

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
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут удалять теги кандидатов")

    await remove_candidate_tag(session, candidate_id, tag_id, company_id, user.id)
    await session.commit()


@router.post("/{candidate_id}/applications", response_model=ApplicationRow, status_code=201)
async def assign_to_vacancy_route(
    candidate_id: UUID,
    data: AssignToVacancyRequest,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    result = await assign_candidate_to_vacancy(
        session, candidate_id, data.vacancy_id, data.stage, company_id, user.id
    )
    await session.commit()
    return result


@router.get("/{candidate_id}/resume")
async def export_candidate_resume(
    candidate_id: UUID,
    format: str = Query("pdf", description="Формат экспорта: pdf или docx"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Экспорт резюме кандидата в PDF или DOCX"""

    # Валидация формата
    if format not in ["pdf", "docx"]:
        raise ValidationError("Допустимые форматы: pdf, docx")

    # Проверяем доступ к кандидату (аналогично GET /candidates/{candidate_id})
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    # Загружаем кандидата
    candidate = await load_candidate_for_export(session, company_id, candidate_id)

    # Генерируем файл в зависимости от формата
    if format == "pdf":
        content = build_resume_pdf(candidate)
        media_type = "application/pdf"
        extension = "pdf"
    else:  # docx
        content = build_resume_docx(candidate)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"

    # Формируем имя файла
    filename = f"{_full_name(candidate)}.{extension}"

    # Устанавливаем заголовки для скачивания с поддержкой кириллицы
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
    }

    return Response(
        content=content,
        media_type=media_type,
        headers=headers
    )