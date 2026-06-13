"""Mango VPBX API клиент.

Реализует авторизованные вызовы к API Mango Office:
- Подпись запросов через sha256(api_key + json + api_salt)
- Form-urlencoded отправка с тремя полями: json, vpbx_api_key, sign
- Валидный тестовый запрос stats/request для избежания блокировки
"""

import hashlib
import json
import time
from typing import Optional

import httpx

from ....core.errors import AppError


class MangoClient:
    """Клиент для работы с Mango VPBX API."""

    def __init__(self, api_key: str, api_salt: str, base_url: str = "https://app.mango-office.ru/vpbx/"):
        self.api_key = api_key
        self.api_salt = api_salt
        self.base_url = base_url.rstrip("/") + "/"
        self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)

    def _sign(self, json_str: str) -> str:
        """Создает подпись sha256 для запроса."""
        # Подпись = sha256(vpbx_api_key + json + vpbx_api_salt) в hex
        sign_data = self.api_key + json_str + self.api_salt
        return hashlib.sha256(sign_data.encode()).hexdigest()

    async def _post(self, path: str, payload: dict) -> dict:
        """Выполняет POST-запрос с подписью к Mango API."""
        # Сериализуем payload в JSON строку
        json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))

        # Создаем подпись
        sign = self._sign(json_str)

        # Формируем form-data
        form_data = {
            "json": json_str,
            "vpbx_api_key": self.api_key,
            "sign": sign
        }

        url = self.base_url + path.lstrip("/")

        try:
            response = await self._client.post(
                url,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
        except httpx.TimeoutException:
            raise AppError(
                code="MANGO_TIMEOUT",
                message="Таймаут при обращении к Mango Office API",
                status_code=502
            )
        except httpx.RequestError as e:
            raise AppError(
                code="MANGO_NETWORK_ERROR",
                message=f"Сетевая ошибка при обращении к Mango Office: {str(e)}",
                status_code=502
            )

        # Обработка HTTP ошибок
        if response.status_code == 401:
            raise AppError(
                code="MANGO_AUTH_ERROR",
                message="Ошибка авторизации Mango Office. Возможно, ключ заблокирован на 2 минуты или неверные учетные данные",
                status_code=400
            )
        elif response.status_code == 429:
            raise AppError(
                code="MANGO_RATE_LIMIT",
                message="Превышен лимит запросов к Mango Office API",
                status_code=429
            )
        elif not (200 <= response.status_code < 300):
            response_text = response.text[:300] if response.text else "Нет ответа"
            raise AppError(
                code="MANGO_API_ERROR",
                message=f"Ошибка Mango Office API (HTTP {response.status_code}): {response_text}",
                status_code=502
            )

        # Парсинг JSON ответа
        try:
            return response.json()
        except json.JSONDecodeError:
            response_text = response.text[:300] if response.text else "Пустой ответ"
            raise AppError(
                code="MANGO_PARSE_ERROR",
                message=f"Невалидный JSON ответ от Mango Office: {response_text}",
                status_code=502
            )

    async def check_auth(self) -> dict:
        """Проверяет подключение к Mango API валидным запросом статистики.

        Использует stats/request с минимальным периодом (60 секунд) для избежания
        блокировки ключа при неверных запросах.

        Returns:
            dict: {"ok": True} при успешной авторизации

        Raises:
            AppError: При любой ошибке авторизации или API
        """
        now = int(time.time())
        payload = {
            "date_from": now - 60,  # 60 секунд назад
            "date_to": now
        }

        response = await self._post("stats/request", payload)

        # Проверяем, что ответ содержит ожидаемую структуру
        if not isinstance(response, dict) or "key" not in response:
            raise AppError(
                code="MANGO_INVALID_RESPONSE",
                message="Неожиданный формат ответа от Mango Office API",
                status_code=502
            )

        return {"ok": True}

    async def close(self):
        """Закрывает HTTP клиент."""
        await self._client.aclose()