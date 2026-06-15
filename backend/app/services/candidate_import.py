"""Сервис импорта кандидатов из Excel файлов"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, List, Any
from uuid import UUID

from openpyxl import load_workbook
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import ValidationError
from ..database import AsyncSessionLocal
from ..models import Candidate, CandidateImportJob, CandidateExperience, CandidateSkill, CandidateEducation
from ..schemas.candidate import CandidateSource
from ..services.audit import audit
from ..services.integrations.potok.client import get_all_applicants, preview_applicants
from ..services.integrations.potok.mapper import map_potok_applicant
from .base_search import reindex_all_embeddings
from .candidate_dedup import _clean_phone, _normalize_contact, _phone_query_variants, _get_existing_candidates

logger = logging.getLogger(__name__)

# Удерживаем ссылки на фоновые задачи импорта — иначе event loop держит лишь слабую
# ссылку и GC может убить задачу до завершения (job навсегда застрянет в running).
_active_tasks: dict = {}

# Потолок размера загружаемого файла (защита воркера от OOM на гигантском .xlsx).
MAX_IMPORT_FILE_BYTES = 15 * 1024 * 1024


def _fit(value, maxlen: int):
    """Обрезает строковое значение под лимит колонки БД (иначе StringDataRightTruncation
    на commit уронит весь батч). None — как есть."""
    if value is None:
        return None
    s = str(value)
    return s[:maxlen] if len(s) > maxlen else s

# Синонимы для авто-распознавания колонок (fuzzy matching, lowercase)
FIELD_SYNONYMS = {
    "name": ["фио кандидата", "фио", "имя", "кандидат", "full name", "полное имя"],
    "phone": ["моб. телефон", "мобильный телефон", "телефон", "номер телефона", "phone", "мобильный"],
    "email": ["e-mail", "эл. почта", "почта", "email", "электронная почта"],
    "city": ["город", "город проживания", "city", "местоположение"],
    "age": ["возраст", "age", "лет"],
    "salary": ["зарплатные ожидания", "зп", "ожидания по зарплате", "salary", "зарплата"],
    "source": ["источник", "источник отклика", "по способу добавления", "source"],
    "position": ["желаемая должность", "должность", "позиция", "position", "роль"],
    "company": ["компания", "место работы", "company", "организация"],
    "experience": ["опыт", "стаж", "experience", "опыт работы"],
    "comment": ["комментарий", "комментарий рекрутёра", "note", "заметка"],
    "resume_url": ["резюме", "ссылка на резюме", "cv link", "резюме ссылка", "cv url"]
}


def _parse_excel_sync(content: bytes) -> tuple[list[str], dict[str, list[str]], int]:
    """Синхронный парсинг Excel файла с возвратом колонок, примеров и количества строк"""

    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    worksheet = workbook.active

    rows_iter = worksheet.iter_rows(values_only=True)

    # Первая строка - заголовки
    headers_row = next(rows_iter, None)
    if not headers_row:
        raise ValidationError("Файл пустой или не содержит заголовков")

    # Очищаем заголовки от None и приводим к строкам
    columns = [str(cell).strip() if cell is not None else f"Колонка {i+1}"
               for i, cell in enumerate(headers_row)]

    # Собираем примеры данных (до 3 на колонку)
    samples = {col: [] for col in columns}
    data_rows = []

    for row in rows_iter:
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue  # Пропускаем пустые строки

        data_rows.append(row)

        # Собираем примеры для каждой колонки
        for i, cell in enumerate(row):
            if i < len(columns) and cell is not None:
                cell_str = str(cell).strip()
                if cell_str and len(samples[columns[i]]) < 3:
                    samples[columns[i]].append(cell_str)

    workbook.close()
    return columns, samples, len(data_rows)


async def parse_excel_file(content: bytes, filename: str) -> dict:
    """Парсинг Excel файла и возврат метаданных"""
    file_ext = Path(filename).suffix.lower()

    if file_ext == '.xls':
        raise ValidationError("Старый формат .xls не поддерживается. Пересохраните файл в формате .xlsx")

    if file_ext != '.xlsx':
        raise ValidationError("Поддерживаются только файлы формата .xlsx")

    try:
        columns, samples, row_count = await asyncio.to_thread(_parse_excel_sync, content)
    except Exception as e:
        logger.error(f"Ошибка парсинга Excel файла {filename}: {e}")
        raise ValidationError("Не удалось прочитать файл. Поддерживаются только .xlsx файлы")

    # Автоматическое распознавание колонок
    auto_mapping = _auto_map_columns(columns)

    return {
        "columns": columns,
        "samples": samples,
        "row_count": row_count,
        "auto_mapping": auto_mapping
    }


def _auto_map_columns(columns: list[str]) -> dict[str, str]:
    """Автоматическое распознавание колонок файла"""
    mapping = {}
    used_fields = set()

    for col in columns:
        col_lower = col.lower().strip()

        # Ищем лучшее совпадение
        best_field = None
        for field_key, synonyms in FIELD_SYNONYMS.items():
            if field_key in used_fields:
                continue

            for synonym in synonyms:
                if synonym in col_lower:
                    best_field = field_key
                    break

            if best_field:
                break

        if best_field:
            mapping[col] = best_field
            used_fields.add(best_field)
        else:
            mapping[col] = "skip"

    return mapping


def _clean_name(value: str) -> tuple[str, str, str]:
    """Очистка и разбор ФИО. Возвращает (last_name, first_name, middle_name)"""
    if not value:
        return "", "", ""

    # Убираем коды анонимизации типа "062-" (только в начале токена — чтобы не клеить
    # слова вроде "Иван123-Петров").
    cleaned = re.sub(r'\b\d{3}-', '', str(value)).strip()

    # Разбиваем по пробелам
    parts = [p.strip() for p in cleaned.split() if p.strip()]

    if len(parts) == 0:
        return "", "", ""
    elif len(parts) == 1:
        return "", parts[0], ""  # first_name
    elif len(parts) == 2:
        return parts[0], parts[1], ""  # last_name, first_name
    else:
        # 3+ токена: фамилия, имя, остальное как отчество
        return parts[0], parts[1], " ".join(parts[2:])




def _parse_company_position(value: str, field_type: str) -> tuple[str, str]:
    """Парсинг значения 'Компания: Должность' - возвращает (company, position)"""
    if not value or ':' not in value:
        if field_type == 'company':
            return str(value or ""), ""
        else:  # position
            return "", str(value or "")

    parts = value.split(':', 1)
    company = parts[0].strip()
    position = parts[1].strip()

    return company, position


def _clean_salary(value: str) -> Optional[int]:
    """Извлечение зарплаты как числа"""
    if not value:
        return None

    # Убираем пробелы и нецифровые символы, оставляем только цифры
    digits = re.sub(r'[^\d]', '', str(value))

    if not digits:
        return None

    try:
        salary = int(digits)
        # Санити-проверка
        if salary < 0 or salary > 10_000_000:
            return None
        return salary
    except ValueError:
        return None


def _clean_source(value: str) -> str:
    """Очистка и маппинг источника"""
    if not value:
        return "other"

    value_lower = str(value).lower()

    if any(x in value_lower for x in ['headhunter', 'hh']):
        return "hh"
    elif any(x in value_lower for x in ['вручную', 'manual']):
        return "manual"
    elif any(x in value_lower for x in ['telegram', 'телеграм']):
        return "telegram"
    elif any(x in value_lower for x in ['avito', 'авито']):
        return "avito"
    elif 'superjob' in value_lower:
        return "superjob"
    else:
        return "other"




def _classify_rows(rows: list[dict], existing_candidates: list[Candidate],
                  mapping: dict[str, str]) -> list[dict]:
    """Классификация строк на new/duplicate/error"""
    # Создаем словари существующих контактов
    existing_phones = {_normalize_contact(c.phone or ""): c for c in existing_candidates if c.phone}
    existing_emails = {_normalize_contact(c.email or ""): c for c in existing_candidates if c.email}

    # Для отслеживания внутрифайловых дублей
    seen_phones = {}
    seen_emails = {}

    classified_rows = []

    for i, row in enumerate(rows):
        # Базовая информация
        preview_row = {
            "index": i + 1,
            "name": "",
            "phone": "",
            "email": "",
            "city": "",
            "source": "other",
            "status": "new",
            "error": None,
            "detail": {}
        }

        # Заполняем детали из маппинга
        name_value = ""
        phone_value = ""
        email_value = ""

        for col, field in mapping.items():
            if field == "skip":
                continue

            value = row.get(col, "")
            if not value:
                continue

            if field == "name":
                name_value = str(value).strip()
                last_name, first_name, middle_name = _clean_name(name_value)
                preview_row["name"] = f"{first_name} {last_name}".strip()
                preview_row["detail"]["full_name"] = f"{last_name} {first_name} {middle_name}".strip()
                preview_row["detail"]["last_name"] = last_name
                preview_row["detail"]["first_name"] = first_name
                preview_row["detail"]["middle_name"] = middle_name

            elif field == "phone":
                phone_value = str(value).strip()
                preview_row["phone"] = _clean_phone(phone_value)
                preview_row["detail"]["phone"] = preview_row["phone"]

            elif field == "email":
                email_value = str(value).strip()
                preview_row["email"] = email_value
                preview_row["detail"]["email"] = email_value

            elif field == "city":
                preview_row["city"] = str(value).strip()
                preview_row["detail"]["city"] = str(value).strip()

            elif field == "source":
                preview_row["source"] = _clean_source(str(value))
                preview_row["detail"]["source"] = preview_row["source"]

            elif field == "position":
                company, position = _parse_company_position(str(value), "position")
                if position:
                    preview_row["detail"]["position"] = position
                if company:
                    preview_row["detail"]["company"] = company

            elif field == "company":
                company, position = _parse_company_position(str(value), "company")
                if company:
                    preview_row["detail"]["company"] = company
                if position:
                    preview_row["detail"]["position"] = position

            elif field == "experience":
                preview_row["detail"]["experience"] = str(value).strip()

            elif field == "age":
                try:
                    age = int(str(value))
                    preview_row["detail"]["age"] = age
                except (ValueError, TypeError):
                    pass

            elif field == "salary":
                salary = _clean_salary(str(value))
                if salary:
                    preview_row["detail"]["salary"] = salary

            elif field == "comment":
                preview_row["detail"]["comment"] = str(value).strip()

            elif field == "resume_url":
                url = str(value).strip()
                if len(url) <= 500:
                    preview_row["detail"]["resume_url"] = url

        # Проверяем ошибки
        if not name_value.strip():
            preview_row["status"] = "error"
            preview_row["error"] = "нет имени"
        elif not phone_value.strip() and not email_value.strip():
            preview_row["status"] = "error"
            preview_row["error"] = "нет контакта"
        else:
            # Проверяем дедупликацию
            norm_phone = _normalize_contact(phone_value)
            norm_email = _normalize_contact(email_value)

            # Базовый дубль (есть в БД) — запоминаем кандидата для режима «Обновить».
            matched = None
            if norm_phone and norm_phone in existing_phones:
                matched = existing_phones[norm_phone]
            elif norm_email and norm_email in existing_emails:
                matched = existing_emails[norm_email]
            # Внутрифайловый дубль (повтор более ранней строки этого же файла).
            within_file = bool(
                (norm_phone and norm_phone in seen_phones)
                or (norm_email and norm_email in seen_emails)
            )

            if matched is not None:
                preview_row["status"] = "duplicate"
                preview_row["_match_id"] = str(matched.id)
            elif within_file:
                preview_row["status"] = "duplicate"
            else:
                # Запоминаем контакты для следующих строк
                if norm_phone:
                    seen_phones[norm_phone] = i
                if norm_email:
                    seen_emails[norm_email] = i

        classified_rows.append(preview_row)

    return classified_rows


async def preview_import(session: AsyncSession, company_id: UUID, content: bytes,
                        mapping: dict[str, str], dedup_mode: str) -> dict:
    """Превью импорта с классификацией строк"""
    # Парсим файл заново
    columns, samples, row_count = await asyncio.to_thread(_parse_excel_sync, content)

    # Читаем все строки данных

    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    worksheet = workbook.active

    rows_iter = worksheet.iter_rows(values_only=True)
    next(rows_iter)  # Пропускаем заголовки

    rows = []
    for row in rows_iter:
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        # Преобразуем row в словарь по колонкам
        row_dict = {}
        for i, cell in enumerate(row):
            if i < len(columns):
                row_dict[columns[i]] = cell
        rows.append(row_dict)

    workbook.close()

    # Собираем все контакты для проверки дедупликации
    all_phones = []
    all_emails = []

    for row in rows:
        for col, field in mapping.items():
            value = row.get(col, "")
            if not value:
                continue

            if field == "phone":
                norm_phone = _normalize_contact(_clean_phone(str(value)))
                if norm_phone:
                    all_phones.append(norm_phone)
            elif field == "email":
                norm_email = _normalize_contact(str(value))
                if norm_email:
                    all_emails.append(norm_email)

    # Получаем существующих кандидатов
    existing_candidates = await _get_existing_candidates(session, company_id, all_phones, all_emails)

    # Классифицируем строки
    classified_rows = _classify_rows(rows, existing_candidates, mapping)

    # Подсчитываем статистику
    total = len(classified_rows)
    new = len([r for r in classified_rows if r["status"] == "new"])
    duplicates = len([r for r in classified_rows if r["status"] == "duplicate"])
    errors = len([r for r in classified_rows if r["status"] == "error"])

    # Возвращаем первые 50 строк (без внутренних служебных ключей вроде _match_id)
    shown = min(50, total)
    remaining = max(0, total - shown)
    clean_rows = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in classified_rows[:shown]
    ]

    return {
        "summary": {
            "total": total,
            "new": new,
            "duplicates": duplicates,
            "errors": errors
        },
        "rows": clean_rows,
        "shown": shown,
        "remaining": remaining
    }


async def create_import_job(session: AsyncSession, company_id: UUID, total_rows: int) -> CandidateImportJob:
    """Создание задачи импорта"""
    job = CandidateImportJob(
        company_id=company_id,
        total=total_rows,
        status="running"
    )
    session.add(job)
    await session.flush()
    return job


async def get_import_job(session: AsyncSession, job_id: UUID, company_id: UUID) -> Optional[CandidateImportJob]:
    """Получение задачи импорта"""
    result = await session.execute(
        select(CandidateImportJob).where(
            CandidateImportJob.id == job_id,
            CandidateImportJob.company_id == company_id
        )
    )
    return result.scalar_one_or_none()


def _utc_naive_now() -> datetime:
    """Текущий UTC без tzinfo для finished_at"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _apply_update(candidate: Candidate, detail: dict) -> None:
    """Режим «Обновить»: переписывает поля существующего кандидата значениями из файла
    (только непустыми — не затираем имеющееся пустым). Имя/этап не трогаем."""
    if detail.get("phone"):
        candidate.phone = _fit(detail["phone"], 20)
    if detail.get("email"):
        candidate.email = _fit(detail["email"], 255)
    if detail.get("city"):
        candidate.city = _fit(detail["city"], 120)
    if detail.get("salary"):
        salary_value = detail["salary"]
        candidate.salary_expectation = salary_value
        candidate.salary_from = salary_value
        candidate.salary_to = salary_value
    if detail.get("position"):
        candidate.last_position = _fit(detail["position"], 255)
    if detail.get("company"):
        candidate.last_company = _fit(detail["company"], 255)
    if detail.get("experience"):
        candidate.last_period = _fit(detail["experience"], 120)
    if detail.get("resume_url"):
        candidate.source_url = _fit(detail["resume_url"], 500)


async def _update_job_progress(job_id: UUID, **updates):
    """Обновление прогресса задачи короткой сессией"""

    try:
        async with AsyncSessionLocal() as session:
            job = await session.get(CandidateImportJob, job_id)
            if not job:
                return

            for key, value in updates.items():
                setattr(job, key, value)

            await asyncio.wait_for(session.commit(), timeout=10)
    except Exception as e:
        logger.warning(f"Ошибка обновления прогресса импорта {job_id}: {e}")


async def _finalize_job(job_id: UUID, status: str, error: str = None):
    """Финализация задачи импорта"""

    try:
        async with AsyncSessionLocal() as session:
            job = await session.get(CandidateImportJob, job_id)
            if not job:
                return

            job.status = status
            job.finished_at = _utc_naive_now()
            if error:
                job.error = error

            await asyncio.wait_for(session.commit(), timeout=10)
    except Exception as e:
        logger.error(f"Ошибка финализации импорта {job_id}: {e}")


async def _run_import(job_id: UUID, company_id: UUID, user_id: UUID,
                     file_bytes: bytes, mapping: dict[str, str], dedup_mode: str):
    """Фоновое выполнение импорта"""

    try:
        # Парсим файл
        columns, samples, row_count = await asyncio.to_thread(_parse_excel_sync, file_bytes)

        # Читаем все строки
        workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        worksheet = workbook.active

        rows_iter = worksheet.iter_rows(values_only=True)
        next(rows_iter)  # Пропускаем заголовки

        all_rows = []
        for row in rows_iter:
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            row_dict = {}
            for i, cell in enumerate(row):
                if i < len(columns):
                    row_dict[columns[i]] = cell
            all_rows.append(row_dict)

        workbook.close()

        # Обновляем total
        await _update_job_progress(job_id, total=len(all_rows))

        # Получаем существующих кандидатов для дедупликации
        all_phones = []
        all_emails = []

        for row in all_rows:
            for col, field in mapping.items():
                value = row.get(col, "")
                if not value:
                    continue

                if field == "phone":
                    norm_phone = _normalize_contact(_clean_phone(str(value)))
                    if norm_phone:
                        all_phones.append(norm_phone)
                elif field == "email":
                    norm_email = _normalize_contact(str(value))
                    if norm_email:
                        all_emails.append(norm_email)

        async with AsyncSessionLocal() as session:
            existing_candidates = await _get_existing_candidates(session, company_id, all_phones, all_emails)

        # Классифицируем строки
        classified_rows = _classify_rows(all_rows, existing_candidates, mapping)

        # Обрабатываем батчами
        batch_size = 500
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors_count = 0

        for i in range(0, len(classified_rows), batch_size):
            batch = classified_rows[i:i + batch_size]

            async with AsyncSessionLocal() as session:
                for row_data in batch:
                    try:
                        if row_data["status"] == "error":
                            errors_count += 1
                            continue

                        # Каждую строку обрабатываем в savepoint: сбой одной записи
                        # (нарушение CHECK и т.п.) откатывает ТОЛЬКО её, не «отравляет»
                        # сессию и не валит весь батч (до 500 кандидатов). Счётчики
                        # инкрементим строго ПОСЛЕ успешного flush.
                        async with session.begin_nested():
                            if row_data["status"] == "duplicate":
                                match_id = row_data.get("_match_id")
                                if dedup_mode == "update" and match_id:
                                    # Реальное обновление существующего кандидата полями из файла.
                                    existing = await session.get(Candidate, UUID(match_id))
                                    if existing is not None and existing.company_id == company_id:
                                        _apply_update(existing, row_data["detail"])
                                        await session.flush()
                                        updated_count += 1
                                    else:
                                        skipped_count += 1
                                else:
                                    # skip-режим ИЛИ внутрифайловый дубль (без базового совпадения)
                                    skipped_count += 1
                            elif row_data["status"] == "new":
                                detail = row_data["detail"]
                                candidate = Candidate(
                                    company_id=company_id,  # ВСЕГДА из контекста, не из файла
                                    last_name=_fit(detail.get("last_name") or "", 120),
                                    first_name=_fit(detail.get("first_name") or "Неизвестно", 120),
                                    middle_name=_fit(detail.get("middle_name") or None, 120),
                                    phone=_fit(detail.get("phone"), 20),
                                    email=_fit(detail.get("email"), 255),
                                    city=_fit(detail.get("city"), 120),
                                    salary_expectation=detail.get("salary"),
                                    salary_from=detail.get("salary"),
                                    salary_to=detail.get("salary"),
                                    last_position=_fit(detail.get("position"), 255),
                                    last_company=_fit(detail.get("company"), 255),
                                    last_period=_fit(detail.get("experience"), 120),
                                    source=detail.get("source") or "import",
                                    external_source="import",
                                    source_url=_fit(detail.get("resume_url"), 500),
                                    extra={"imported": True}
                                )
                                session.add(candidate)
                                await session.flush()
                                created_count += 1

                    except Exception as e:
                        logger.error(f"Ошибка обработки строки импорта Excel: {e}")
                        errors_count += 1

                await session.commit()

            # Обновляем прогресс
            processed = min(i + batch_size, len(classified_rows))
            await _update_job_progress(
                job_id,
                processed=processed,
                created=created_count,
                updated=updated_count,
                skipped=skipped_count,
                errors=errors_count
            )

        # Создаем audit запись
        async with AsyncSessionLocal() as session:
            await audit(
                session,
                action="candidates_import",
                entity_type="candidate_import_job",
                entity_id=job_id,
                after={
                    "created": created_count,
                    "updated": updated_count,
                    "skipped": skipped_count,
                    "errors": errors_count
                },
                actor_type="human",
                actor_user_id=user_id,
                company_id=company_id
            )
            await session.commit()

        # Финализируем
        await _finalize_job(job_id, "done")

        # Запускаем переиндексацию эмбеддингов для всей компании
        try:
            await reindex_all_embeddings(company_id)
            logger.info(f"Запущена переиндексация эмбеддингов после импорта для компании {company_id}")
        except Exception as e:
            logger.error(f"Ошибка запуска переиндексации после импорта: {e}")

    except Exception as e:
        logger.error(f"Ошибка выполнения импорта {job_id}: {e}")
        await _finalize_job(job_id, "error", str(e)[:500])


async def execute_import(session: AsyncSession, company_id: UUID, user_id: UUID,
                        content: bytes, mapping: dict[str, str], dedup_mode: str) -> UUID:
    """Запуск импорта в фоновой задаче"""
    # Считаем общее количество строк
    columns, samples, row_count = await asyncio.to_thread(_parse_excel_sync, content)

    # Создаем задачу
    job = await create_import_job(session, company_id, row_count)
    await session.commit()

    # Запускаем в фоне. Удерживаем ссылку в _active_tasks — иначе GC может убить задачу
    # до завершения (job застрянет в running навсегда). callback снимает ссылку по завершении.
    task = asyncio.create_task(_run_import(job.id, company_id, user_id, content, mapping, dedup_mode))
    _active_tasks[job.id] = task

    def _cleanup_task(_t, _jid=job.id):
        _active_tasks.pop(_jid, None)

    task.add_done_callback(_cleanup_task)

    return job.id


# === POTOK IMPORT FUNCTIONS ===

async def preview_potok_import(session: AsyncSession, company_id: UUID, token: str, dedup_mode: str) -> dict:
    """
    Превью импорта кандидатов из Potok.io с дедупликацией

    Использует LIGHT preview_applicants() — быстрый запрос без полной загрузки

    Args:
        session: DB сессия
        company_id: ID компании
        token: API токен Potok
        dedup_mode: режим дедупликации ('skip' или 'update')

    Returns:
        Статистика превью аналогично Excel-импорту
    """
    logger.info("Начинаем превью импорта Potok")

    try:
        # Быстрый превью без полной загрузки всех ~15,700
        estimated_total, preview_sample = await preview_applicants(token, sample=50)

        logger.info(f"Превью Potok: получено {len(preview_sample)} образцов, оценка общего количества: {estimated_total}")

    except Exception as e:
        logger.error(f"Ошибка превью Potok: {e}")
        raise

    # Маппим кандидатов для превью
    mapped_candidates = []
    for raw in preview_sample:
        try:
            mapped = map_potok_applicant(raw)
            mapped_candidates.append(mapped)
        except Exception as e:
            logger.error(f"Ошибка маппинга кандидата Potok {raw.get('id', '?')}: {e}")
            continue

    # Собираем контакты для дедупликации
    all_phones = []
    all_emails = []
    for candidate in mapped_candidates:
        if candidate.get("phone"):
            norm_phone = _normalize_contact(candidate["phone"])
            if norm_phone:
                all_phones.append(norm_phone)
        if candidate.get("email"):
            norm_email = _normalize_contact(candidate["email"])
            if norm_email:
                all_emails.append(norm_email)

    # Получаем существующих кандидатов
    existing_candidates = await _get_existing_candidates(session, company_id, all_phones, all_emails)

    # Классифицируем кандидатов для превью
    classified_rows = _classify_potok_rows(mapped_candidates, existing_candidates)

    # Подсчет статистики для превью
    preview_total = len(classified_rows)
    preview_new = len([r for r in classified_rows if r["status"] == "new"])
    preview_duplicates = len([r for r in classified_rows if r["status"] == "duplicate"])
    preview_errors = len([r for r in classified_rows if r["status"] == "error"])

    # Экстраполируем статистику на весь объем данных
    if len(preview_sample) > 0 and estimated_total > len(preview_sample):
        scale_factor = estimated_total / len(preview_sample)
        total = int(preview_total * scale_factor)
        new = int(preview_new * scale_factor)
        duplicates = int(preview_duplicates * scale_factor)
        errors = int(preview_errors * scale_factor)
    else:
        total = preview_total
        new = preview_new
        duplicates = preview_duplicates
        errors = preview_errors

    # Возвращаем preview sample
    shown = len(classified_rows)
    remaining = max(0, total - shown)
    clean_rows = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in classified_rows
    ]

    return {
        "summary": {
            "total": total,
            "new": new,
            "duplicates": duplicates,
            "errors": errors
        },
        "rows": clean_rows,
        "shown": shown,
        "remaining": remaining
    }


def _classify_potok_rows(candidates: list[dict], existing_candidates: list[Candidate]) -> list[dict]:
    """Классификация кандидатов Potok на new/duplicate/error (аналог _classify_rows)"""
    # Создаем словари существующих контактов
    existing_phones = {_normalize_contact(c.phone or ""): c for c in existing_candidates if c.phone}
    existing_emails = {_normalize_contact(c.email or ""): c for c in existing_candidates if c.email}

    # Для отслеживания внутренних дублей
    seen_phones = {}
    seen_emails = {}

    classified_rows = []

    for i, candidate in enumerate(candidates):
        # Базовая информация для превью
        first_name = candidate.get("first_name", "")
        last_name = candidate.get("last_name", "")
        # маппер отдаёт phone/email как None (не "") → coerce, иначе .strip() ниже падает
        phone = candidate.get("phone") or ""
        email = candidate.get("email") or ""

        preview_row = {
            "index": i + 1,
            "name": f"{first_name} {last_name}".strip() or "Неизвестно",
            "phone": phone,
            "email": email,
            "city": candidate.get("city", ""),
            "source": "potok",
            "status": "new",
            "error": None,
            "detail": candidate  # полные данные для импорта
        }

        # Проверяем ошибки
        if not first_name.strip() and not last_name.strip():
            preview_row["status"] = "error"
            preview_row["error"] = "нет имени"
        elif not phone.strip() and not email.strip():
            preview_row["status"] = "error"
            preview_row["error"] = "нет контакта"
        else:
            # Проверяем дедупликацию
            norm_phone = _normalize_contact(phone)
            norm_email = _normalize_contact(email)

            # Базовый дубль (есть в БД)
            matched = None
            if norm_phone and norm_phone in existing_phones:
                matched = existing_phones[norm_phone]
            elif norm_email and norm_email in existing_emails:
                matched = existing_emails[norm_email]

            # Внутренний дубль (повтор в этом же запросе)
            within_request = bool(
                (norm_phone and norm_phone in seen_phones)
                or (norm_email and norm_email in seen_emails)
            )

            if matched is not None:
                preview_row["status"] = "duplicate"
                preview_row["_match_id"] = str(matched.id)
            elif within_request:
                preview_row["status"] = "duplicate"
            else:
                # Запоминаем контакты для следующих строк
                if norm_phone:
                    seen_phones[norm_phone] = i
                if norm_email:
                    seen_emails[norm_email] = i

        classified_rows.append(preview_row)

    return classified_rows


def _apply_potok_update(candidate: Candidate, detail: dict) -> None:
    """
    Режим «Обновить» для кандидата Potok: обновляем скалярные поля.

    Для MVP обновляем только основные поля, child-таблицы (опыт/навыки/образование)
    пересоздаем только для НОВЫХ кандидатов чтобы не плодить дубли.
    """
    if detail.get("phone"):
        candidate.phone = _fit(detail["phone"], 20)
    if detail.get("email"):
        candidate.email = _fit(detail["email"], 255)
    if detail.get("city"):
        candidate.city = _fit(detail["city"], 120)
    if detail.get("birth_date"):
        candidate.birth_date = detail["birth_date"]
    if detail.get("gender"):
        candidate.gender = detail["gender"]
    if detail.get("salary_expectation"):
        salary_value = detail["salary_expectation"]
        candidate.salary_expectation = salary_value
        candidate.salary_from = salary_value
        candidate.salary_to = salary_value
    if detail.get("last_position"):
        candidate.last_position = _fit(detail["last_position"], 255)
    if detail.get("resume_text"):
        candidate.resume_text = detail["resume_text"]
    if detail.get("resume_summary"):
        candidate.resume_summary = detail["resume_summary"]
    if detail.get("source_url"):
        candidate.source_url = _fit(detail["source_url"], 500)
    if detail.get("external_id"):
        candidate.external_id = _fit(detail["external_id"], 120)


async def _create_potok_child_records(session: AsyncSession, company_id: UUID, candidate_id: UUID, detail: dict):
    """Создание связанных записей (опыт, навыки, образование) для кандидата Potok"""

    # Опыт работы
    experience_list = detail.get("experience") or []
    for exp in experience_list:
        if exp.get("position"):
            session.add(CandidateExperience(
                company_id=company_id,
                candidate_id=candidate_id,
                position=_fit(exp["position"], 255),
                company=_fit(exp.get("company"), 255) if exp.get("company") else None,
                period=_fit(exp.get("period"), 120) if exp.get("period") else None,
                description=exp.get("description"),
                order_index=exp.get("order_index", 0)
            ))

    # Навыки
    skills_list = detail.get("skills") or []
    for skill in skills_list:
        if skill.get("skill"):
            session.add(CandidateSkill(
                company_id=company_id,
                candidate_id=candidate_id,
                skill=_fit(skill["skill"], 120),
                order_index=skill.get("order_index", 0)
            ))

    # Образование
    education_list = detail.get("education") or []
    for edu in education_list:
        if edu.get("institution"):
            session.add(CandidateEducation(
                company_id=company_id,
                candidate_id=candidate_id,
                institution=_fit(edu["institution"], 255),
                specialty=_fit(edu.get("specialty"), 255) if edu.get("specialty") else None,
                years=_fit(edu.get("years"), 40) if edu.get("years") else None,
                order_index=edu.get("order_index", 0)
            ))


async def _run_potok_import(job_id: UUID, company_id: UUID, user_id: UUID, token: str, dedup_mode: str):
    """Фоновое выполнение импорта из Potok.io"""

    try:
        # Progress callback: ставим total СРАЗУ → бар двигается уже на длинной фазе
        # загрузки из Потока (а не «зависает» на 0). Троттлинг: не плодим сотни
        # fire-and-forget сессий (иначе по одной на каждого applicant → давление на пул).
        def update_progress(done: int, total: int):
            if done == 1 or done % 20 == 0 or done == total:
                asyncio.create_task(_update_job_progress(job_id, processed=done, total=total))

        logger.info("Начинаем полный импорт из Potok")

        # Получаем всех кандидатов через новый HYBRID API
        try:
            all_candidates = await asyncio.wait_for(
                get_all_applicants(token, on_progress=update_progress),
                timeout=1800  # 30 минут таймаут на полный импорт (~15,700 кандидатов)
            )
        except asyncio.TimeoutError:
            logger.error("Таймаут полного импорта из Potok")
            await _finalize_job(job_id, "error", "Таймаут при загрузке всех кандидатов из Potok")
            return
        except Exception as e:
            logger.error(f"Ошибка полного импорта из Potok: {e}")
            raise

        # Обновляем total в джобе
        await _update_job_progress(job_id, total=len(all_candidates))
        logger.info(f"Получено {len(all_candidates)} кандидатов для импорта")

        # Маппим кандидатов
        mapped_candidates = []
        for raw in all_candidates:
            try:
                mapped = map_potok_applicant(raw)
                mapped_candidates.append(mapped)
            except Exception as e:
                logger.error(f"Ошибка маппинга кандидата Potok {raw.get('id', '?')}: {e}")
                continue

        # Получаем существующих кандидатов для дедупликации
        all_phones = []
        all_emails = []
        for candidate in mapped_candidates:
            if candidate.get("phone"):
                norm_phone = _normalize_contact(candidate["phone"])
                if norm_phone:
                    all_phones.append(norm_phone)
            if candidate.get("email"):
                norm_email = _normalize_contact(candidate["email"])
                if norm_email:
                    all_emails.append(norm_email)

        async with AsyncSessionLocal() as session:
            existing_candidates = await _get_existing_candidates(session, company_id, all_phones, all_emails)

        # Классифицируем кандидатов
        classified_rows = _classify_potok_rows(mapped_candidates, existing_candidates)

        # Обрабатываем батчами
        batch_size = 500
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors_count = 0

        for i in range(0, len(classified_rows), batch_size):
            batch = classified_rows[i:i + batch_size]

            async with AsyncSessionLocal() as session:
                for row_data in batch:
                    try:
                        if row_data["status"] == "error":
                            errors_count += 1
                            continue

                        # Каждую строку обрабатываем в savepoint: сбой одной записи
                        # (нарушение CHECK и т.п.) откатывает ТОЛЬКО её, не «отравляет»
                        # сессию и не валит весь батч (до 500 кандидатов). Счётчики
                        # инкрементим строго ПОСЛЕ успешного flush.
                        async with session.begin_nested():
                            if row_data["status"] == "duplicate":
                                match_id = row_data.get("_match_id")
                                if dedup_mode == "update" and match_id:
                                    # Обновление существующего кандидата
                                    existing = await session.get(Candidate, UUID(match_id))
                                    if existing is not None and existing.company_id == company_id:
                                        _apply_potok_update(existing, row_data["detail"])
                                        await session.flush()
                                        updated_count += 1
                                    else:
                                        skipped_count += 1
                                else:
                                    # skip-режим или внутренний дубль
                                    skipped_count += 1
                            elif row_data["status"] == "new":
                                detail = row_data["detail"]
                                candidate = Candidate(
                                    company_id=company_id,
                                    first_name=_fit(detail.get("first_name") or "Неизвестно", 120),
                                    last_name=_fit(detail.get("last_name") or "", 120),
                                    middle_name=_fit(detail.get("middle_name"), 120) if detail.get("middle_name") else None,
                                    phone=_fit(detail.get("phone"), 20) if detail.get("phone") else None,
                                    email=_fit(detail.get("email"), 255) if detail.get("email") else None,
                                    city=_fit(detail.get("city"), 120) if detail.get("city") else None,
                                    birth_date=detail.get("birth_date"),
                                    gender=detail.get("gender"),
                                    salary_expectation=detail.get("salary_expectation"),
                                    salary_from=detail.get("salary_expectation"),
                                    salary_to=detail.get("salary_expectation"),
                                    last_position=_fit(detail.get("last_position"), 255) if detail.get("last_position") else None,
                                    resume_text=detail.get("resume_text"),
                                    resume_summary=detail.get("resume_summary"),
                                    source="potok",
                                    external_source="potok",
                                    external_id=_fit(detail.get("external_id"), 120) if detail.get("external_id") else None,
                                    source_url=_fit(detail.get("source_url"), 500) if detail.get("source_url") else None,
                                    extra={"imported": True, "languages": detail.get("languages") or []}
                                )
                                session.add(candidate)
                                await session.flush()  # получаем ID

                                # Создаем связанные записи и фиксируем их в savepoint
                                await _create_potok_child_records(session, company_id, candidate.id, detail)
                                await session.flush()

                                created_count += 1

                    except Exception as e:
                        logger.error(f"Ошибка обработки кандидата Potok: {e}")
                        errors_count += 1

                await session.commit()

            # Обновляем прогресс
            processed = min(i + batch_size, len(classified_rows))
            await _update_job_progress(
                job_id,
                processed=processed,
                created=created_count,
                updated=updated_count,
                skipped=skipped_count,
                errors=errors_count
            )

        # Создаем audit запись
        async with AsyncSessionLocal() as session:
            await audit(
                session,
                action="candidates_import_potok",
                entity_type="candidate_import_job",
                entity_id=job_id,
                after={
                    "source": "potok",
                    "created": created_count,
                    "updated": updated_count,
                    "skipped": skipped_count,
                    "errors": errors_count
                },
                actor_type="human",
                actor_user_id=user_id,
                company_id=company_id
            )
            await session.commit()

        # Финализируем
        await _finalize_job(job_id, "done")

        # Запускаем переиндексацию эмбеддингов для всей компании
        try:
            await reindex_all_embeddings(company_id)
            logger.info(f"Запущена переиндексация эмбеддингов после Potok импорта для компании {company_id}")
        except Exception as e:
            logger.error(f"Ошибка запуска переиндексации после Potok импорта: {e}")

    except Exception as e:
        logger.error(f"Ошибка выполнения импорта Potok {job_id}: {e}")
        await _finalize_job(job_id, "error", str(e)[:500])


async def execute_potok_import(session: AsyncSession, company_id: UUID, user_id: UUID,
                              token: str, dedup_mode: str) -> UUID:
    """Запуск импорта из Potok в фоновой задаче"""

    # Создаем задачу с предварительным total (будет обновлен в _run_potok_import)
    job = await create_import_job(session, company_id, 0)  # total обновится позже
    await session.commit()

    # Запускаем в фоне с защитой от GC
    task = asyncio.create_task(_run_potok_import(job.id, company_id, user_id, token, dedup_mode))
    _active_tasks[job.id] = task

    def _cleanup_task(_t, _jid=job.id):
        _active_tasks.pop(_jid, None)

    task.add_done_callback(_cleanup_task)

    return job.id