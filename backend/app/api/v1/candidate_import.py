from fastapi import APIRouter, Depends, File, UploadFile, Form
from uuid import UUID
from typing import Dict, Any
import json

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...database import get_db
from ...core.errors import ValidationError, NotFoundError
from ...services.candidate_import import (
    parse_excel_file,
    preview_import,
    execute_import,
    get_import_job
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/parse")
async def parse_file(
    file: UploadFile = File(...),
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
    if not file.filename:
        raise ValidationError("Файл не выбран")

    content = await file.read()
    if not content:
        raise ValidationError("Файл пустой")

    result = await parse_excel_file(content, file.filename)
    return result


@router.post("/preview")
async def preview_import_data(
    file: UploadFile = File(...),
    mapping: str = Form(...),  # JSON строка с маппингом колонок
    dedup_mode: str = Form(...),  # "skip" или "update"
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

    job_id = await execute_import(session, company_id, user.id, content, mapping_dict, dedup_mode)

    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_import_job_status(
    job_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db)
):
    """
    Получение статуса задачи импорта

    Returns:
        Информация о задаче импорта: id, status, прогресс, статистика
    """
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