"""Сервис синхронизации звонков из Mango Office"""

import asyncio
import csv
import io
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from uuid import UUID

from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from ..database import AsyncSessionLocal
from ..models import CallSyncJob, Call, Candidate, Integration
from ..services.audit import audit
from ..services.candidate_dedup import find_duplicate_candidates
from ..services.integrations.mango.service import get_status as get_mango_status, DEFAULT_BASE_URL
from ..services.integrations.mango.client import MangoClient
from ..services.settings.crypto import decrypt_text
from ..core.errors import ValidationError, ConflictError

logger = logging.getLogger(__name__)

# Удержание ссылок на фоновые задачи (защита от GC)
_active_tasks: Dict[str, asyncio.Task] = {}

# Константы для парсинга CSV
# Ожидаемые поля в указанном порядке - требует пиннинга на реальном ключе
EXPECTED_CSV_FIELDS = [
    "records", "start", "finish", "answer", "from_extension",
    "from_number", "to_extension", "to_number", "disconnect_reason",
    "entry_id", "line_number"
]

# Максимальное время ожидания готовности статистики (секунды)
MAX_STATS_WAIT_TIME = 120
STATS_POLL_INTERVAL = 5


def _parse_stats_csv(csv_content: str) -> List[Dict[str, Any]]:
    """Парсинг CSV статистики звонков из Mango Office.

    ВНИМАНИЕ: Функция требует пиннинга на реальном API ключе Mango Office.
    Реализована по документации API, но точные поля CSV и их порядок
    необходимо проверить при первом запуске с живыми данными.

    Args:
        csv_content: CSV строка от Mango Office

    Returns:
        List[Dict]: Список распарсенных звонков
    """
    if not csv_content.strip():
        return []

    calls = []
    try:
        # CSV формат: строки разделены \n, поля разделены ;, БЕЗ экранирования
        reader = csv.reader(io.StringIO(csv_content), delimiter=';')

        for row_num, row in enumerate(reader, 1):
            if len(row) < len(EXPECTED_CSV_FIELDS):
                logger.warning("CSV row %d has %d fields, expected %d, skipping",
                             row_num, len(row), len(EXPECTED_CSV_FIELDS))
                continue

            try:
                # Маппинг по позициям согласно документации
                call_data = {}
                for i, field_name in enumerate(EXPECTED_CSV_FIELDS):
                    call_data[field_name] = row[i].strip() if i < len(row) else ""

                # Обработка поля records (может содержать несколько ID через запятую)
                records_str = call_data.get("records", "")
                recording_ids = [r.strip() for r in records_str.split(",") if r.strip()]
                call_data["recording_id"] = recording_ids[0] if recording_ids else None

                # Определение направления звонка
                # ТРЕБУЕТ ПИННИНГА: точная логика зависит от реальных данных CSV
                from_ext = call_data.get("from_extension", "")
                to_ext = call_data.get("to_extension", "")
                from_num = call_data.get("from_number", "")
                to_num = call_data.get("to_number", "")
                answer = call_data.get("answer", "0")

                if from_ext and to_num and not to_ext:
                    # Есть внутренний номер отправителя и внешний получатель -> исходящий
                    direction = "out"
                    candidate_number = to_num
                elif to_ext and from_num and not from_ext:
                    # Есть внутренний номер получателя и внешний отправитель -> входящий
                    direction = "in"
                    candidate_number = from_num
                elif answer == "0":
                    # Не отвечен -> missed
                    direction = "missed"
                    candidate_number = to_num if from_ext else from_num
                else:
                    # Неопределенное направление - пропускаем
                    logger.warning("CSV row %d: cannot determine direction, skipping", row_num)
                    continue

                # Парсинг времени - ТРЕБУЕТ ПИННИНГА для определения формата
                start_time = None
                start_str = call_data.get("start", "")
                if start_str:
                    try:
                        # Предполагаем Unix timestamp; колонка started_at — НАИВНЫЙ UTC
                        # (точный часовой пояс Mango требует пиннинга на реальном ключе)
                        start_time = datetime.fromtimestamp(int(start_str), tz=timezone.utc).replace(tzinfo=None)
                    except (ValueError, OSError):
                        logger.warning("CSV row %d: invalid start time '%s'", row_num, start_str)

                # Длительность
                duration_sec = 0
                try:
                    start_ts = int(call_data.get("start", "0") or "0")
                    finish_ts = int(call_data.get("finish", "0") or "0")
                    if finish_ts > start_ts:
                        duration_sec = finish_ts - start_ts
                except ValueError:
                    pass

                # Формируем external_id (требует пиннинга - какое поле использовать)
                external_id = call_data.get("entry_id", "") or call_data.get("line_number", "")
                if not external_id:
                    logger.warning("CSV row %d: no external_id found, skipping", row_num)
                    continue

                parsed_call = {
                    "external_id": external_id,
                    "recording_id": call_data["recording_id"],
                    "direction": direction,
                    "candidate_number": candidate_number,
                    "from_number": from_num,
                    "to_number": to_num,
                    "duration_sec": duration_sec,
                    "started_at": start_time,
                    "raw_data": call_data  # Для отладки
                }

                calls.append(parsed_call)

            except Exception as e:
                logger.error("CSV row %d parsing error: %s, skipping", row_num, e)
                continue

    except Exception as e:
        logger.error("CSV parsing failed: %s", e)
        return []

    logger.info("Parsed %d calls from CSV (%d rows total)", len(calls), row_num)
    return calls


async def create_call_sync_job(
    session: AsyncSession,
    company_id: UUID,
    actor_user_id: UUID,
    days: int = 30
) -> CallSyncJob:
    """Создание джоба синхронизации звонков.

    Args:
        session: DB сессия
        company_id: ID компании
        actor_user_id: ID пользователя, запустившего синхронизацию
        days: Период синхронизации (дней назад от текущего момента)

    Returns:
        CallSyncJob: Созданный джоб

    Raises:
        ConflictError: Если уже есть запущенный джоб для компании
    """
    # TOCTOU-защита: проверяем, нет ли уже запущенного джоба
    existing_job = await session.execute(
        select(CallSyncJob).where(
            CallSyncJob.company_id == company_id,
            CallSyncJob.status == "running"
        )
    )
    if existing_job.scalar_one_or_none():
        raise ConflictError("Синхронизация звонков уже выполняется для этой компании")

    # Создаем джоб
    job = CallSyncJob(
        company_id=company_id,
        status="running"
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("Синхронизация звонков уже выполняется для этой компании")

    # Аудит запуска
    await audit(
        session,
        action="call_sync_started",
        entity_type="call_sync_job",
        entity_id=job.id,
        after={"days": days},
        actor_user_id=actor_user_id,
        company_id=company_id
    )

    await session.commit()
    return job


async def spawn_sync(job_id: UUID, company_id: UUID) -> None:
    """Запуск фоновой задачи синхронизации.

    Args:
        job_id: ID джоба синхронизации
        company_id: ID компании
    """
    # Создаем задачу и сохраняем ссылку
    task = asyncio.create_task(_run_sync(job_id, company_id))
    task_key = f"{company_id}_{job_id}"
    _active_tasks[task_key] = task

    # Очистка по завершению
    def cleanup_task(completed_task):
        _active_tasks.pop(task_key, None)

    task.add_done_callback(cleanup_task)


async def _run_sync(job_id: UUID, company_id: UUID) -> None:
    """Основная логика синхронизации звонков (выполняется в фоне).

    Args:
        job_id: ID джоба
        company_id: ID компании
    """
    logger.info("Starting call sync job %s for company %s", job_id, company_id)

    try:
        # Получаем настройки Mango Office
        async with AsyncSessionLocal() as session:
            mango_status = await get_mango_status(session, company_id)
            if not mango_status.get("configured") or not mango_status.get("verified"):
                await _finalize_job(job_id, "error", "Mango Office не настроен или не подключен")
                return

        # Читаем зашифрованные ключи
        async with AsyncSessionLocal() as session:
            integration = await session.execute(
                select(Integration).where(
                    Integration.company_id == company_id,
                    Integration.provider == "mango"
                )
            )
            integration = integration.scalar_one()

            config = integration.config
            api_key = decrypt_text(config["api_key"])
            api_salt = decrypt_text(config["api_salt"])
            base_url = config.get("vpbx_api_url", DEFAULT_BASE_URL)

        # Создаем клиент Mango
        client = MangoClient(api_key, api_salt, base_url)

        # Определяем период синхронизации (последние 30 дней)
        now = datetime.now(timezone.utc)
        date_to = int(now.timestamp())
        date_from = int((now - timedelta(days=30)).timestamp())

        # Запрашиваем статистику
        fields = "records,start,finish,answer,from_extension,from_number,to_extension,to_number,disconnect_reason,entry_id,line_number"
        stats_response = await client.request_stats(date_from, date_to, fields)
        stats_key = stats_response["key"]

        logger.info("Requested Mango stats with key %s, waiting for result", stats_key)

        # Ждем готовности статистики с поллингом
        csv_content = None
        start_wait = time.time()

        while time.time() - start_wait < MAX_STATS_WAIT_TIME:
            try:
                csv_content = await client.get_stats_result(stats_key)
                if csv_content is not None:
                    break

                await asyncio.sleep(STATS_POLL_INTERVAL)
            except Exception as e:
                logger.error("Error polling stats result: %s", e)
                await asyncio.sleep(STATS_POLL_INTERVAL)

        if csv_content is None:
            await _finalize_job(job_id, "error",
                              f"Статистика не готова через {MAX_STATS_WAIT_TIME}с")
            return

        # Парсим CSV
        calls_data = _parse_stats_csv(csv_content)
        total_calls = len(calls_data)

        logger.info("Processing %d calls from Mango Office", total_calls)

        # Обновляем счетчик total
        async with AsyncSessionLocal() as session:
            await _update_job_progress(session, job_id, total=total_calls)

        # Обрабатываем звонки батчами
        matched_count = 0
        created_count = 0
        batch_size = 50

        for i in range(0, len(calls_data), batch_size):
            batch = calls_data[i:i + batch_size]

            async with AsyncSessionLocal() as session:
                for call_data in batch:
                    try:
                        candidate_number = call_data.get("candidate_number", "")
                        if not candidate_number:
                            continue

                        # Ищем кандидата по номеру телефона
                        candidates = await find_duplicate_candidates(
                            session, company_id, candidate_number, None
                        )

                        if not candidates:
                            # Нет совпадений - пропускаем (не храним чужие звонки)
                            continue

                        matched_count += 1

                        # Берем самого свежего кандидата при множественном совпадении
                        candidate = max(candidates, key=lambda c: c.created_at)

                        # Проверяем дедупликацию по external_id
                        existing_call = await session.execute(
                            select(Call).where(
                                Call.company_id == company_id,
                                Call.external_id == call_data["external_id"]
                            )
                        )
                        if existing_call.scalar_one_or_none():
                            continue  # Уже есть

                        # Создаем запись звонка
                        call = Call(
                            company_id=company_id,
                            candidate_id=candidate.id,
                            external_id=call_data["external_id"],
                            recording_id=call_data.get("recording_id"),
                            direction=call_data.get("direction"),
                            from_number=call_data.get("from_number"),
                            to_number=call_data.get("to_number"),
                            duration_sec=call_data.get("duration_sec", 0),
                            started_at=call_data.get("started_at"),
                            # recruiter_name можно определить из внутреннего номера,
                            # но требует пиннинга справочника сотрудников
                            recruiter_name=None
                        )
                        session.add(call)
                        created_count += 1

                    except Exception as e:
                        logger.error("Error processing call %s: %s",
                                   call_data.get("external_id", "?"), e)
                        continue

                await session.commit()

                # Обновляем прогресс
                await _update_job_progress(session, job_id,
                                         matched=matched_count,
                                         created=created_count)

        logger.info("Call sync completed: %d total, %d matched, %d created",
                   total_calls, matched_count, created_count)

        # Завершаем успешно
        async with AsyncSessionLocal() as session:
            await _finalize_job_success(session, job_id, company_id)

    except Exception as e:
        logger.error("Call sync job %s failed: %s", job_id, e, exc_info=True)
        await _finalize_job(job_id, "error", str(e))


async def _update_job_progress(
    session: AsyncSession,
    job_id: UUID,
    **kwargs
) -> None:
    """Обновление прогресса джоба"""
    update_data = {k: v for k, v in kwargs.items() if v is not None}
    if update_data:
        await session.execute(
            update(CallSyncJob)
            .where(CallSyncJob.id == job_id)
            .values(**update_data)
        )
        await session.commit()


async def _finalize_job(job_id: UUID, status: str, error: Optional[str] = None) -> None:
    """Финализация джоба с ошибкой"""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(CallSyncJob)
            .where(CallSyncJob.id == job_id)
            .values(
                status=status,
                error=error,
                finished_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
        )
        await session.commit()


async def _finalize_job_success(session: AsyncSession, job_id: UUID, company_id: UUID) -> None:
    """Финализация успешного джоба"""
    await session.execute(
        update(CallSyncJob)
        .where(CallSyncJob.id == job_id)
        .values(
            status="done",
            finished_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
    )

    # Аудит завершения
    await audit(
        session,
        action="call_sync_completed",
        entity_type="call_sync_job",
        entity_id=job_id,
        actor_user_id=None,  # Системное действие
        company_id=company_id,
        actor_type="ai"
    )

    await session.commit()


async def sweep_orphaned_call_sync_jobs() -> None:
    """Очистка зависших джобов синхронизации (вызывается при старте)"""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(CallSyncJob)
            .where(
                CallSyncJob.status == "running",
                CallSyncJob.updated_at < cutoff
            )
            .values(
                status="error",
                error="Процесс прерван (таймаут/перезапуск сервера)",
                finished_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            .returning(CallSyncJob.id)
        )
        orphaned_ids = [row[0] for row in result.fetchall()]

        if orphaned_ids:
            logger.warning("Cleaned up %d orphaned call sync jobs: %s",
                         len(orphaned_ids), orphaned_ids)
            await session.commit()