"""API эндпоинты для работы со звонками Mango Office"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...deps import get_current_user
from ...core.permissions import require_recruiter_or_admin
from ...core.errors import ValidationError, ConflictError, NotFoundError
from ...database import get_db, AsyncSessionLocal
from ...models import User, Call, CallSyncJob, Candidate, Integration
from ...schemas.call import CallOut, CallSyncJobOut, CallSyncStartResponse
from ...services.audit import audit
from ...services.call_sync import create_call_sync_job, spawn_sync
from ...services.integrations.mango.client import MangoClient
from ...services.integrations.mango.service import get_status as get_mango_status, DEFAULT_BASE_URL
from ...services.settings.crypto import decrypt_text
from ...services.glafira.transcription import transcribe_audio, analyze_call

logger = logging.getLogger(__name__)

router = APIRouter()


# Фоновые задачи расшифровки (защита от GC)
_transcribe_tasks: dict = {}


@router.get("/candidates/{candidate_id}/calls", response_model=List[CallOut])
async def get_candidate_calls(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[CallOut]:
    """Получить звонки кандидата"""
    # Company-scoped доступ
    result = await db.execute(
        select(Call)
        .where(
            and_(
                Call.candidate_id == candidate_id,
                Call.company_id == current_user.company_id
            )
        )
        .order_by(desc(Call.started_at))
    )
    calls = result.scalars().all()

    # Проверяем, что кандидат принадлежит компании
    if calls:
        candidate_result = await db.execute(
            select(Candidate).where(
                and_(
                    Candidate.id == candidate_id,
                    Candidate.company_id == current_user.company_id,
                    Candidate.deleted_at.is_(None)
                )
            )
        )
        if not candidate_result.scalar_one_or_none():
            raise NotFoundError("Кандидат не найден")
    elif candidate_id:
        # Проверяем существование кандидата, даже если звонков нет
        candidate_result = await db.execute(
            select(Candidate).where(
                and_(
                    Candidate.id == candidate_id,
                    Candidate.company_id == current_user.company_id,
                    Candidate.deleted_at.is_(None)
                )
            )
        )
        if not candidate_result.scalar_one_or_none():
            raise NotFoundError("Кандидат не найден")

    return [CallOut.from_call(call) for call in calls]


@router.post("/calls/sync", response_model=CallSyncStartResponse)
async def start_call_sync(
    db: AsyncSession = Depends(get_db),
    _guard: None = Depends(require_recruiter_or_admin),
    current_user: User = Depends(get_current_user),
) -> CallSyncStartResponse:
    """Запустить синхронизацию звонков из Mango Office"""
    # ConflictError (двойной запуск) пробрасывается в единый обработчик ошибок → 409.
    job = await create_call_sync_job(
        db, current_user.company_id, current_user.id
    )

    # Запускаем фоновую задачу
    await spawn_sync(job.id, current_user.company_id)

    return CallSyncStartResponse(job_id=job.id)


@router.get("/calls/sync/jobs/{job_id}", response_model=CallSyncJobOut)
async def get_call_sync_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CallSyncJobOut:
    """Получить статус джоба синхронизации"""
    result = await db.execute(
        select(CallSyncJob).where(
            and_(
                CallSyncJob.id == job_id,
                CallSyncJob.company_id == current_user.company_id
            )
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError("Джоб синхронизации не найден")

    return CallSyncJobOut.model_validate(job)


@router.get("/calls/{call_id}", response_model=CallOut)
async def get_call(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CallOut:
    """Получить информацию о звонке"""
    result = await db.execute(
        select(Call).where(
            and_(
                Call.id == call_id,
                Call.company_id == current_user.company_id
            )
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Звонок не найден")

    return CallOut.from_call(call)


@router.get("/calls/{call_id}/recording")
async def download_call_recording(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Скачать запись звонка"""
    # Проверяем доступ к звонку
    result = await db.execute(
        select(Call).where(
            and_(
                Call.id == call_id,
                Call.company_id == current_user.company_id
            )
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Звонок не найден")

    if not call.recording_id:
        raise NotFoundError("Запись звонка не найдена")

    # Получаем настройки Mango Office
    mango_status = await get_mango_status(db, current_user.company_id)
    if not mango_status.get("configured") or not mango_status.get("verified"):
        raise ValidationError("Mango Office не настроен или не подключен")

    # Читаем ключи и создаем клиент
    integration_result = await db.execute(
        select(Integration).where(
            Integration.company_id == current_user.company_id,
            Integration.provider == "mango"
        )
    )
    integration = integration_result.scalar_one()

    config = integration.config
    api_key = decrypt_text(config["api_key"])
    api_salt = decrypt_text(config["api_salt"])
    base_url = config.get("vpbx_api_url", DEFAULT_BASE_URL)

    client = MangoClient(api_key, api_salt, base_url)

    # Загружаем файл записи (ссылка Mango одноразовая — качаем сразу, не кэшируем URL)
    try:
        audio_bytes = await client.download_recording(call.recording_id)
    except Exception as e:
        logger.error("Failed to download recording %s: %s", call.recording_id, e)
        raise HTTPException(status_code=502, detail="Ошибка загрузки записи")
    finally:
        await client.close()

    def generate():
        yield audio_bytes

    return StreamingResponse(
        generate(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'attachment; filename="call_{call_id}.mp3"'
        }
    )


@router.post("/calls/{call_id}/transcribe", response_model=CallOut)
async def transcribe_call(
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
    _guard: None = Depends(require_recruiter_or_admin),
    current_user: User = Depends(get_current_user),
) -> CallOut:
    """Запустить расшифровку звонка"""
    # Проверяем доступ к звонку
    result = await db.execute(
        select(Call).where(
            and_(
                Call.id == call_id,
                Call.company_id == current_user.company_id
            )
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Звонок не найден")

    if not call.recording_id:
        raise ValidationError("У звонка нет записи для расшифровки")

    # Если расшифровка уже есть, возвращаем как есть (кэш)
    if call.transcript and call.transcribe_status == "done":
        return CallOut.from_call(call)

    # TOCTOU-защита: проверяем статус и атомарно устанавливаем running
    update_result = await db.execute(
        update(Call)
        .where(
            and_(
                Call.id == call_id,
                Call.transcribe_status.in_(["none", "error"])
            )
        )
        .values(transcribe_status="running")
        .returning(Call.id)
    )

    if not update_result.fetchone():
        # Уже выполняется или завершено
        await db.rollback()
        raise ConflictError("Расшифровка уже выполняется или завершена")

    await db.commit()

    # Запускаем фоновую задачу расшифровки
    task = asyncio.create_task(
        _run_transcription(call_id, current_user.company_id)
    )
    task_key = f"transcribe_{call_id}"
    _transcribe_tasks[task_key] = task

    # Очистка задачи по завершению
    def cleanup_task(completed_task):
        _transcribe_tasks.pop(task_key, None)

    task.add_done_callback(cleanup_task)

    # Аудит действия
    await audit(
        db,
        action="call_transcribe_started",
        entity_type="call",
        entity_id=call_id,
        actor_user_id=current_user.id,
        company_id=current_user.company_id,
        actor_type="human",  # запуск инициирует рекрутёр; сам AI-разбор — фоновая задача
    )
    await db.commit()

    # Возвращаем статус "running"
    call.transcribe_status = "running"
    return CallOut.from_call(call)


async def _run_transcription(call_id: UUID, company_id: UUID) -> None:
    """Фоновая задача расшифровки звонка"""
    logger.info("Starting transcription for call %s", call_id)

    async with AsyncSessionLocal() as db:
        try:
            # Получаем звонок
            result = await db.execute(
                select(Call).where(Call.id == call_id)
            )
            call = result.scalar_one()

            # Получаем настройки Mango и ключи
            integration_result = await db.execute(
                select(Integration).where(
                    Integration.company_id == company_id,
                    Integration.provider == "mango"
                )
            )
            integration = integration_result.scalar_one()

            config = integration.config
            api_key = decrypt_text(config["api_key"])
            api_salt = decrypt_text(config["api_salt"])
            base_url = config.get("vpbx_api_url", DEFAULT_BASE_URL)

            client = MangoClient(api_key, api_salt, base_url)

            # Скачиваем аудио (ссылка одноразовая)
            try:
                audio_bytes = await client.download_recording(call.recording_id)
            finally:
                await client.close()

            # Расшифровываем
            transcription_result = await transcribe_audio(audio_bytes, "mp3")

            if not transcription_result["success"]:
                # Ошибка расшифровки
                await db.execute(
                    update(Call)
                    .where(Call.id == call_id)
                    .values(
                        transcribe_status="error",
                        transcribe_error=transcription_result["error"]
                    )
                )
                await db.commit()
                logger.error("Transcription failed for call %s: %s",
                           call_id, transcription_result["error"])
                return

            # Анализируем расшифровку
            analysis_result = await analyze_call(transcription_result["full_text"])

            # Сохраняем результаты
            update_data = {
                "transcribe_status": "done",
                "transcript": transcription_result["full_text"],
                "transcript_segments": transcription_result["segments"],
                "transcribe_error": None,
            }

            if analysis_result:
                update_data.update({
                    "summary": analysis_result["summary"],
                    "ai_hint": analysis_result["hint"],
                    "ai_hint_tone": analysis_result["hint_tone"],
                })

            await db.execute(
                update(Call)
                .where(Call.id == call_id)
                .values(**update_data)
            )
            await db.commit()

            logger.info("Transcription completed successfully for call %s", call_id)

        except Exception as e:
            # Ошибка выполнения
            logger.error("Transcription task failed for call %s: %s",
                        call_id, e, exc_info=True)

            await db.execute(
                update(Call)
                .where(Call.id == call_id)
                .values(
                    transcribe_status="error",
                    transcribe_error=f"Внутренняя ошибка: {str(e)[:200]}"
                )
            )
            await db.commit()