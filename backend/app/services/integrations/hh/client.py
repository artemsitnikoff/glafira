"""hh.ru API клиент для OAuth и API вызовов"""

import httpx
from urllib.parse import urlencode

from ....config import settings
from ....core.errors import ValidationError


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


def _check_hh_config():
    """Проверяет конфигурацию hh.ru интеграции"""
    if not settings.HH_CLIENT_ID:
        raise ValidationError("hh.ru не настроен: отсутствует HH_CLIENT_ID")
    if not settings.HH_CLIENT_SECRET:
        raise ValidationError("hh.ru не настроен: отсутствует HH_CLIENT_SECRET")
    if not settings.HH_REDIRECT_URI:
        raise ValidationError("hh.ru не настроен: отсутствует HH_REDIRECT_URI")


async def exchange_code(code: str) -> dict:
    """
    Обменивает authorization_code на токены

    Args:
        code: authorization code от hh.ru

    Returns:
        dict: {access_token, refresh_token, token_type, expires_in}

    Raises:
        ValidationError: при ошибке API или валидации
    """
    _check_hh_config()

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.HH_CLIENT_ID,
        "client_secret": settings.HH_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.HH_REDIRECT_URI
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


async def refresh_tokens(refresh_token: str) -> dict:
    """
    Обновляет токены через refresh_token

    Args:
        refresh_token: refresh token

    Returns:
        dict: {access_token, refresh_token, token_type, expires_in}

    Raises:
        ValidationError: при ошибке API или валидации
    """
    _check_hh_config()

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
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


def build_authorize_url(state: str) -> str:
    """
    Строит URL для авторизации через hh.ru

    Args:
        state: уникальный state для CSRF защиты

    Returns:
        str: полный URL для редиректа в браузер

    Raises:
        ValidationError: если нет конфигурации
    """
    _check_hh_config()

    params = {
        "response_type": "code",
        "client_id": settings.HH_CLIENT_ID,
        "redirect_uri": settings.HH_REDIRECT_URI,
        "state": state,
        "role": "employer",
        "force_role": "true",
        "skip_choose_account": "true"
    }

    return f"{settings.HH_AUTHORIZE_URL}?{urlencode(params)}"