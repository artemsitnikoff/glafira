"""DaData — онлайн-подсказки городов для автокомплита (форма вакансии) и
Clean API для стандартизации данных (верификация).

Использует suggest/address с from/to_bound по населённым пунктам, чтобы подсказки
были именно городами/посёлками, а не улицами/домами.

Clean API стандартизирует и проверяет качество телефонов, email, ФИО.
Авторизация для Clean API — Token + X-Secret (оба ключа нужны).

Если ключ не задан или DaData недоступна — возвращаем graceful None/[]
(не роняем верификацию/форму).
"""

import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
DADATA_CLEAN_URL = "https://cleaner.dadata.ru/api/v1/clean"
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


async def clean_phone(phone: str) -> dict | None:
    """Стандартизация и проверка номера телефона.

    Returns: {phone: str, type: str, provider: str, region: str, qc: int} или None.
    qc: 0=российский валидный, 7=зарубежный валидный, 1=с допущениями, 2=мусор, 3=несколько номеров.
    """
    if not phone or not phone.strip():
        return None

    if not settings.DADATA_API_KEY or not settings.DADATA_SECRET_KEY:
        logger.debug("[dadata] clean_phone: API ключи не настроены")
        return None

    headers = {
        "Authorization": f"Token {settings.DADATA_API_KEY}",
        "X-Secret": settings.DADATA_SECRET_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=DADATA_TIMEOUT) as client:
            resp = await client.post(
                f"{DADATA_CLEAN_URL}/phone",
                json=[phone.strip()],
                headers=headers
            )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[0]
        return None
    except (httpx.HTTPError, ValueError, IndexError) as e:
        logger.warning("[dadata] clean_phone failed: %s: %s", type(e).__name__, e)
        return None


async def clean_email(email: str) -> dict | None:
    """Стандартизация и проверка email адреса.

    Returns: {email: str, type: str, qc: int} или None.
    qc: 0=валидный.
    """
    if not email or not email.strip():
        return None

    if not settings.DADATA_API_KEY or not settings.DADATA_SECRET_KEY:
        logger.debug("[dadata] clean_email: API ключи не настроены")
        return None

    headers = {
        "Authorization": f"Token {settings.DADATA_API_KEY}",
        "X-Secret": settings.DADATA_SECRET_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=DADATA_TIMEOUT) as client:
            resp = await client.post(
                f"{DADATA_CLEAN_URL}/email",
                json=[email.strip()],
                headers=headers
            )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[0]
        return None
    except (httpx.HTTPError, ValueError, IndexError) as e:
        logger.warning("[dadata] clean_email failed: %s: %s", type(e).__name__, e)
        return None


async def clean_name(full_name: str) -> dict | None:
    """Стандартизация и проверка ФИО.

    Returns: {surname: str, name: str, patronymic: str, gender: str, qc: int} или None.
    qc: 0=корректное ФИО.
    """
    if not full_name or not full_name.strip():
        return None

    if not settings.DADATA_API_KEY or not settings.DADATA_SECRET_KEY:
        logger.debug("[dadata] clean_name: API ключи не настроены")
        return None

    headers = {
        "Authorization": f"Token {settings.DADATA_API_KEY}",
        "X-Secret": settings.DADATA_SECRET_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=DADATA_TIMEOUT) as client:
            resp = await client.post(
                f"{DADATA_CLEAN_URL}/name",
                json=[full_name.strip()],
                headers=headers
            )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[0]
        return None
    except (httpx.HTTPError, ValueError, IndexError) as e:
        logger.warning("[dadata] clean_name failed: %s: %s", type(e).__name__, e)
        return None
