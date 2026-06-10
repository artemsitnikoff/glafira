"""Клиент для работы с Potok.io API"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
import httpx

from ....config import settings
from ....core.errors import ValidationError, NotFoundError, ConflictError

logger = logging.getLogger(__name__)


class PotokAPIError(Exception):
    """Базовая ошибка Potok API"""
    pass


class PotokAuthError(PotokAPIError):
    """Ошибка аутентификации Potok"""
    pass


class PotokSubscriptionError(PotokAPIError):
    """Ошибка подписки Potok"""
    pass


class PotokRateLimitError(PotokAPIError):
    """Ошибка превышения rate limit Potok"""
    pass


async def _handle_potok_error(response: httpx.Response):
    """Обработка ошибок Potok API с преобразованием в доменные ошибки"""
    try:
        error_data = response.json() if response.content else {}
    except Exception:
        error_data = {}

    error_message = error_data.get('message', f"HTTP {response.status_code}")

    if response.status_code == 401:
        raise ValidationError("Поток отклонил токен (проверьте, что токен активен и даёт доступ на чтение кандидатов)")
    elif response.status_code == 402:
        raise ConflictError("Подписка Потока просрочена")
    elif response.status_code == 429:
        raise ValidationError("Превышен лимит запросов к Потоку (100 запросов за 10 секунд)")
    elif response.status_code >= 500:
        raise ValidationError("Сервер Потока недоступен, попробуйте позже")
    else:
        raise ValidationError(f"Ошибка Потока: {error_message}")


async def _retry_request(func, *args, max_retries=3, **kwargs):
    """Ретраи с экспоненциальным backoff для 429/5xx ошибок"""
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            if "лимит запросов" in str(e) and attempt < max_retries - 1:
                # 429 rate limit - ждем и повторяем
                wait_time = (2 ** attempt) * 1
                logger.warning(f"Rate limit Потока, повтор через {wait_time}с")
                await asyncio.sleep(wait_time)
                continue
            elif "недоступен" in str(e) and attempt < max_retries - 1:
                # 5xx server error - ждем и повторяем
                wait_time = (2 ** attempt) * 2
                logger.warning(f"Сервер Потока недоступен, повтор через {wait_time}с")
                await asyncio.sleep(wait_time)
                continue
            else:
                raise


async def list_applicants(token: str, page: int = 1, per_page: int = 100) -> Dict[str, Any]:
    """
    Получение списка кандидатов из Potok.io

    ВНИМАНИЕ: Реальный ответ API пинится на токене заказчика. Структура может отличаться
    от OpenAPI спеки при реальных запросах.

    Args:
        token: API токен Potok.io
        page: номер страницы (начиная с 1)
        per_page: количество записей на странице (макс 100)

    Returns:
        Ответ API с массивом кандидатов и пагинацией

    Raises:
        ValidationError: при ошибках токена, подписки, rate limit или сети
    """
    if not token or not token.strip():
        raise ValidationError("Токен Потока обязателен")

    if page < 1:
        page = 1
    if per_page > 100:
        per_page = 100

    url = f"{settings.POTOK_API_BASE}/applicants.json"
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "User-Agent": "Glafira/1.0 (glafira.dclouds.ru)"
    }
    params = {
        "page": page,
        "per_page": per_page
    }

    async def _make_request():
        try:
            async with httpx.AsyncClient(timeout=settings.POTOK_TIMEOUT) as client:
                response = await client.get(url, headers=headers, params=params)

                if not response.is_success:
                    await _handle_potok_error(response)

                return response.json()

        except httpx.TimeoutException:
            raise ValidationError("Не удалось связаться с Потоком (таймаут)")
        except httpx.NetworkError:
            raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")
        except httpx.HTTPStatusError as e:
            await _handle_potok_error(e.response)
        except Exception as e:
            if isinstance(e, (ValidationError, ConflictError)):
                raise
            logger.error(f"Неожиданная ошибка при запросе к Potok: {e}")
            raise ValidationError("Не удалось связаться с Потоком")

    return await _retry_request(_make_request)


async def test_connection(token: str) -> bool:
    """
    Тестирование соединения с Potok API

    Args:
        token: API токен

    Returns:
        True если соединение успешное, False иначе
    """
    try:
        # Запрашиваем первую страницу с минимальным количеством записей
        result = await list_applicants(token, page=1, per_page=1)
        return True
    except Exception:
        return False