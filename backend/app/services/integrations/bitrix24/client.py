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

    Параметры date_from/date_to: строка 'YYYY-MM-DD HH:MM:SS' в указанном TZ.
    Возвращает event id как строку.

    Scope: calendar.
    """
    params: dict = {
        "type": "user",
        "ownerId": host,
        "name": name,
        "description": description,
        "location": location,
        "dateFrom": date_from,
        "dateTo": date_to,
        "timezone": tz,
        "is_meeting": "Y",
        "accessibility": "busy",
        "attendees": [str(uid) for uid in attendees],
        "host": host,
    }
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
