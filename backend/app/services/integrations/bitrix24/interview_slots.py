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
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ....core.errors import AppError
from . import client as b24_client

logger = logging.getLogger(__name__)

# In-memory кэш слотов: token -> (monotonic_ts, slots_list)
_slots_cache: dict[str, tuple[float, list[tuple[datetime, datetime]]]] = {}
_cache_lock = asyncio.Lock()
CACHE_TTL = 60.0  # секунд


def _get_tz(tz_str: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError):
        return ZoneInfo("Europe/Moscow")


def _parse_bitrix_dt(raw) -> datetime | None:
    """Парсит datetime из ответа Б24 в НАИВНЫЙ datetime (локальное время портала).

    Основной формат accessibility — '13.07.2026 09:00:00'; поддержаны и ISO-варианты.
    TZ отбрасывается (как в рабочем ArkadyJarvis) — время трактуется как локальное
    портала, привязка к поясу компании делается вызывающим.
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in (
        "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=None)
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _parse_b24_accessibility(
    raw: dict,
    user_ids: list[int],
    tz: ZoneInfo,
) -> dict[int, list[tuple[datetime, datetime]]]:
    """Парсит ответ calendar.accessibility.get → {b24_user_id: [(from_utc, to_utc)]}.

    Формат Б24 сверен с рабочим ArkadyJarvis: result = {user_id: [ {DATE_FROM, DATE_TO,
    ACCESSIBILITY, ~USER_OFFSET_FROM, ~USER_OFFSET_TO}, ... ]}.
    - поля именно DATE_FROM/DATE_TO (не FROM/TO — прежняя причина «все свободны»);
    - ACCESSIBILITY='free' занятостью НЕ считаем (busy/absent/quest — считаем);
    - время локальное; нормализуем вычитанием ~USER_OFFSET (как ArkadyJarvis), затем
      привязываем к поясу компании tz и переводим в UTC.
    При ошибке разбора конкретного интервала — пропускаем (не считаем занятым).
    """
    result: dict[int, list[tuple[datetime, datetime]]] = {uid: [] for uid in user_ids}
    for uid_str, intervals in (raw or {}).items():
        try:
            uid = int(uid_str)
        except (ValueError, TypeError):
            continue
        result.setdefault(uid, [])
        if not isinstance(intervals, list):
            continue
        for slot in intervals:
            if not isinstance(slot, dict):
                continue
            acc = str(slot.get("ACCESSIBILITY") or "busy").lower()
            if acc == "free":
                continue
            local_from = _parse_bitrix_dt(slot.get("DATE_FROM"))
            local_to = _parse_bitrix_dt(slot.get("DATE_TO"))
            if not local_from or not local_to:
                continue
            try:
                off_from = int(slot.get("~USER_OFFSET_FROM", 0) or 0)
                off_to = int(slot.get("~USER_OFFSET_TO", 0) or 0)
            except (ValueError, TypeError):
                off_from = off_to = 0
            local_from -= timedelta(seconds=off_from)
            local_to -= timedelta(seconds=off_to)
            from_utc = local_from.replace(tzinfo=tz).astimezone(timezone.utc)
            to_utc = local_to.replace(tzinfo=tz).astimezone(timezone.utc)
            if from_utc < to_utc:
                result[uid].append((from_utc, to_utc))
    return result


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


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Сливает пересекающиеся/смежные интервалы. Отсортированный список без пересечений."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda x: x[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _split_into_chunks(
    interval_from: datetime,
    interval_to: datetime,
    chunk_len: timedelta,
    min_chunk: timedelta,
) -> list[tuple[datetime, datetime]]:
    """Режет свободный интервал на куски длиной ≤ chunk_len; хвост короче min_chunk отбрасывает.

    Модель ArkadyJarvis: 09:00–12:00 → 09:00–10:00, 10:00–11:00, 11:00–12:00; окно
    09:00–09:30 → один кусок 09:00–09:30 (30-минутные окна между встречами не теряются).
    """
    chunks: list[tuple[datetime, datetime]] = []
    cursor = interval_from
    while cursor < interval_to:
        nxt = cursor + chunk_len
        chunk_end = min(nxt, interval_to)
        if chunk_end - cursor >= min_chunk:
            chunks.append((cursor, chunk_end))
        cursor = nxt
    return chunks


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

    # Диаг-лог: сырой семпл первого пользователя — чтобы запиннить точный формат
    # полей (DATE_FROM/ACCESSIBILITY/~USER_OFFSET) на живом портале заказчика.
    if isinstance(raw_accessibility, dict) and raw_accessibility:
        try:
            _uid = next(iter(raw_accessibility))
            _lst = raw_accessibility.get(_uid) or []
            logger.info(
                "[interview_slots] accessibility uid=%s count=%s sample=%s",
                _uid, len(_lst) if isinstance(_lst, list) else "n/a",
                (_lst[0] if isinstance(_lst, list) and _lst else None),
            )
        except Exception:
            pass

    busy = _parse_b24_accessibility(raw_accessibility, b24_user_ids, tz)

    # Парсим рабочее время (часы приёма в поясе компании)
    try:
        work_start_h, work_start_m = (int(x) for x in work_start.split(":"))
        work_end_h, work_end_m = (int(x) for x in work_end.split(":"))
    except (ValueError, AttributeError):
        work_start_h, work_start_m = 9, 0
        work_end_h, work_end_m = 19, 0

    # Занятость ВСЕХ участников объединяем (слот свободен, только если свободны ВСЕ).
    all_busy: list[tuple[datetime, datetime]] = []
    for uid in b24_user_ids:
        all_busy.extend(busy.get(uid, []))
    merged_busy = _merge_intervals(all_busy)

    chunk_len = timedelta(minutes=duration_min)   # длина куска (по умолчанию 60 мин)
    min_chunk = timedelta(minutes=step_min)        # мин. хвост (30 мин) — 30-минутные окна не теряются

    # Свободные интервалы по дням = рабочее окно минус занятость, режем на куски
    free_slots: list[tuple[datetime, datetime]] = []
    current_day_local = from_local.date()
    end_day_local = to_local.date()

    while current_day_local <= end_day_local:
        if current_day_local.isoweekday() in work_days:  # 1=пн..7=вс
            day_start = datetime(
                current_day_local.year, current_day_local.month, current_day_local.day,
                work_start_h, work_start_m, 0, tzinfo=tz,
            ).astimezone(timezone.utc)
            day_end = datetime(
                current_day_local.year, current_day_local.month, current_day_local.day,
                work_end_h, work_end_m, 0, tzinfo=tz,
            ).astimezone(timezone.utc)

            # окно дня с учётом лид-времени и горизонта
            win_start = max(day_start, window_from)
            win_end = min(day_end, window_to)
            if win_start < win_end:
                day_busy = _merge_intervals([
                    (max(bf, win_start), min(bt, win_end))
                    for bf, bt in merged_busy
                    if bt > win_start and bf < win_end
                ])
                # свободные интервалы = окно минус занятость → куски
                cursor = win_start
                for bf, bt in day_busy:
                    if cursor < bf:
                        free_slots.extend(_split_into_chunks(cursor, bf, chunk_len, min_chunk))
                    cursor = max(cursor, bt)
                if cursor < win_end:
                    free_slots.extend(_split_into_chunks(cursor, win_end, chunk_len, min_chunk))

        current_day_local += timedelta(days=1)

    # Обновляем кэш
    if token_cache_key:
        async with _cache_lock:
            _slots_cache[token_cache_key] = (time.monotonic(), free_slots)

    return free_slots


def invalidate_cache(token: str) -> None:
    """Инвалидирует кэш слотов для токена."""
    _slots_cache.pop(token, None)
