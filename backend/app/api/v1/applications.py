from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...deps import get_current_company_id, get_current_user
from ...models import User, Application
from ...core.errors import ForbiddenError, NotFoundError, ValidationError
from ...core.permissions import is_user_assigned_to_vacancy
from ...schemas.application import (
    ApplicationRow,
    BulkMoveRequest,
    BulkRejectRequest,
    BulkMoveResult,
    BulkRejectResult,
    MoveRequest,
    OfferPreviewOut,
    OfferStatusOut,
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
from ...services.offer import build_offer_preview, send_offer

router = APIRouter()

# ── Вложение письма-оффера ─────────────────────────────────────────────────────
# Один необязательный файл к письму. Валидация — В РОУТЕ (сервис получает готовый
# dict). Кап и белый список — по идиоме загрузки документов (services/document.py),
# но с более широким набором форматов офиса + честной 400 (ValidationError), а не
# 413/415, как требует контракт фичи.
_OFFER_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ
_OFFER_ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".rtf", ".png", ".jpg", ".jpeg",
}
_OFFER_ALLOWED_LABEL = "PDF, Word, Excel, изображения, текст"
# Фолбэк-MIME по расширению, когда content_type пуст/битый.
_OFFER_EXT_MIME = {
    ".pdf": ("application", "pdf"),
    ".doc": ("application", "msword"),
    ".docx": ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xls": ("application", "vnd.ms-excel"),
    ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".txt": ("text", "plain"),
    ".rtf": ("application", "rtf"),
    ".png": ("image", "png"),
    ".jpg": ("image", "jpeg"),
    ".jpeg": ("image", "jpeg"),
}


def _sanitize_attachment_filename(raw: str | None) -> str:
    """Только basename без путей/управляющих символов, ограниченный по длине.

    Отрезает и '/'-, и '\\'-пути (path-traversal в имени), выкидывает control-символы
    и переводы строк (инъекция заголовка), режет до 150. Пусто после чистки → 'attachment'.
    """
    base = (raw or "").replace("\\", "/").split("/")[-1]
    cleaned = "".join(ch for ch in base if ord(ch) >= 32).strip()[:150].strip()
    return cleaned or "attachment"


def _resolve_attachment_mime(content_type: str | None, ext: str) -> tuple[str, str]:
    """maintype/subtype из content_type ('application/pdf'→('application','pdf')).

    Пустой/битый content_type → фолбэк по расширению → 'application/octet-stream'.
    """
    ct = (content_type or "").strip()
    if ct and "/" in ct:
        maintype, _, subtype = ct.partition("/")
        maintype = maintype.strip().lower()
        subtype = subtype.split(";")[0].strip().lower()
        if maintype and subtype:
            return maintype, subtype
    if ext in _OFFER_EXT_MIME:
        return _OFFER_EXT_MIME[ext]
    return "application", "octet-stream"


def _build_offer_attachment(file: UploadFile, content: bytes) -> dict:
    """Провалидировать файл-вложение и собрать dict для send_email.

    Ошибки — честная 400 (ValidationError): слишком большой файл / недопустимый тип.
    Возвращает {"filename": str, "content": bytes, "maintype": str, "subtype": str}.
    """
    if len(content) > _OFFER_MAX_FILE_SIZE:
        raise ValidationError("Файл слишком большой (макс 10 МБ)")

    filename = _sanitize_attachment_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if ext not in _OFFER_ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Недопустимый тип файла. Разрешены: {_OFFER_ALLOWED_LABEL}"
        )

    maintype, subtype = _resolve_attachment_mime(file.content_type, ext)
    return {"filename": filename, "content": content, "maintype": maintype, "subtype": subtype}


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


@router.post(
    "/applications/{application_id}/offer/generate",
    response_model=OfferPreviewOut,
)
async def generate_offer_endpoint(
    application_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Сгенерировать тело оффера + вернуть эффективные приветствие/подпись (read-only).

    Только на этапе «Оффер». Роль manager — запрещена (hiring_manager отсечён _deny_hm).
    Генерация может ходить в LLM (долго) → wait_for внутри сервиса; фолбэк при сбое.
    Чтение — коммит не нужен.
    """
    if current_user.role == "manager":
        raise ForbiddenError("Недостаточно прав для отправки оффера")
    return await build_offer_preview(
        session, application_id=application_id, company_id=company_id
    )


@router.post(
    "/applications/{application_id}/offer/send",
    response_model=OfferStatusOut,
)
async def send_offer_endpoint(
    application_id: UUID,
    # default="" (а не Form(...)): пустое значение формы FastAPI трактует как отсутствующее
    # поле и даёт 422 «Field required» ДО нашей проверки. С дефолтом "" любое пустое (нет
    # поля / "" / пробелы) доходит до ручной проверки ниже → единая честная 400.
    body: str = Form(default=""),
    file: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Собрать (header настроек + тело + footer настроек) и отправить письмо-оффер.

    multipart/form-data: `body` — текст оффера (обязателен), `file` — необязательное
    вложение (напр. PDF-оффер). Обрамление — из настроек компании (сервер источник
    правды), клиент шлёт только тело. Роль manager — запрещена. Мутирует (Message +
    audit) → коммит в роуте.
    """
    if current_user.role == "manager":
        raise ForbiddenError("Недостаточно прав для отправки оффера")

    # Тело обязательно и не может быть пустым/из одних пробелов. При multipart
    # Pydantic-валидация не применяется → проверяем вручную (честная 400).
    if not body.strip():
        raise ValidationError("Тело оффера не может быть пустым")

    # Файл необязателен. 0 байт (пустая часть формы / файл не выбран) трактуем как «нет».
    attachment: dict | None = None
    if file is not None:
        content = await file.read()
        if content:
            attachment = _build_offer_attachment(file, content)

    await send_offer(
        session,
        application_id=application_id,
        company_id=company_id,
        actor_user_id=current_user.id,
        body=body,
        attachment=attachment,
    )
    await session.commit()
    return {"status": "sent"}


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
