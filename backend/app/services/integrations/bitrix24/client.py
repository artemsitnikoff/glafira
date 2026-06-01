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
            details={"status": resp.status_code, "body": resp.text[:300]},
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
            details={"body": resp.text[:300]},
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
