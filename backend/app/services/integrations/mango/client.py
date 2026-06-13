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

    def _sign(self, json_str: str) -> str:
        """Создает подпись sha256 для запроса."""
        # Подпись = sha256(vpbx_api_key + json + vpbx_api_salt) в hex
        sign_data = self.api_key + json_str + self.api_salt
        return hashlib.sha256(sign_data.encode()).hexdigest()

    async def _post(self, path: str, payload: dict, follow_redirects: bool = True) -> dict:
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

        timeout_config = httpx.Timeout(30.0)

        try:
            async with httpx.AsyncClient(
                timeout=timeout_config,
                follow_redirects=follow_redirects
            ) as client:
                response = await client.post(
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

    async def request_stats(self, date_from: int, date_to: int, fields: str) -> dict:
        """Запрос статистики звонков за период.

        Args:
            date_from: Unix timestamp UTC+3 начала периода
            date_to: Unix timestamp UTC+3 окончания периода
            fields: Список полей через запятую (например: "records,start,finish,answer")

        Returns:
            dict: {"key": "..."} - ключ для получения результата

        Raises:
            AppError: При ошибке API
        """
        payload = {
            "date_from": date_from,
            "date_to": date_to,
            "fields": fields
        }

        response = await self._post("stats/request", payload)

        if not isinstance(response, dict) or "key" not in response:
            raise AppError(
                code="MANGO_INVALID_RESPONSE",
                message="Неожиданный формат ответа stats/request",
                status_code=502
            )

        return response

    async def get_stats_result(self, key: str) -> Optional[str]:
        """Получение результата статистики по ключу.

        Args:
            key: Ключ, полученный от request_stats

        Returns:
            str: CSV-данные если готово, None если ещё обрабатывается

        Raises:
            AppError: При ошибке API или неверном ключе
        """
        payload = {"key": key}

        # Используем минимальные redirects для получения CSV
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                url = self.base_url + "stats/result"
                json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                sign = self._sign(json_str)

                form_data = {
                    "json": json_str,
                    "vpbx_api_key": self.api_key,
                    "sign": sign
                }

                response = await client.post(
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

        if response.status_code == 204:
            # Ещё обрабатывается
            return None
        elif response.status_code == 404:
            raise AppError(
                code="MANGO_STATS_KEY_NOT_FOUND",
                message="Неверный ключ статистики или время жизни истекло",
                status_code=404
            )
        elif response.status_code == 401:
            raise AppError(
                code="MANGO_AUTH_ERROR",
                message="Ошибка авторизации Mango Office",
                status_code=400
            )
        elif response.status_code != 200:
            response_text = response.text[:300] if response.text else "Нет ответа"
            raise AppError(
                code="MANGO_API_ERROR",
                message=f"Ошибка Mango Office API (HTTP {response.status_code}): {response_text}",
                status_code=502
            )

        return response.text

    async def download_recording(self, recording_id: str) -> bytes:
        """Загрузка записи звонка.

        Args:
            recording_id: ID записи в Mango Office

        Returns:
            bytes: MP3 данные записи

        Raises:
            AppError: При ошибке API
        """
        payload = {
            "recording_id": recording_id,
            "action": "download"
        }

        # Шаг 1: Получаем редирект на файл
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                url = self.base_url + "queries/recording/post"
                json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                sign = self._sign(json_str)

                form_data = {
                    "json": json_str,
                    "vpbx_api_key": self.api_key,
                    "sign": sign
                }

                response = await client.post(
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

        if response.status_code != 302:
            if response.status_code == 401:
                raise AppError(
                    code="MANGO_AUTH_ERROR",
                    message="Ошибка авторизации Mango Office",
                    status_code=400
                )
            elif response.status_code == 404:
                raise AppError(
                    code="MANGO_RECORDING_NOT_FOUND",
                    message="Запись звонка не найдена",
                    status_code=404
                )
            else:
                response_text = response.text[:300] if response.text else "Нет ответа"
                raise AppError(
                    code="MANGO_API_ERROR",
                    message=f"Ошибка получения записи (HTTP {response.status_code}): {response_text}",
                    status_code=502
                )

        # Получаем URL файла из Location заголовка
        download_url = response.headers.get("Location")
        if not download_url:
            raise AppError(
                code="MANGO_NO_REDIRECT_URL",
                message="Не получен URL для загрузки записи",
                status_code=502
            )

        # Шаг 2: Скачиваем файл по одноразовой ссылке
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                file_response = await client.get(download_url)
        except httpx.TimeoutException:
            raise AppError(
                code="MANGO_TIMEOUT",
                message="Таймаут при загрузке записи звонка",
                status_code=502
            )
        except httpx.RequestError as e:
            raise AppError(
                code="MANGO_NETWORK_ERROR",
                message=f"Сетевая ошибка при загрузке записи: {str(e)}",
                status_code=502
            )

        if file_response.status_code != 200:
            raise AppError(
                code="MANGO_FILE_DOWNLOAD_ERROR",
                message=f"Ошибка загрузки записи (HTTP {file_response.status_code})",
                status_code=502
            )

        return file_response.content

    async def close(self):
        """Закрывает HTTP клиент."""
        # Метод оставлен для совместимости, реальные клиенты создаются в контекстах