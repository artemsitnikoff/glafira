"""hh.ru API клиент для OAuth и API вызовов"""

import logging

import httpx
from urllib.parse import urlencode

from ....config import settings
from ....core.errors import ValidationError

logger = logging.getLogger(__name__)


def _get_client() -> httpx.AsyncClient:
    """Создает async HTTP клиент с таймаутами и User-Agent"""
    timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0
    )

    headers = {
        "User-Agent": settings.HH_USER_AGENT
    }

    return httpx.AsyncClient(timeout=timeout, headers=headers)


def _check_credentials(client_id: str, client_secret: str, redirect_uri: str):
    """Проверяет переданные credentials"""
    if not client_id:
        raise ValidationError("hh.ru не настроен: отсутствует client_id")
    if not client_secret:
        raise ValidationError("hh.ru не настроен: отсутствует client_secret")
    if not redirect_uri:
        raise ValidationError("hh.ru не настроен: отсутствует redirect_uri")


async def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    """
    Обменивает authorization_code на токены

    Args:
        code: authorization code от hh.ru
        client_id: ID приложения hh.ru
        client_secret: секрет приложения hh.ru
        redirect_uri: redirect URI приложения hh.ru

    Returns:
        dict: {access_token, refresh_token, token_type, expires_in}

    Raises:
        ValidationError: при ошибке API или валидации
    """
    _check_credentials(client_id, client_secret, redirect_uri)

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri
    }

    async with _get_client() as client:
        try:
            response = await client.post(
                settings.HH_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            result = response.json()

            # Проверяем обязательные поля в ответе
            required_fields = ["access_token", "refresh_token", "token_type", "expires_in"]
            for field in required_fields:
                if field not in result:
                    raise ValidationError(f"Ответ hh.ru не содержит поле {field}")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка обмена кода hh.ru: {e}")


async def refresh_tokens(refresh_token: str, client_id: str, client_secret: str) -> dict:
    """
    Обновляет токены через refresh_token

    Args:
        refresh_token: refresh token
        client_id: ID приложения hh.ru
        client_secret: секрет приложения hh.ru

    Returns:
        dict: {access_token, refresh_token, token_type, expires_in}

    Raises:
        ValidationError: при ошибке API или валидации
    """
    if not client_id or not client_secret:
        raise ValidationError("hh.ru не настроен: отсутствует client_id или client_secret")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }

    async with _get_client() as client:
        try:
            response = await client.post(
                settings.HH_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            result = response.json()

            # Проверяем обязательные поля в ответе
            required_fields = ["access_token", "refresh_token", "token_type", "expires_in"]
            for field in required_fields:
                if field not in result:
                    raise ValidationError(f"Ответ hh.ru не содержит поле {field}")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка обновления токенов hh.ru: {e}")


async def get_me(access_token: str) -> dict:
    """
    Получает информацию о текущем пользователе/менеджере

    Args:
        access_token: access token

    Returns:
        dict: данные пользователя с employer.id

    Raises:
        ValidationError: при ошибке API или валидации
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            result = response.json()

            # Базовая проверка структуры ответа
            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru /me")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения данных пользователя hh.ru: {e}")


async def get_employer_vacancies(access_token: str, employer_id: str, page: int = 0, per_page: int = 50) -> dict:
    """
    Получает активные вакансии работодателя

    Args:
        access_token: access token
        employer_id: ID работодателя на hh.ru
        page: страница (0-based)
        per_page: количество записей на странице

    Returns:
        dict: список вакансий {items: [...], pages, page, ...}

    Raises:
        ValidationError: при ошибке API
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/vacancies",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "employer_id": employer_id,
                    "page": page,
                    "per_page": per_page
                }
            )
            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru /vacancies")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения вакансий hh.ru: {e}")


async def get_negotiation_collections(access_token: str, vacancy_id: str) -> list[dict]:
    """Список коллекций откликов работодателя по вакансии.

    hh для работодателя на /negotiations?vacancy_id отдаёт КОЛЛЕКЦИИ по статусам
    (response/consider/interview/discard/…), у каждой свой url для получения откликов.
    ⚠️ Требует доступа работодателя к откликам на hh.ru.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with _get_client() as client:
        try:
            r = await client.get(
                f"{settings.HH_API_BASE}/negotiations",
                headers=headers,
                params={"vacancy_id": vacancy_id},
            )
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения коллекций откликов hh.ru: {e}")
        if r.status_code >= 400:
            raise ValidationError(f"hh.ru ошибка (коллекции, HTTP {r.status_code}): {r.text[:200]}")
        data = r.json()
        if not isinstance(data, dict):
            raise ValidationError("Некорректный формат ответа hh.ru /negotiations")
        return data.get("collections") or []


async def get_collection_page(access_token: str, url: str, page: int = 0, per_page: int = 50) -> dict:
    """Одна страница откликов коллекции по её url. Возвращает {items, found, pages, ...}."""
    headers = {"Authorization": f"Bearer {access_token}"}
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}page={page}&per_page={per_page}"
    async with _get_client() as client:
        try:
            r = await client.get(full, headers=headers)
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения откликов hh.ru: {e}")
        if r.status_code >= 400:
            raise ValidationError(f"hh.ru ошибка (отклики, HTTP {r.status_code}): {r.text[:200]}")
        data = r.json()
        if not isinstance(data, dict):
            raise ValidationError("Некорректный формат откликов hh.ru")
        return data


async def get_negotiation_responses(access_token: str, vacancy_id: str, page: int = 0, per_page: int = 50) -> dict:
    """Отклики коллекции 'response' (обёртка — используется cron-джобом)."""
    collections = await get_negotiation_collections(access_token, vacancy_id)
    resp = next((c for c in collections if c.get("id") == "response"), None)
    if not resp:
        return {"items": [], "found": 0, "pages": 0}
    url = resp.get("url") or f"{settings.HH_API_BASE}/negotiations/response?vacancy_id={vacancy_id}"
    return await get_collection_page(access_token, url, page, per_page)


async def get_resume(access_token: str, resume_url: str) -> dict:
    """Полное резюме по его url (из отклика). В отличие от краткого resume в списке
    откликов, содержит опыт с описанием, образование, возраст и контакты
    (контакты — если hh их открыл/оплачены)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with _get_client() as client:
        try:
            r = await client.get(resume_url, headers=headers)
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения резюме hh.ru: {e}")
        if r.status_code >= 400:
            raise ValidationError(f"hh.ru ошибка (резюме, HTTP {r.status_code}): {r.text[:200]}")
        data = r.json()
        if not isinstance(data, dict):
            raise ValidationError("Некорректный формат резюме hh.ru")
        return data


async def publish_vacancy(access_token: str, payload: dict) -> dict:
    """
    Публикует вакансию на hh.ru

    ⚠️  НЕ проверено без реального токена hh.ru

    Args:
        access_token: access token
        payload: данные вакансии в формате hh.ru API

    Returns:
        dict: ответ с id созданной вакансии

    Raises:
        ValidationError: при ошибке API
    """
    async with _get_client() as client:
        try:
            response = await client.post(
                f"{settings.HH_API_BASE}/vacancies",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru POST /vacancies")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка публикации вакансии hh.ru: {e}")


def build_authorize_url(state: str, client_id: str, redirect_uri: str) -> str:
    """
    Строит URL для авторизации через hh.ru

    Args:
        state: уникальный state для CSRF защиты
        client_id: ID приложения hh.ru
        redirect_uri: redirect URI приложения hh.ru

    Returns:
        str: полный URL для редиректа в браузер

    Raises:
        ValidationError: если нет конфигурации
    """
    if not client_id or not redirect_uri:
        raise ValidationError("hh.ru не настроен: отсутствует client_id или redirect_uri")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "role": "employer",
        "force_role": "true",
        "skip_choose_account": "true"
    }

    return f"{settings.HH_AUTHORIZE_URL}?{urlencode(params)}"