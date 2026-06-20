"""HTTP-клиент Авито Работа Job API (изолированный модуль).

Эндпоинты подтверждены Swagger Авито Job API:
  BASE = https://api.avito.ru  (конфигурируемый AVITO_API_BASE)
  TOKEN = https://api.avito.ru/token  (конфигурируемый AVITO_TOKEN_URL)

⚠️ Секреты (client_secret, access_token) НЕ логируются нигде в этом модуле.

OAuth: client_credentials (НЕ браузерный флоу) — каждая компания
передаёт свой client_id/secret, получает токен автоматически.
"""
import logging
from typing import Any, Optional

import httpx

from ....config import settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


def _make_headers(token: str, employee_of: Optional[str] = None) -> dict[str, str]:
    """Заголовки для Job API запросов (Bearer токен, НЕ логировать)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if employee_of:
        headers["X-Employee-Of"] = employee_of
    return headers


def _check_response(resp: httpx.Response, context: str) -> dict[str, Any]:
    """Проверяет HTTP-статус и парсит JSON.

    Raises:
        ValueError: если статус >= 400 (с описанием ошибки) или ответ не JSON.

    Секреты/токены НЕ включаются в сообщение об ошибке.
    """
    if resp.status_code == 402:
        body_preview = resp.text[:300] if resp.text else "(пустой ответ)"
        logger.warning("[avito] %s: HTTP 402 — %.300s", context, body_preview)
        raise ValueError(
            f"Авито вернул HTTP 402 при {context}. "
            "Проверьте подписку/доступ к Job API Авито."
        )
    if resp.status_code == 429:
        body_preview = resp.text[:200] if resp.text else "(пустой ответ)"
        logger.warning("[avito] %s: HTTP 429 (rate limit) — %.200s", context, body_preview)
        raise ValueError(
            f"Авито вернул HTTP 429 (лимит запросов) при {context}. "
            "Повторите позже."
        )
    if resp.status_code >= 400:
        body_preview = resp.text[:300] if resp.text else "(пустой ответ)"
        logger.warning(
            "[avito] %s: HTTP %d — %.300s",
            context,
            resp.status_code,
            body_preview,
        )
        raise ValueError(
            f"Авито вернул HTTP {resp.status_code} при {context}."
        )

    try:
        return resp.json()
    except Exception as exc:
        logger.warning("[avito] %s: не-JSON ответ — %s", context, exc)
        raise ValueError(
            f"Авито вернул непarseable ответ при {context}."
        ) from exc


async def get_access_token(client_id: str, client_secret: str) -> dict[str, Any]:
    """Получить OAuth client_credentials токен Авито.

    POST https://api.avito.ru/token  (form-encoded)
    Body: grant_type=client_credentials&client_id=...&client_secret=...

    Ответ: {access_token, expires_in, token_type}

    ⚠️ client_secret НЕ логируется.

    Raises:
        ValueError: HTTP >= 400, не-JSON, сетевая ошибка.
    """
    url = settings.AVITO_TOKEN_URL
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, data=data)
    except httpx.HTTPError as exc:
        # client_secret НЕ в логе
        logger.warning("[avito] get_access_token: сетевая ошибка — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении токена Авито: {exc}") from exc

    return _check_response(resp, "получение client_credentials токена")


async def get_application_ids(
    token: str,
    *,
    date_from: str,
    cursor: Optional[str] = None,
    vacancy_ids: Optional[list[str]] = None,
    state: Optional[str] = None,
    employee_of: Optional[str] = None,
) -> dict[str, Any]:
    """Получить идентификаторы откликов.

    GET /job/v1/applications/get_ids
    Query: updatedAtFrom (YYYY-MM-DD), cursor, vacancyIds (comma), state.

    Ответ: {applies:[{id, state, created_at, updated_at}], ...}
    Пагинация: cursor из ответа для следующей страницы.

    Raises:
        ValueError: HTTP >= 400, сетевая ошибка.
    """
    base = settings.AVITO_API_BASE
    url = f"{base}/job/v1/applications/get_ids"

    params: dict[str, Any] = {"updatedAtFrom": date_from}
    if cursor:
        params["cursor"] = cursor
    if vacancy_ids:
        params["vacancyIds"] = ",".join(vacancy_ids)
    if state:
        params["state"] = state

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                url,
                headers=_make_headers(token, employee_of),
                params=params,
            )
    except httpx.HTTPError as exc:
        logger.warning("[avito] get_application_ids network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении id откликов Авито: {exc}") from exc

    return _check_response(resp, "получение id откликов")


async def get_applications_by_ids(
    token: str,
    ids: list[str],
    employee_of: Optional[str] = None,
) -> dict[str, Any]:
    """Получить детали откликов по списку id (до 100 за запрос).

    POST /job/v1/applications/get_by_ids
    Body: {ids: [...]}

    Ответ: {applies:[{id, vacancy_id, created_at, state,
                      applicant:{data:{first_name,last_name,patronymic,...}, resume_id},
                      contacts:{phones:[{value}], chat:{value}},
                      enriched_properties:{phone:{value}, experience, age, citizenship}}]}

    Телефон содержится в отклике БЕСПЛАТНО — не нужно дёргать /contacts.

    Raises:
        ValueError: HTTP >= 400, сетевая ошибка.
    """
    base = settings.AVITO_API_BASE
    url = f"{base}/job/v1/applications/get_by_ids"

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers=_make_headers(token, employee_of),
                json={"ids": ids},
            )
    except httpx.HTTPError as exc:
        logger.warning("[avito] get_applications_by_ids network error — %s", exc)
        raise ValueError(f"Сетевая ошибка при получении откликов Авито: {exc}") from exc

    return _check_response(resp, f"получение деталей откликов ({len(ids)} шт.)")


async def get_resume_v2(
    token: str,
    resume_id: str,
    employee_of: Optional[str] = None,
) -> dict[str, Any]:
    """Получить резюме кандидата (Resume 2.0, обогащение).

    GET /job/v2/resumes/{resume_id}

    Ответ: {experience_list[{work_start, work_finish, company, position, responsibilities}],
             education_list[], language_list[], salary, schedule, description, ...}

    Используется для опционального обогащения секций резюме кандидата.
    Best-effort — при сбое вызывающий код НЕ должен падать.

    Raises:
        ValueError: HTTP >= 400, сетевая ошибка.
    """
    base = settings.AVITO_API_BASE
    url = f"{base}/job/v2/resumes/{resume_id}"

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                url,
                headers=_make_headers(token, employee_of),
            )
    except httpx.HTTPError as exc:
        logger.warning("[avito] get_resume_v2 network error resume_id=%s — %s", resume_id, exc)
        raise ValueError(f"Сетевая ошибка при получении резюме Авито {resume_id}: {exc}") from exc

    return _check_response(resp, f"получение резюме {resume_id}")
