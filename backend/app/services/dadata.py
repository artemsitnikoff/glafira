"""DaData — онлайн-подсказки городов для автокомплита (форма вакансии).

Использует suggest/address с from/to_bound по населённым пунктам, чтобы подсказки
были именно городами/посёлками, а не улицами/домами. Авторизация — Token (только
DADATA_API_KEY; secret для suggestions не нужен — он для Clean API стандартизации).

Если ключ не задан или DaData недоступна — возвращаем [] (поле остаётся
свободным вводом, без падений).
"""

import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
DADATA_TIMEOUT = 8


async def suggest_cities(query: str, count: int = 8) -> list[dict]:
    """Подсказки городов по строке ввода. Возвращает [{value, label, region}].

    value — чистое имя города (пишем в vacancy.city); label — что показываем
    в выпадашке (с типом и регионом для уточнения).
    """
    q = (query or "").strip()
    if not q or not settings.DADATA_API_KEY:
        return []

    headers = {
        "Authorization": f"Token {settings.DADATA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "query": q,
        "count": count,
        # Ограничиваем гранулярность городом..населённым пунктом (не улицы/дома).
        "from_bound": {"value": "city"},
        "to_bound": {"value": "settlement"},
    }

    try:
        async with httpx.AsyncClient(timeout=DADATA_TIMEOUT) as client:
            resp = await client.post(DADATA_SUGGEST_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        # Сетевой сбой/невалидный ответ DaData — не роняем форму, просто без подсказок.
        logger.warning("[dadata] suggest_cities failed: %s: %s", type(e).__name__, e)
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for s in data.get("suggestions", []):
        d = s.get("data") or {}
        # Город федерального значения (Москва/СПб/Севастополь) живёт в region.
        city = d.get("city") or d.get("settlement") or d.get("region")
        if not city:
            continue
        label = s.get("value") or city
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "value": city,
            "label": label,
            "region": d.get("region_with_type"),
        })
    return out
