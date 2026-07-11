"""Расчёт свободных слотов для записи на интервью через Б24-календарь.

TZ-дисциплина:
- Всё хранится и передаётся в UTC (aware datetime).
- Рабочие часы считаются в TZ компании (zoneinfo).
- Б24 принимает datetime как строку; передаём UTC-строку (Б24 интерпретирует по TZ вебхука —
  на практике удобнее передавать в «локальном» TZ компании и указывать timezone в событии;
  accessibility.get принимает строку без TZ → передаём в TZ компании).
- Слоты отдаются клиенту как UTC + tz компании (клиент конвертирует для отображения).
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .....core.errors import AppError
from . import client as b24_client

# In-memory кэш слотов: token -> (monotonic_ts, slots_list)
_slots_cache: dict[str, tuple[float, list[tuple[datetime, datetime]]]] = {}
_cache_lock = asyncio.Lock()
CACHE_TTL = 60.0  # секунд


def _get_tz(tz_str: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError):
        return ZoneInfo("Europe/Moscow")


def _parse_b24_accessibility(
    raw: dict,
    user_ids: list[int],
    tz: ZoneInfo,
) -> dict[int, list[tuple[datetime, datetime]]]:
    """Парсит ответ calendar.accessibility.get.

    Возвращает dict: b24_user_id -> list[(from_utc, to_utc)] занятых интервалов.
    При ошибке парсинга конкретного интервала — пропускает (conservative: не считаем занятым).
    """
    result: dict[int, list[tuple[datetime, datetime]]] = {uid: [] for uid in user_ids}
    for uid_str, intervals in (raw or {}).items():
        try:
            uid = int(uid_str)
        except (ValueError, TypeError):
            continue
        if uid not in result:
            result[uid] = []
        if not isinstance(intervals, list):
            continue
        for interval in intervals:
            try:
                from_raw = interval.get("FROM") or interval.get("from") or ""
                to_raw = interval.get("TO") or interval.get("to") or ""
                # Б24 отдаёт строки в формате 'YYYY-MM-DDTHH:MM:SS+TZ' или 'YYYY-MM-DD HH:MM:SS'
                from_dt = _parse_b24_datetime(from_raw, tz)
                to_dt = _parse_b24_datetime(to_raw, tz)
                if from_dt and to_dt and from_dt < to_dt:
                    result[uid].append((from_dt, to_dt))
            except Exception:
                continue
    return result


def _parse_b24_datetime(raw: str, tz: ZoneInfo) -> datetime | None:
    """Парсит строку datetime от Б24. Возвращает None при ошибке."""
    if not raw:
        return None
    raw = raw.strip()
    # Попытка 1: ISO с таймзоной
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    # Попытка 2: 'YYYY-MM-DD HH:MM:SS' без TZ → считаем в TZ компании
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw[:len(fmt)], fmt)
            dt = dt.replace(tzinfo=tz)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _slot_is_free(
    slot_from: datetime,
    slot_to: datetime,
    busy: dict[int, list[tuple[datetime, datetime]]],
    user_ids: list[int],
) -> bool:
    """True если слот свободен у ВСЕХ участников."""
    for uid in user_ids:
        for busy_from, busy_to in busy.get(uid, []):
            # Пересечение: слот не свободен если занятость начинается до конца слота
            # и заканчивается после начала слота
            if busy_from < slot_to and busy_to > slot_from:
                return False
    return True


async def calculate_free_slots(
    webhook_url: str,
    b24_user_ids: list[int],
    *,
    tz_str: str,
    work_days: list[int],
    work_start: str,
    work_end: str,
    duration_min: int,
    step_min: int,
    horizon_days: int,
    lead_hours: int,
    token_cache_key: str | None = None,
) -> list[tuple[datetime, datetime]]:
    """Рассчитывает список свободных слотов для записи на интервью.

    Алгоритм:
    1. Запрашивает занятость всех b24_user_ids через calendar.accessibility.get.
    2. Строит сетку слотов в рабочие дни/часы в TZ компании.
    3. Возвращает слоты, свободные у ВСЕХ участников, список (from_utc, to_utc).

    ВАЖНО: при любой ошибке Б24 — бросает AppError (НЕ возвращает пустой список).
    """
    if not b24_user_ids:
        raise AppError(
            code="B24_NOT_MAPPED",
            message="Не указаны участники интервью с b24_user_id",
            status_code=503,
        )

    tz = _get_tz(tz_str)
    now_utc = datetime.now(timezone.utc)
    # Начало окна — сейчас + lead_hours
    window_from = now_utc + timedelta(hours=lead_hours)
    # Конец окна — сейчас + horizon_days
    window_to = now_utc + timedelta(days=horizon_days)

    # Проверяем кэш
    if token_cache_key:
        async with _cache_lock:
            cached = _slots_cache.get(token_cache_key)
            if cached:
                ts, slots = cached
                if time.monotonic() - ts < CACHE_TTL:
                    return slots

    # Форматируем datetime для Б24 в TZ компании (accessibility.get принимает локальное время)
    from_local = window_from.astimezone(tz)
    to_local = window_to.astimezone(tz)
    date_from_str = from_local.strftime("%Y-%m-%d %H:%M:%S")
    date_to_str = to_local.strftime("%Y-%m-%d %H:%M:%S")

    # Запрашиваем занятость — fail-closed: ошибка → 503, не пустые слоты
    try:
        raw_accessibility = await b24_client.get_accessibility(
            webhook_url, b24_user_ids, date_from_str, date_to_str
        )
    except AppError:
        raise
    except Exception as e:
        raise AppError(
            code="B24_CALENDAR_ERROR",
            message=f"Ошибка получения занятости из Б24: {e}",
            status_code=503,
        )

    busy = _parse_b24_accessibility(raw_accessibility, b24_user_ids, tz)

    # Парсим рабочее время
    try:
        work_start_h, work_start_m = (int(x) for x in work_start.split(":"))
        work_end_h, work_end_m = (int(x) for x in work_end.split(":"))
    except (ValueError, AttributeError):
        work_start_h, work_start_m = 10, 0
        work_end_h, work_end_m = 18, 0

    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=step_min)

    # Генерируем сетку слотов
    free_slots: list[tuple[datetime, datetime]] = []

    # Итерируем по дням в окне
    current_day_local = from_local.date()
    end_day_local = to_local.date()

    while current_day_local <= end_day_local:
        # Проверяем рабочий день (1=пн..7=вс, совпадает с isoweekday())
        isowd = current_day_local.isoweekday()  # 1=пн, 7=вс
        if isowd in work_days:
            # Начало и конец рабочего дня в TZ компании (aware)
            day_start = datetime(
                current_day_local.year, current_day_local.month, current_day_local.day,
                work_start_h, work_start_m, 0, tzinfo=tz,
            )
            day_end = datetime(
                current_day_local.year, current_day_local.month, current_day_local.day,
                work_end_h, work_end_m, 0, tzinfo=tz,
            )

            slot_start = max(day_start, window_from.astimezone(tz))
            # Выравниваем до следующего step_min
            if slot_start > day_start:
                minutes_into_day = (slot_start.hour * 60 + slot_start.minute) - (work_start_h * 60 + work_start_m)
                if minutes_into_day % step_min != 0:
                    aligned_minutes = ((minutes_into_day // step_min) + 1) * step_min
                    slot_start = day_start + timedelta(minutes=aligned_minutes)

            while True:
                slot_end = slot_start + duration
                if slot_end > day_end:
                    break
                # Конец окна
                if slot_start.astimezone(timezone.utc) >= window_to:
                    break

                slot_from_utc = slot_start.astimezone(timezone.utc)
                slot_to_utc = slot_end.astimezone(timezone.utc)

                if _slot_is_free(slot_from_utc, slot_to_utc, busy, b24_user_ids):
                    free_slots.append((slot_from_utc, slot_to_utc))

                slot_start += step

        current_day_local += timedelta(days=1)

    # Обновляем кэш
    if token_cache_key:
        async with _cache_lock:
            _slots_cache[token_cache_key] = (time.monotonic(), free_slots)

    return free_slots


def invalidate_cache(token: str) -> None:
    """Инвалидирует кэш слотов для токена."""
    _slots_cache.pop(token, None)
