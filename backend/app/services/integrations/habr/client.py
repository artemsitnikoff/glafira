"""HTTP-клиент Хабр Карьера (изолированный модуль).

Эндпоинты подтверждены документацией API Хабр Карьера:
  BASE = https://career.habr.com/v1/integrations  (конфигурируемый HABR_API_BASE)

Секреты (access_token) НЕ логируются нигде в этом модуле.
"""
import logging
from typing import Any

import httpx

from ....config import settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


def _make_headers(access_token: str) -> dict[str, str]:
    """Заголовки для API-запросов Хабр Карьера (Bearer-токен, НЕ логировать)."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def _check_response(resp: httpx.Response, context: str) -> dict[str, Any]:
    """Проверяет HTTP-статус и парсит JSON.

    Raises:
        ValueError: если статус >= 400 (с описанием ошибки) или ответ не JSON.

    Токен/секрет НЕ включается в сообщение об ошибке.
    """
    if resp.status_code >= 400:
        body_preview = resp.text[:300] if resp.text else "(пустой ответ)"
        logger.warning(
            "[habr] %s: HTTP %d — %.300s",
            context,
            resp.status_code,
            body_preview,
        )
        raise ValueError(
            f"Хабр Карьера вернул HTTP {resp.status_code} при {context}."
        )

    try:
        return resp.json()
    except Exception as exc:
        logger.warning("[habr] %s: не-JSON ответ — %s", context, exc)
        raise ValueError(
            f"Хабр Карьера вернул непarseable ответ при {context}."
        ) from exc


async def get_vacancy_responses(
    access_token: str,
    vacancy_id: str,
    page: int = 1,
) -> dict[str, Any]:
    """Отклики работодателя на конкретную вакансию.

    GET {BASE}/vacancies/{vacancy_id}/responses?page={page}

    Ответ: { responses: [...], pagination: {total, page, per} }

    Returns:
        dict: raw ответ Хабра (responses, pagination).

    Raises:
        ValueError: HTTP >= 400, не-JSON, сетевая ошибка.
    """
    base = settings.HABR_API_BASE
    url = f"{base}/vacancies/{vacancy_id}/responses"

    params: dict[str, Any] = {"page": page}

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_make_headers(access_token), params=params)
    except httpx.HTTPError as exc:
        logger.warning("[habr] get_vacancy_responses network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении откликов Хабра: {exc}") from exc

    return _check_response(resp, f"получение откликов вакансии {vacancy_id}")


async def get_employer_vacancies(access_token: str) -> dict[str, Any]:
    """Список вакансий работодателя.

    GET {BASE}/vacancies

    Returns:
        dict: raw ответ Хабра.

    Raises:
        ValueError: HTTP >= 400, не-JSON, сетевая ошибка.
    """
    base = settings.HABR_API_BASE
    url = f"{base}/vacancies"

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_make_headers(access_token))
    except httpx.HTTPError as exc:
        logger.warning("[habr] get_employer_vacancies network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении вакансий Хабра: {exc}") from exc

    return _check_response(resp, "получение вакансий работодателя")


async def get_user_profile(access_token: str, login: str) -> dict[str, Any]:
    """Полный профиль пользователя (БЕСПЛАТНО).

    GET {BASE}/users/{login}

    Богаче, чем данные в response.user: содержит experiences[], university_educations[],
    salary{from,currency}, resume_headline, skills[], contacts{} (если открыты).

    Returns:
        dict: raw профиль пользователя.

    Raises:
        ValueError: HTTP >= 400, не-JSON, сетевая ошибка.
    """
    base = settings.HABR_API_BASE
    url = f"{base}/users/{login}"

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_make_headers(access_token))
    except httpx.HTTPError as exc:
        logger.warning("[habr] get_user_profile network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении профиля Хабра: {exc}") from exc

    return _check_response(resp, f"получение профиля пользователя {login}")


async def get_user_contacts(access_token: str, login: str) -> dict[str, Any]:
    """Контакты пользователя.

    ⚠️ ПЛАТНО: каждый вызов = открытие контактов, списывается лимит компании.
    Вызывать ТОЛЬКО явно по действию пользователя (кнопка «Открыть контакты»).
    НЕ вызывать автоматически в poll/sync.

    GET {BASE}/users/{login}/contacts

    При ошибке/исчерпанном лимите — кидает ValueError наверх для честной обработки
    (НЕ глотать ошибку, НЕ помечать контакты как открытые).

    Returns:
        dict: raw контакты пользователя.

    Raises:
        ValueError: HTTP >= 400 (включая лимит), не-JSON, сетевая ошибка.
    """
    base = settings.HABR_API_BASE
    url = f"{base}/users/{login}/contacts"

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_make_headers(access_token))
    except httpx.HTTPError as exc:
        logger.warning("[habr] get_user_contacts network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении контактов Хабра: {exc}") from exc

    return _check_response(resp, f"открытие контактов пользователя {login}")
