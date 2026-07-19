"""Клиент Битрикс24 REST через ВХОДЯЩИЙ ВЕБХУК.

URL вебхука (из офиц. доки apidocs.bitrix24.com):
    https://{портал}/rest/{user_id}/{secret_code}/
Метод вызывается как `{webhook_base}{method}.json` (POST, JSON-тело параметров —
чтобы секрет/параметры не светились в query/логах).

Формат ответа: {"result": ..., "total": N, "next": M, "time": {...}}.
Формат ошибки: {"error": "...", "error_description": "..."} (как правило с не-2xx).

Эндпоинты НЕ выдуманы — взяты из доки:
- user.get (scope `user`): список сотрудников, пагинация start/next/total, поле ACTIVE.
- department.get (scope `department`): оргструктура (опционально).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from ....core.errors import AppError

B24_TIMEOUT = 20  # сек


def normalize_base(webhook_url: str) -> str:
    """Гарантирует ровно один завершающий слэш у базового URL вебхука."""
    return webhook_url.strip().rstrip("/") + "/"


async def call(webhook_url: str, method: str, params: dict | None = None) -> dict:
    """Вызывает один REST-метод Битрикс24. Бросает AppError с честным кодом при сбое."""
    base = normalize_base(webhook_url)
    url = f"{base}{method}.json"

    try:
        async with httpx.AsyncClient(timeout=B24_TIMEOUT) as client:
            resp = await client.post(url, json=params or {})
    except httpx.TimeoutException as e:
        raise AppError(
            code="B24_TIMEOUT",
            message="Таймаут подключения к Битрикс24 (проверьте URL вебхука)",
            status_code=400,
            details={"reason": str(e)},
        )
    except httpx.RequestError as e:
        raise AppError(
            code="B24_CONNECT_ERROR",
            message="Не удалось подключиться к порталу Битрикс24 (проверьте URL вебхука)",
            status_code=400,
            details={"reason": str(e)},
        )

    # Битрикс24 на ошибке отдаёт JSON {error, error_description}
    try:
        data = resp.json()
    except Exception:
        raise AppError(
            code="B24_BAD_RESPONSE",
            message="Битрикс24 вернул не-JSON ответ",
            status_code=400,
            details={"status": resp.status_code},
        )

    if isinstance(data, dict) and data.get("error"):
        b24_code = str(data.get("error"))
        desc = data.get("error_description") or b24_code
        raise AppError(
            code="B24_API_ERROR",
            message=f"Битрикс24: {desc}",
            status_code=400,
            details={"b24_error": b24_code},
        )

    if resp.status_code >= 400:
        raise AppError(
            code="B24_API_ERROR",
            message=f"Битрикс24 вернул HTTP {resp.status_code}",
            status_code=400,
            details={"status": resp.status_code},
        )

    return data


async def get_users_page(webhook_url: str, start: int = 0) -> dict:
    """Одна страница user.get (до 50 записей). Возвращает сырой ответ B24."""
    return await call(webhook_url, "user.get", {"start": start})


async def get_all_users(webhook_url: str, max_items: int = 5000) -> list[dict]:
    """Все сотрудники постранично (user.get, пагинация по next). С backstop-лимитом."""
    items: list[dict] = []
    start = 0
    while True:
        data = await get_users_page(webhook_url, start)
        batch = data.get("result") or []
        items.extend(batch)

        nxt = data.get("next")
        if nxt is None or not batch:
            break
        start = int(nxt)
        if len(items) >= max_items:
            break

    return items


async def get_departments(webhook_url: str) -> list[dict]:
    """Отделы организации (department.get). Возвращает сырой результат B24."""
    data = await call(webhook_url, "department.get", {})
    return data.get("result") or []


def _valid_iana_tz(name) -> str | None:
    """Возвращает name, если это валидное IANA-имя часового пояса, иначе None."""
    if not name or not isinstance(name, str):
        return None
    try:
        ZoneInfo(name)
        return name
    except Exception:
        return None


def _offset_from_iso(iso_dt) -> str | None:
    """Из ISO-строки с оффсетом ('2026-07-12T14:00:00+07:00') делает IANA-имя
    фиксированного пояса 'Etc/GMT∓N'.

    Знак в Etc/GMT ИНВЕРТИРОВАН по стандарту POSIX: UTC+7 → 'Etc/GMT-7'. Россия не
    переходит на летнее время, поэтому фикс-оффсет для сетки слотов (горизонт ~2 недели)
    корректен. Получасовые пояса Etc/GMT не выражает → None (упадём в дефолт).
    """
    if not iso_dt or not isinstance(iso_dt, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_dt)
    except (ValueError, TypeError):
        return None
    off = dt.utcoffset()
    if off is None:
        return None
    total = int(off.total_seconds())
    if total % 3600 != 0:
        return None
    hours = total // 3600
    name = f"Etc/GMT{'-' if hours >= 0 else '+'}{abs(hours)}"
    return _valid_iana_tz(name)


async def resolve_interview_tz(webhook_url: str, recruiter_b24_id: int | None) -> tuple[str, dict]:
    """Определяет часовой пояс сетки слотов записи на интервью ИЗ Битрикс24.

    Приоритет: TIME_ZONE ответственного рекрутёра (IANA-имя из профиля) → пояс портала
    из служебного блока `time.date_start` ответа REST → 'Europe/Moscow'.

    Возвращает (tz_name, debug). debug логируется вызывающим — семантику полей Б24
    (TIME_ZONE/TIME_ZONE_OFFSET/date_start) пиннить на живом портале заказчика.

    Scope: user.
    """
    debug: dict = {"recruiter_b24_id": recruiter_b24_id}
    params = {"ID": recruiter_b24_id} if recruiter_b24_id else {}
    try:
        data = await call(webhook_url, "user.get", params)
    except AppError as e:
        debug["error"] = e.code
        return "Europe/Moscow", debug

    results = data.get("result") or []
    if results:
        u = results[0]
        debug["TIME_ZONE"] = u.get("TIME_ZONE")
        debug["TIME_ZONE_OFFSET"] = u.get("TIME_ZONE_OFFSET")
        iana = _valid_iana_tz(u.get("TIME_ZONE"))
        if iana:
            debug["source"] = "recruiter_TIME_ZONE"
            return iana, debug

    # Фолбэк: пояс портала из служебного блока time ответа REST (= настройка портала,
    # обычно совпадает с городом компании).
    tblock = data.get("time") or {}
    server_start = tblock.get("date_start")
    debug["server_date_start"] = server_start
    portal_tz = _offset_from_iso(server_start)
    if portal_tz:
        debug["source"] = "portal_time"
        return portal_tz, debug

    debug["source"] = "default_moscow"
    return "Europe/Moscow", debug


# ──────────────────────────────────────────────────────────────────────────────
# Calendar-методы для записи на интервью
# ──────────────────────────────────────────────────────────────────────────────

async def get_current_user_b24(webhook_url: str) -> dict:
    """user.current — текущий пользователь вебхука. Используется для проверки прав.

    Scope: user. Бросает AppError если вебхуку не хватает прав.
    """
    data = await call(webhook_url, "user.current", {})
    result = data.get("result")
    if not isinstance(result, dict):
        raise AppError(
            code="B24_UNEXPECTED_RESPONSE",
            message="Битрикс24 вернул неожиданный ответ на user.current",
            status_code=400,
        )
    return result


async def find_user_by_email(webhook_url: str, email: str) -> dict | None:
    """Ищет пользователя Б24 по email. Возвращает первый совпадающий или None.

    Scope: user.
    """
    data = await call(webhook_url, "user.get", {"filter": {"EMAIL": email}})
    results = data.get("result") or []
    return results[0] if results else None


async def get_accessibility(
    webhook_url: str,
    user_ids: list[int],
    date_from: str,
    date_to: str,
) -> dict:
    """calendar.accessibility.get — занятость пользователей Б24.

    Параметры date_from/date_to в формате 'YYYY-MM-DD HH:MM:SS' (локальный TZ портала)
    или ISO. Возвращает сырой dict ответа (ключи — строковые user_id, значения —
    list[{from, to}] занятых интервалов).

    Scope: calendar.
    Бросает AppError при ошибке (НЕ возвращает пустой dict — fail-closed).
    """
    # ВАЖНО: тело уходит как JSON (client.post(json=params)), поэтому массив передаём
    # под ПЛОСКИМ ключом "users" — скобочная нотация "users[]" валидна только для
    # url-encoded форм; в JSON Битрикс получил бы буквальный ключ "users[]" и не
    # смапил бы его на параметр users → метод не видел участников (пустое расписание).
    params: dict = {
        "users": [str(uid) for uid in user_ids],
        "from": date_from,
        "to": date_to,
    }
    data = await call(webhook_url, "calendar.accessibility.get", params)
    result = data.get("result")
    if result is None:
        # Б24 не вернул result — считаем ошибкой (не можем знать занятость → fail-closed)
        raise AppError(
            code="B24_CALENDAR_ERROR",
            message="Битрикс24 не вернул данные занятости (calendar.accessibility.get)",
            status_code=503,
        )
    return result if isinstance(result, dict) else {}


async def add_calendar_event(
    webhook_url: str,
    *,
    name: str,
    date_from: str,
    date_to: str,
    tz: str,
    attendees: list[int],
    host: int,
    description: str,
    location: str,
    section: int | None = None,
) -> str:
    """calendar.event.add — создаёт событие-встречу в Б24.

    Формат параметров сверен с рабочим ArkadyJarvis: from/to (а не dateFrom/dateTo),
    timezone_from/timezone_to, встреча через is_meeting/host/attendees/meeting.
    date_from/date_to: строка '%d.%m.%Y %H:%M:%S' в поясе tz. Возвращает event id.

    Scope: calendar.
    """
    params: dict = {
        "type": "user",
        "ownerId": host,
        "name": name,
        "description": description,
        "from": date_from,
        "to": date_to,
        "timezone_from": tz,
        "timezone_to": tz,
    }
    if location:
        params["location"] = location
    if attendees:
        # host первым, без дублей — как в эталоне
        all_ids = [host] + [aid for aid in attendees if aid != host]
        params.update({
            "is_meeting": "Y",
            "accessibility": "busy",
            "host": host,
            "attendees": [str(uid) for uid in all_ids],
            "meeting": {"notify": True, "open": False, "reinvite": False},
        })
    if section is not None:
        params["sectionId"] = section

    data = await call(webhook_url, "calendar.event.add", params)
    result = data.get("result")
    if result is None:
        raise AppError(
            code="B24_CALENDAR_ERROR",
            message="Битрикс24 не вернул id созданного события",
            status_code=503,
        )
    return str(result)


async def delete_calendar_event(
    webhook_url: str,
    *,
    event_id: str,
    owner_id: int,
) -> None:
    """calendar.event.delete — удаляет событие-встречу в Б24.

    Применяется при отмене интервью кандидатом: событие должно исчезнуть из календарей
    команды, иначе рекрутёр придёт на несуществующую встречу.
    owner_id — тот же, что был host при создании (calendar.event.add).

    Scope: calendar. Бросает AppError (из call) при сбое — вызывающий решает,
    fail-soft это или нет.
    """
    await call(
        webhook_url,
        "calendar.event.delete",
        {"id": event_id, "ownerId": owner_id, "type": "user"},
    )


async def create_videoconference(
    webhook_url: str,
    title: str,
    user_ids: list[int] | None = None,
) -> str | None:
    """Создаёт видеоконференцию Битрикс24 и возвращает публичную /video/-ссылку.

    Механизм (проверен на живом портале): конференция = чат `ENTITY_TYPE=VIDEOCONF`.
    `im.chat.add` создаёт его, `im.dialog.get` отдаёт `result.public.link` = ссылку
    вида https://{портал}/video/{code}. Внешний кандидат заходит по ней как гость.

    Scope: `im`. Graceful: любой сбой → None (бронь не валим — откат на фолбэк-ссылку).
    """
    add_params: dict = {
        "TYPE": "CHAT",
        "TITLE": (title or "Интервью")[:255],
        "ENTITY_TYPE": "VIDEOCONF",
    }

    # Всё внутри try + широкий except: функция обещает «любой сбой → None» (бронь не
    # валим). Коэрсинг user_ids тоже внутри — нечисловой id не должен пробить наружу.
    try:
        if user_ids:
            add_params["USERS"] = [int(uid) for uid in user_ids]
        add = await call(webhook_url, "im.chat.add", add_params)
        chat_id = add.get("result")
        if chat_id is None:
            return None
        dlg = await call(webhook_url, "im.dialog.get", {"DIALOG_ID": f"chat{chat_id}"})
    except (AppError, ValueError, TypeError):
        return None
    public = (dlg.get("result") or {}).get("public") or {}
    link = public.get("link")
    return link if isinstance(link, str) and link.strip() else None
