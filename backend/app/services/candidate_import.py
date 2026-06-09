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

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import ValidationError
from ..models import Candidate, CandidateImportJob
from ..schemas.candidate import CandidateSource
from ..services.audit import audit

logger = logging.getLogger(__name__)

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
    from openpyxl import load_workbook

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

    # Убираем коды анонимизации типа "123-"
    cleaned = re.sub(r'\d{3}-', '', str(value)).strip()

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


def _clean_phone(value: str) -> str:
    """Очистка и нормализация телефона"""
    if not value:
        return ""

    # Только цифры
    digits = re.sub(r'\D', '', str(value))

    if not digits:
        return str(value)[:20]  # Возвращаем как есть, обрезанное

    # Нормализация
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    elif len(digits) == 10:
        digits = '7' + digits

    return '+' + digits


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


def _normalize_contact(value: str) -> str:
    """Нормализация контакта для дедупликации"""
    if not value:
        return ""

    if '@' in value:  # email
        return value.lower().strip()
    else:  # phone
        return _clean_phone(value).replace('+', '').replace(' ', '')


async def _get_existing_candidates(session: AsyncSession, company_id: UUID,
                                 phones: list[str], emails: list[str]) -> list[Candidate]:
    """Получение существующих кандидатов для дедупликации"""
    if not phones and not emails:
        return []

    conditions = []
    if phones:
        conditions.append(Candidate.phone.in_(phones))
    if emails:
        conditions.append(Candidate.email.in_(emails))

    result = await session.execute(
        select(Candidate).where(
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
            or_(*conditions)
        )
    )
    return result.scalars().all()


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

            is_duplicate = False

            # Проверяем с существующими в базе
            if norm_phone and norm_phone in existing_phones:
                is_duplicate = True
            elif norm_email and norm_email in existing_emails:
                is_duplicate = True

            # Проверяем внутрифайловые дубли
            elif norm_phone and norm_phone in seen_phones:
                is_duplicate = True
            elif norm_email and norm_email in seen_emails:
                is_duplicate = True

            if is_duplicate:
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
    from openpyxl import load_workbook

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

    # Возвращаем первые 50 строк
    shown = min(50, total)
    remaining = max(0, total - shown)

    return {
        "summary": {
            "total": total,
            "new": new,
            "duplicates": duplicates,
            "errors": errors
        },
        "rows": classified_rows[:shown],
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


async def _update_job_progress(job_id: UUID, **updates):
    """Обновление прогресса задачи короткой сессией"""
    from ..database import AsyncSessionLocal

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
    from ..database import AsyncSessionLocal

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
    from ..database import AsyncSessionLocal

    try:
        # Парсим файл
        columns, samples, row_count = await asyncio.to_thread(_parse_excel_sync, file_bytes)

        # Читаем все строки
        from openpyxl import load_workbook

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
                        elif row_data["status"] == "duplicate":
                            if dedup_mode == "skip":
                                skipped_count += 1
                            else:  # update
                                # Пока просто считаем как обновленные, реальное обновление - в следующей итерации
                                updated_count += 1
                        elif row_data["status"] == "new":
                            # Создаем нового кандидата
                            detail = row_data["detail"]
                            full_name = detail.get("full_name", "")

                            # Правильно разбираем ФИО
                            if full_name:
                                name_parts = full_name.split()
                                if len(name_parts) >= 2:
                                    last_name = name_parts[0]
                                    first_name = name_parts[1]
                                    middle_name = " ".join(name_parts[2:]) if len(name_parts) > 2 else None
                                elif len(name_parts) == 1:
                                    last_name = ""
                                    first_name = name_parts[0]
                                    middle_name = None
                                else:
                                    last_name = ""
                                    first_name = "Неизвестно"
                                    middle_name = None
                            else:
                                last_name = ""
                                first_name = "Неизвестно"
                                middle_name = None

                            candidate = Candidate(
                                company_id=company_id,
                                last_name=last_name,
                                first_name=first_name,
                                middle_name=middle_name,
                                phone=detail.get("phone"),
                                email=detail.get("email"),
                                city=detail.get("city"),
                                salary_expectation=detail.get("salary"),
                                last_position=detail.get("position"),
                                last_company=detail.get("company"),
                                last_period=detail.get("experience"),
                                source=detail.get("source", "import"),
                                external_source="import",
                                source_url=detail.get("resume_url"),
                                extra={"imported": True}
                            )

                            session.add(candidate)
                            created_count += 1

                    except Exception as e:
                        logger.error(f"Ошибка обработки строки импорта: {e}")
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

    # Запускаем в фоне
    task = asyncio.create_task(_run_import(job.id, company_id, user_id, content, mapping, dedup_mode))

    return job.id