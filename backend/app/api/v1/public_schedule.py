"""Публичные эндпоинты записи на интервью (БЕЗ авторизации).

Кандидат получает ссылку /schedule/{token} (фронт) и взаимодействует с тремя
эндпоинтами ниже. company_id определяется ТОЛЬКО из токена (lookup InterviewLink).

Rate-limit: in-memory best-effort, 30 req/min per IP:token. X-Forwarded-For учитывается.

TZ: слоты хранятся и передаются в UTC, tz компании передаётся строкой для клиента.
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models import (
    Application, Candidate, Company, Integration, InterviewLink, User, Vacancy, VacancyTeam, Event
)
from ...services.audit import audit
from ...services.integrations.bitrix24 import client as b24_client
from ...services.integrations.bitrix24.interview_slots import (
    calculate_free_slots, invalidate_cache,
)
from ...services.integrations.smtp.service import send_email
from ...services.settings.crypto import decrypt_text
from ...core.errors import AppError

logger = logging.getLogger(__name__)

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Rate limiter (in-memory, best-effort)
# ──────────────────────────────────────────────────────────────────────────────
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = asyncio.Lock()
_RATE_LIMIT = 30  # запросов
_RATE_WINDOW = 60.0  # секунд


async def _check_rate_limit(request: Request, token: str) -> None:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    key = f"{ip}:{token}"
    now = time.monotonic()

    async with _rate_lock:
        timestamps = [t for t in _rate_store[key] if now - t < _RATE_WINDOW]
        if len(timestamps) >= _RATE_LIMIT:
            _rate_store[key] = timestamps
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "RATE_LIMITED", "message": "Слишком много запросов. Попробуйте позже."}},
            )
        timestamps.append(now)
        _rate_store[key] = timestamps


# ──────────────────────────────────────────────────────────────────────────────
# Схемы
# ──────────────────────────────────────────────────────────────────────────────

class ParticipantOut(BaseModel):
    name: str
    avatar_url: str | None = None


class ScheduleInfoResponse(BaseModel):
    status: str  # 'active' | 'booked' | 'expired'
    vacancy_name: str
    recruiter_name: str
    participants: list[ParticipantOut]
    tz: str
    slot_from: datetime | None = None
    slot_to: datetime | None = None


class SlotOut(BaseModel):
    from_utc: datetime
    to_utc: datetime


class SlotsResponse(BaseModel):
    slots: list[SlotOut]
    tz: str


class BookRequest(BaseModel):
    slot_from: datetime  # UTC
    slot_to: datetime    # UTC


class BookResponse(BaseModel):
    status: str
    slot_from: datetime
    slot_to: datetime
    video_link: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────────────

async def _get_link_or_raise(session: AsyncSession, token: str) -> InterviewLink:
    """Загружает InterviewLink по токену. 404 без деталей (не раскрывать company/candidate)."""
    link = (await session.execute(
        select(InterviewLink).where(InterviewLink.token == token)
    )).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Ссылка не найдена"}})
    return link


async def _check_not_expired(link: InterviewLink) -> None:
    """Проверяет срок действия ссылки. 410 если истёкла или уже забронирована."""
    now = datetime.now(timezone.utc)
    if link.status == "expired" or (link.status == "active" and link.expires_at < now):
        raise HTTPException(status_code=410, detail={"error": {"code": "LINK_EXPIRED", "message": "Срок ссылки истёк"}})
    if link.status == "booked":
        raise HTTPException(status_code=410, detail={"error": {"code": "ALREADY_BOOKED", "message": "Слот уже забронирован"}})


def _get_slot_settings(b24_row: Integration) -> dict:
    cfg = b24_row.config or {}
    return {
        "work_days": cfg.get("work_days", [1, 2, 3, 4, 5]),
        "work_start": cfg.get("work_start", "10:00"),
        "work_end": cfg.get("work_end", "18:00"),
        "duration_min": int(cfg.get("duration_min", 60)),
        "step_min": int(cfg.get("step_min", 30)),
        "horizon_days": int(cfg.get("horizon_days", 14)),
        "lead_hours": int(cfg.get("lead_hours", 24)),
        "tz": cfg.get("tz", "Europe/Moscow"),
        "interview_video_link": cfg.get("interview_video_link", ""),
    }


async def _load_context(session: AsyncSession, link: InterviewLink):
    """Загружает application, vacancy (с командой), candidate, b24 integration."""
    app = (await session.execute(
        select(Application).where(Application.id == link.application_id)
    )).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Заявка не найдена"}})

    vacancy = (await session.execute(
        select(Vacancy)
        .where(Vacancy.id == app.vacancy_id)
        .options(selectinload(Vacancy.team).selectinload(VacancyTeam.user))
    )).scalar_one_or_none()
    if not vacancy:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Вакансия не найдена"}})

    candidate = (await session.execute(
        select(Candidate).where(Candidate.id == app.candidate_id)
    )).scalar_one_or_none()

    b24_row = (await session.execute(
        select(Integration).where(
            Integration.provider == "bitrix24",
            Integration.company_id == link.company_id,
        )
    )).scalar_one_or_none()

    return app, vacancy, candidate, b24_row


def _collect_participants(vacancy: Vacancy) -> list[User]:
    """Собирает уникальных участников команды вакансии."""
    seen_ids = set()
    participants: list[User] = []
    for vt in (vacancy.team or []):
        if vt.user and vt.user_id not in seen_ids:
            participants.append(vt.user)
            seen_ids.add(vt.user_id)
    return participants


def _get_recruiter(vacancy: Vacancy) -> User | None:
    """Ответственный за вакансию (первый is_responsible или первый в команде)."""
    for vt in (vacancy.team or []):
        if vt.is_responsible and vt.user:
            return vt.user
    for vt in (vacancy.team or []):
        if vt.user:
            return vt.user
    return None


def _collect_b24_user_ids(vacancy: Vacancy) -> tuple[list[int], list[str]]:
    """Возвращает (b24_user_ids, unmapped_names) для всех участников."""
    b24_ids: list[int] = []
    unmapped: list[str] = []
    for vt in (vacancy.team or []):
        if vt.user:
            if vt.user.b24_user_id:
                b24_ids.append(vt.user.b24_user_id)
            else:
                unmapped.append(vt.user.full_name)
    return b24_ids, unmapped


# ──────────────────────────────────────────────────────────────────────────────
# Эндпоинты
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/schedule/{token}", response_model=ScheduleInfoResponse)
async def get_schedule_info(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Информация о ссылке записи на интервью.

    Отдаёт: статус, название вакансии, ФИО рекрутёра, участники (имя + avatar),
    TZ компании. БЕЗ телефонов/emails/внутренних ID кандидата.
    """
    await _check_rate_limit(request, token)

    link = await _get_link_or_raise(session, token)

    # Expired — check time too
    now = datetime.now(timezone.utc)
    if link.status == "active" and link.expires_at < now:
        link.status = "expired"
        await session.commit()

    app, vacancy, candidate, b24_row = await _load_context(session, link)

    slot_settings = _get_slot_settings(b24_row) if b24_row else {}
    tz = slot_settings.get("tz", "Europe/Moscow")

    recruiter = _get_recruiter(vacancy)
    participants = _collect_participants(vacancy)

    return ScheduleInfoResponse(
        status=link.status,
        vacancy_name=vacancy.name,
        recruiter_name=recruiter.full_name if recruiter else "",
        participants=[
            ParticipantOut(name=u.full_name, avatar_url=u.avatar_url)
            for u in participants
        ],
        tz=tz,
        slot_from=link.slot_from,
        slot_to=link.slot_to,
    )


@router.get("/schedule/{token}/slots", response_model=SlotsResponse)
async def get_schedule_slots(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Список свободных слотов для записи.

    Б24 недоступен / нет прав / участники не замаплены → 503 (НЕ пустой список).
    """
    await _check_rate_limit(request, token)

    link = await _get_link_or_raise(session, token)

    # Только active
    now = datetime.now(timezone.utc)
    if link.status == "active" and link.expires_at < now:
        link.status = "expired"
        await session.commit()
        raise HTTPException(
            status_code=410,
            detail={"error": {"code": "LINK_EXPIRED", "message": "Срок ссылки истёк"}},
        )
    if link.status != "active":
        raise HTTPException(
            status_code=410,
            detail={"error": {"code": "LINK_INACTIVE", "message": f"Ссылка недействительна (статус: {link.status})"}},
        )

    app, vacancy, candidate, b24_row = await _load_context(session, link)

    if not b24_row or not (b24_row.config or {}).get("webhook_url"):
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "B24_NOT_CONFIGURED", "message": "Битрикс24 не настроен"}},
        )

    slot_settings = _get_slot_settings(b24_row)
    tz = slot_settings["tz"]

    b24_ids, unmapped = _collect_b24_user_ids(vacancy)
    if unmapped:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "B24_NOT_MAPPED",
                    "message": f"Участники без b24_user_id: {', '.join(unmapped)}",
                }
            },
        )
    if not b24_ids:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "B24_NOT_MAPPED", "message": "Нет участников с b24_user_id"}},
        )

    webhook_url = decrypt_text(b24_row.config["webhook_url"])

    try:
        free_slots = await calculate_free_slots(
            webhook_url,
            b24_ids,
            tz_str=tz,
            work_days=slot_settings["work_days"],
            work_start=slot_settings["work_start"],
            work_end=slot_settings["work_end"],
            duration_min=slot_settings["duration_min"],
            step_min=slot_settings["step_min"],
            horizon_days=slot_settings["horizon_days"],
            lead_hours=slot_settings["lead_hours"],
            token_cache_key=token,
        )
    except AppError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": e.code, "message": e.message}},
        )
    except Exception as e:
        logger.error("[public_schedule] ошибка расчёта слотов token=%s: %s", token, e)
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "B24_CALENDAR_ERROR", "message": "Ошибка получения расписания"}},
        )

    return SlotsResponse(
        slots=[SlotOut(from_utc=s[0], to_utc=s[1]) for s in free_slots],
        tz=tz,
    )


@router.post("/schedule/{token}/book", response_model=BookResponse)
async def book_schedule_slot(
    token: str,
    body: BookRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Бронирование слота. Перепроверяет занятость (анти-гонка) перед созданием события."""
    await _check_rate_limit(request, token)

    link = await _get_link_or_raise(session, token)
    await _check_not_expired(link)

    app, vacancy, candidate, b24_row = await _load_context(session, link)

    if not b24_row or not (b24_row.config or {}).get("webhook_url"):
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "B24_NOT_CONFIGURED", "message": "Битрикс24 не настроен"}},
        )

    slot_settings = _get_slot_settings(b24_row)
    tz = slot_settings["tz"]
    video_link = slot_settings.get("interview_video_link", "")

    b24_ids, unmapped = _collect_b24_user_ids(vacancy)
    if unmapped:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "B24_NOT_MAPPED", "message": f"Не замаплены: {', '.join(unmapped)}"}},
        )

    webhook_url = decrypt_text(b24_row.config["webhook_url"])

    # Нормализуем slot_from/slot_to в UTC-aware
    slot_from = body.slot_from
    slot_to = body.slot_to
    if slot_from.tzinfo is None:
        slot_from = slot_from.replace(tzinfo=timezone.utc)
    else:
        slot_from = slot_from.astimezone(timezone.utc)
    if slot_to.tzinfo is None:
        slot_to = slot_to.replace(tzinfo=timezone.utc)
    else:
        slot_to = slot_to.astimezone(timezone.utc)

    # АНТИ-ГОНКА: перепроверяем занятость этого конкретного слота
    from zoneinfo import ZoneInfo
    try:
        tz_info = ZoneInfo(tz)
    except Exception:
        tz_info = ZoneInfo("Europe/Moscow")

    from_local_str = slot_from.astimezone(tz_info).strftime("%Y-%m-%d %H:%M:%S")
    to_local_str = slot_to.astimezone(tz_info).strftime("%Y-%m-%d %H:%M:%S")

    try:
        raw_accessibility = await b24_client.get_accessibility(
            webhook_url, b24_ids, from_local_str, to_local_str
        )
    except AppError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": e.code, "message": e.message}},
        )

    # Проверяем пересечение
    from ...services.integrations.bitrix24.interview_slots import (
        _parse_b24_accessibility, _slot_is_free,
    )
    busy = _parse_b24_accessibility(raw_accessibility, b24_ids, tz_info)
    if not _slot_is_free(slot_from, slot_to, busy, b24_ids):
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "SLOT_TAKEN", "message": "Этот слот только что заняли. Выберите другое время."}},
        )

    # Определяем host (ответственный рекрутёр)
    recruiter = _get_recruiter(vacancy)
    host_b24_id = recruiter.b24_user_id if recruiter and recruiter.b24_user_id else (b24_ids[0] if b24_ids else 0)

    # Формируем описание события
    candidate_name = candidate.full_name if candidate else "Кандидат"
    event_name = f"Интервью: {vacancy.name} — {candidate_name}"
    event_description = (
        f"Вакансия: {vacancy.name}\n"
        f"Кандидат: {candidate_name}\n"
    )
    if video_link:
        event_description += f"Видеовстреча: {video_link}\n"

    # Строки для Б24 в TZ компании
    date_from_b24 = slot_from.astimezone(tz_info).strftime("%Y-%m-%d %H:%M:%S")
    date_to_b24 = slot_to.astimezone(tz_info).strftime("%Y-%m-%d %H:%M:%S")

    # АТОМАРНЫЙ ЗАХВАТ токена (active→booked) ПЕРЕД созданием события: два запроса на
    # ОДИН токен (двойной клик / ретрай) → второй получит 0 строк → 409, событие
    # создаст только первый. При сбое Б24 ниже статус откатывается на 'active'.
    claim = await session.execute(
        update(InterviewLink)
        .where(InterviewLink.token == token, InterviewLink.status == "active")
        .values(status="booked")
        .returning(InterviewLink.id)
    )
    if claim.first() is None:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "SLOT_TAKEN", "message": "Ссылка уже забронирована."}},
        )
    await session.flush()

    try:
        b24_event_id = await b24_client.add_calendar_event(
            webhook_url,
            name=event_name,
            date_from=date_from_b24,
            date_to=date_to_b24,
            tz=tz,
            attendees=b24_ids,
            host=host_b24_id,
            description=event_description,
            location=video_link or "",
        )
    except AppError as e:
        # Откат захвата — Б24 не создал событие, слот снова доступен.
        await session.execute(
            update(InterviewLink).where(InterviewLink.token == token).values(status="active")
        )
        await session.flush()
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": e.code, "message": e.message}},
        )

    # Сохраняем бронь
    now = datetime.now(timezone.utc)
    link.status = "booked"
    link.slot_from = slot_from
    link.slot_to = slot_to
    link.b24_event_id = b24_event_id
    link.booked_at = now
    await session.flush()

    # Инвалидируем кэш слотов
    invalidate_cache(token)

    # Подтверждение кандидату по email
    if candidate and candidate.email:
        try:
            from zoneinfo import ZoneInfo as _ZI
            _tz = _ZI(tz)
            slot_local = slot_from.astimezone(_tz)
            slot_str = slot_local.strftime("%d.%m.%Y %H:%M") + f" ({tz})"
            body_text = (
                f"Здравствуйте, {candidate.full_name or 'уважаемый кандидат'}!\n\n"
                f"Интервью по вакансии «{vacancy.name}» подтверждено.\n"
                f"Время: {slot_str}\n"
            )
            if video_link:
                body_text += f"Ссылка на встречу: {video_link}\n"

            await send_email(
                session,
                link.company_id,
                to=candidate.email,
                subject=f"Интервью подтверждено: {vacancy.name}",
                body_text=body_text,
            )
        except Exception as e:
            logger.warning("[public_schedule] Не удалось отправить подтверждение кандидату: %s", e)

    # Event + audit
    slot_text = slot_from.strftime("%Y-%m-%d %H:%M UTC")
    session.add(Event(
        company_id=link.company_id,
        type="interview",
        actor_type="system",
        actor_user_id=None,
        text=f"Встреча назначена: {slot_text}. Кандидат: {candidate_name}, вакансия: {vacancy.name}.",
        entities=[],
        candidate_id=candidate.id if candidate else None,
        vacancy_id=vacancy.id,
    ))
    await audit(
        session,
        action="interview_booked",
        entity_type="application",
        entity_id=app.id,
        after={
            "slot_from": slot_from.isoformat(),
            "slot_to": slot_to.isoformat(),
            "b24_event_id": b24_event_id,
            "candidate_id": str(candidate.id) if candidate else None,
            "vacancy_id": str(vacancy.id),
        },
        actor_user_id=None,
        actor_type="system",
        company_id=link.company_id,
    )
    await session.commit()

    return BookResponse(
        status="booked",
        slot_from=slot_from,
        slot_to=slot_to,
        video_link=video_link or None,
    )
