"""HTTP-клиент Хабр Карьера (изолированный модуль).

⚠️⚠️ ВСЕ эндпоинты/поля API Хабра в этом файле являются ASSUMPTION (предположением):
документация API Хабр Карьера находится за стеной одобрения приложения и НЕ подтверждена.
Метки «# ⚠️ ASSUMPTION» проставлены на каждом вызове и описании полей.

ПОСЛЕ получения одобрения приложения Хабром:
1. Запросить реальную документацию API у Хабр Карьера.
2. Проверить каждый эндпоинт/поле, помеченный ASSUMPTION.
3. Пинить реальные значения в .env (HABR_API_BASE) и обновить константы ниже.
4. Убрать/скорректировать пометки ASSUMPTION.

Секреты (access_token) НЕ логируются нигде в этом модуле.
"""
import logging
from typing import Any

import httpx

from ....config import settings

logger = logging.getLogger(__name__)

# ⚠️ ASSUMPTION — ПУТЬ /employer/responses — типичное соглашение
# для откликов на вакансию работодателя. Реальный path НЕ подтверждён.
# Пиннинг по реальному ответу с одобренным приложением.
_PATH_VACANCY_RESPONSES = "/employer/responses"

# ⚠️ ASSUMPTION — ПУТЬ /resumes/{resume_ref} — типичный REST-идиом.
# Реальный path (и имя поля-ссылки на резюме в отклике) НЕ подтверждены.
_PATH_RESUME = "/resumes/{resume_ref}"

# ⚠️ ASSUMPTION — ПУТЬ /employer/vacancies — типичный REST-идиом
# для списка вакансий работодателя. Реальный path НЕ подтверждён.
_PATH_EMPLOYER_VACANCIES = "/employer/vacancies"

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
        # Ограничиваем длину тела, чтобы не логировать потенциально большой HTML
        body_preview = resp.text[:300] if resp.text else "(пустой ответ)"
        logger.warning(
            "[habr] %s: HTTP %d — %.300s",
            context,
            resp.status_code,
            body_preview,
        )
        raise ValueError(
            f"Хабр Карьера вернул HTTP {resp.status_code} при {context}. "
            f"Возможно, токен протух или приложение не одобрено Хабром. "
            f"Пиннинг эндпоинтов требует одобренного приложения."
        )

    try:
        return resp.json()
    except Exception as exc:
        logger.warning("[habr] %s: не-JSON ответ (возможно HTML) — %s", context, exc)
        raise ValueError(
            f"Хабр Карьера вернул непarseable ответ при {context}. "
            f"Скорее всего, это HTML-страница ошибки, а не JSON API. "
            f"Эндпоинты требуют пиннинга с одобренным приложением."
        ) from exc


async def get_vacancy_responses(
    access_token: str,
    habr_vacancy_id: str,
    page: int = 0,
    per_page: int = 50,
) -> dict[str, Any]:
    """Отклики работодателя на конкретную вакансию Хабр Карьера.

    # ⚠️ ASSUMPTION — эндпоинт, параметры пагинации и структура ответа НЕ подтверждены.
    # Предположение: GET {HABR_API_BASE}/employer/responses?vacancy_id={id}&page={p}&per_page={n}
    # Ожидаемый ответ: {items: [...отклики...], total: N, page: P, per_page: N}
    # Пиннинг по реальному ответу с одобренным приложением.

    Returns:
        dict: raw ответ Хабра (items, total, ...). Пустой items[] = откликов нет.

    Raises:
        ValueError: HTTP >= 400, не-JSON, сетевая ошибка.
    """
    base = settings.HABR_API_BASE
    url = f"{base}{_PATH_VACANCY_RESPONSES}"

    # ⚠️ ASSUMPTION — имена query-параметров: vacancy_id, page, per_page
    params = {
        "vacancy_id": habr_vacancy_id,
        "page": page,
        "per_page": per_page,
    }

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_make_headers(access_token), params=params)
    except httpx.HTTPError as exc:
        logger.warning("[habr] get_vacancy_responses network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении откликов Хабра: {exc}") from exc

    return _check_response(resp, f"получение откликов вакансии {habr_vacancy_id}")


async def get_resume(
    access_token: str,
    resume_ref: str,
) -> dict[str, Any]:
    """Полное резюме кандидата по ссылке/идентификатору из отклика.

    # ⚠️ ASSUMPTION — resume_ref может быть как числовым ID, так и URL.
    # Предположение: GET {HABR_API_BASE}/resumes/{resume_ref}
    # Пиннинг: проверить поле в response_item, указывающее на резюме (url? id?).
    # Ожидаемый ответ: dict с полями резюме (имя, опыт, навыки, город, контакты, ...).

    Returns:
        dict: raw резюме. Маппинг полей — в _habr_resume_to_normalized() в sync.py.

    Raises:
        ValueError: HTTP >= 400, не-JSON, сетевая ошибка.
    """
    base = settings.HABR_API_BASE

    # ⚠️ ASSUMPTION — resume_ref — ID резюме (число или slug), подставляется в путь.
    # Если Хабр использует абсолютный URL в отклике — нужно дёргать напрямую,
    # а не строить из base+path. Пиннинг после одобрения.
    if resume_ref.startswith("http"):
        # Если ссылка абсолютная — используем как есть (ASSUMPTION)
        url = resume_ref
    else:
        url = f"{base}{_PATH_RESUME.format(resume_ref=resume_ref)}"

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_make_headers(access_token))
    except httpx.HTTPError as exc:
        logger.warning("[habr] get_resume network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении резюме Хабра: {exc}") from exc

    return _check_response(resp, f"получение резюме {resume_ref}")


async def get_employer_vacancies(
    access_token: str,
    page: int = 0,
    per_page: int = 50,
) -> dict[str, Any]:
    """Список вакансий работодателя на Хабр Карьере (для UI-связывания).

    # ⚠️ ASSUMPTION — эндпоинт, параметры и структура ответа НЕ подтверждены.
    # Предположение: GET {HABR_API_BASE}/employer/vacancies?page={p}&per_page={n}
    # Ожидаемый ответ: {items: [{id, title, city, ...}, ...], total: N}
    # Пиннинг по реальному ответу с одобренным приложением.

    Returns:
        dict: raw ответ Хабра (items, total, ...).

    Raises:
        ValueError: HTTP >= 400, не-JSON, сетевая ошибка.
    """
    base = settings.HABR_API_BASE
    url = f"{base}{_PATH_EMPLOYER_VACANCIES}"

    # ⚠️ ASSUMPTION — имена query-параметров: page, per_page
    params = {"page": page, "per_page": per_page}

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_make_headers(access_token), params=params)
    except httpx.HTTPError as exc:
        logger.warning("[habr] get_employer_vacancies network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении вакансий Хабра: {exc}") from exc

    return _check_response(resp, "получение вакансий работодателя")
