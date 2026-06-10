from fastapi import APIRouter, Depends, File, UploadFile, Form
from uuid import UUID
from typing import Dict, Any
import json

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...database import get_db
from ...core.errors import ValidationError, NotFoundError, ForbiddenError
from ...services.candidate_import import (
    parse_excel_file,
    preview_import,
    execute_import,
    get_import_job,
    MAX_IMPORT_FILE_BYTES,
    preview_potok_import,
    execute_potok_import,
)
from sqlalchemy.ext.asyncio import AsyncSession
from ...schemas.potok_import import PotokImportRequest, PotokImportResponse

router = APIRouter()

_MANAGER_FORBIDDEN = "Менеджеры не имеют доступа к общей базе кандидатов"


def _read_capped(content: bytes) -> None:
    """Защита воркера: отклоняем слишком большой файл (OOM)."""
    if len(content) > MAX_IMPORT_FILE_BYTES:
        raise ValidationError(
            f"Файл слишком большой. Максимальный размер — {MAX_IMPORT_FILE_BYTES // (1024*1024)} МБ"
        )


@router.post("/parse")
async def parse_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """
    Парсинг Excel файла и автоматическое распознавание колонок

    Returns:
        - columns: список названий колонок
        - samples: словарь с примерами данных по каждой колонке (до 3 примеров)
        - row_count: количество строк данных
        - auto_mapping: автоматически распознанные соответствия колонок
    """
    if user.role == "manager":
        raise ForbiddenError(_MANAGER_FORBIDDEN)
    if not file.filename:
        raise ValidationError("Файл не выбран")

    content = await file.read()
    if not content:
        raise ValidationError("Файл пустой")
    _read_capped(content)

    result = await parse_excel_file(content, file.filename)
    return result


@router.post("/preview")
async def preview_import_data(
    file: UploadFile = File(...),
    mapping: str = Form(...),  # JSON строка с маппингом колонок
    dedup_mode: str = Form(...),  # "skip" или "update"
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Превью импорта с классификацией строк

    Args:
        file: Excel файл
        mapping: JSON строка с соответствием колонок {column_name: field_key}
        dedup_mode: режим обработки дублей ("skip" или "update")

    Returns:
        - summary: статистика {total, new, duplicates, errors}
        - rows: превью строк (до 50)
        - shown: количество показанных строк
        - remaining: количество оставшихся строк
    """
    if user.role == "manager":
        raise ForbiddenError(_MANAGER_FORBIDDEN)
    if not file.filename:
        raise ValidationError("Файл не выбран")

    try:
        mapping_dict = json.loads(mapping)
    except (json.JSONDecodeError, TypeError):
        raise ValidationError("Неверный формат маппинга колонок")

    if dedup_mode not in ["skip", "update"]:
        raise ValidationError("Режим дедупликации должен быть 'skip' или 'update'")

    content = await file.read()
    if not content:
        raise ValidationError("Файл пустой")
    _read_capped(content)

    result = await preview_import(session, company_id, content, mapping_dict, dedup_mode)
    return result


@router.post("/execute")
async def execute_import_job(
    file: UploadFile = File(...),
    mapping: str = Form(...),  # JSON строка с маппингом
    dedup_mode: str = Form(...),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Запуск импорта в фоновом режиме

    Args:
        file: Excel файл
        mapping: JSON строка с соответствием колонок
        dedup_mode: режим обработки дублей

    Returns:
        job_id: UUID задачи импорта для отслеживания прогресса
    """
    if user.role == "manager":
        raise ForbiddenError(_MANAGER_FORBIDDEN)
    if not file.filename:
        raise ValidationError("Файл не выбран")

    try:
        mapping_dict = json.loads(mapping)
    except (json.JSONDecodeError, TypeError):
        raise ValidationError("Неверный формат маппинга колонок")

    if dedup_mode not in ["skip", "update"]:
        raise ValidationError("Режим дедупликации должен быть 'skip' или 'update'")

    content = await file.read()
    if not content:
        raise ValidationError("Файл пустой")
    _read_capped(content)

    job_id = await execute_import(session, company_id, user.id, content, mapping_dict, dedup_mode)

    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_import_job_status(
    job_id: UUID,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Получение статуса задачи импорта

    Returns:
        Информация о задаче импорта: id, status, прогресс, статистика
    """
    if user.role == "manager":
        raise ForbiddenError(_MANAGER_FORBIDDEN)
    job = await get_import_job(session, job_id, company_id)
    if not job:
        raise NotFoundError(f"Задача импорта {job_id} не найдена")

    return {
        "id": job.id,
        "status": job.status,
        "total": job.total,
        "processed": job.processed,
        "created": job.created,
        "updated": job.updated,
        "skipped": job.skipped,
        "errors": job.errors,
        "error": job.error
    }


@router.post("/potok/preview")
async def preview_potok_import_data(
    data: PotokImportRequest,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Превью импорта кандидатов из Potok.io

    Args:
        data: токен и режим дедупликации

    Returns:
        Статистика превью аналогично Excel-импорту
    """
    if user.role == "manager":
        raise ForbiddenError(_MANAGER_FORBIDDEN)

    result = await preview_potok_import(session, company_id, data.token, data.dedup_mode)
    return result


@router.post("/potok/execute", response_model=PotokImportResponse)
async def execute_potok_import_job(
    data: PotokImportRequest,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Запуск импорта из Potok.io в фоновом режиме

    Args:
        data: токен и режим дедупликации

    Returns:
        job_id: UUID задачи импорта для отслеживания прогресса
    """
    if user.role == "manager":
        raise ForbiddenError(_MANAGER_FORBIDDEN)

    job_id = await execute_potok_import(session, company_id, user.id, data.token, data.dedup_mode)

    return PotokImportResponse(job_id=str(job_id))