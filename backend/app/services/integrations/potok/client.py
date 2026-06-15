"""Клиент для работы с Potok.io API"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
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


def _parse_retry_after(header_value: str | None, default: float = 2.0) -> float:
    """Parse Potok's Retry-After header (usually seconds). Fall back to `default`
    if not parseable or missing. Never raises."""
    if not header_value:
        return default
    try:
        return float(header_value)
    except ValueError:
        return default


async def get_all_applicants(token: str, on_progress: Optional[Callable[[int, int], None]] = None) -> List[Dict[str, Any]]:
    """
    Получение всех кандидатов из Potok.io через правильный flow API

    Использует проверенную схему из ArkadyJarvis:
    1. Список всех job-ов (активных + архивных)
    2. Для каждого job получение списка applicant_id
    3. Fetch каждого applicant по id с ограничением concurrency

    Args:
        token: API токен Potok.io
        on_progress: optional callback (done_count, total_count) для обновления UI

    Returns:
        Список всех applicant detail-объектов

    Raises:
        ValidationError: при ошибках токена, подписки, rate limit или сети
    """
    if not token or not token.strip():
        raise ValidationError("Токен Потока обязателен")

    async with httpx.AsyncClient(
        base_url=settings.POTOK_API_BASE,
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        headers={
            "Authorization": f"Bearer {token.strip()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    ) as client:
        # 1. Получаем все job IDs (активные + архивные)
        job_ids = []
        for scope in ("active", "archived"):
            cursor = None
            while True:
                params = {"by_scope": scope, "per_page": 50}
                if cursor:
                    params["page_cursor"] = cursor

                try:
                    resp = await client.get("/api/v3/cursor_paginated/jobs.json", params=params)
                    if not resp.is_success:
                        await _handle_potok_error(resp)
                    data = resp.json()
                    jobs = data.get("objects", {}).get("jobs", [])
                    job_ids.extend(job["id"] for job in jobs)

                    if not data.get("has_next_page"):
                        break
                    cursor = data.get("page_next_cursor")
                except httpx.TimeoutException:
                    raise ValidationError("Не удалось связаться с Потоком (таймаут)")
                except httpx.NetworkError:
                    raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")

        # Дедуплицируем job IDs
        job_ids = list(set(job_ids))
        logger.info(f"Potok: найдено {len(job_ids)} уникальных job-ов")

        # 2. Получаем все applicant IDs из всех job-ов
        all_applicant_ids = set()
        for job_id in job_ids:
            cursor = None
            while True:
                params = {"per_page": 100}
                if cursor:
                    params["page_cursor"] = cursor

                try:
                    resp = await client.get(f"/api/v3/jobs/{job_id}/ajs_joins.json", params=params)
                    if not resp.is_success:
                        await _handle_potok_error(resp)
                    data = resp.json()

                    # Включаем всех кандидатов (active и inactive), если не указано иное
                    for obj in data.get("objects", []):
                        all_applicant_ids.add(obj["applicant_id"])

                    if not data.get("has_next_page"):
                        break
                    cursor = data.get("page_next_cursor")
                except httpx.TimeoutException:
                    raise ValidationError("Не удалось связаться с Потоком (таймаут)")
                except httpx.NetworkError:
                    raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")

        applicant_ids = list(all_applicant_ids)
        logger.info(f"Potok: найдено {len(applicant_ids)} уникальных applicant-ов")

        # 3. Fetch каждого applicant по id с ограничением concurrency
        semaphore = asyncio.Semaphore(5)  # Ограничиваем до 5 одновременных запросов
        applicants = []
        completed = 0

        async def _fetch_applicant(applicant_id: int) -> Optional[Dict[str, Any]]:
            nonlocal completed
            async with semaphore:
                for attempt in range(3):  # 3 попытки с retry на 429
                    try:
                        resp = await client.get(f"/api/v3/applicants/{applicant_id}.json")
                        if resp.status_code == 429 and attempt < 2:
                            delay = _parse_retry_after(resp.headers.get("Retry-After"))
                            await asyncio.sleep(delay)
                            continue
                        if not resp.is_success:
                            await _handle_potok_error(resp)
                        completed += 1
                        if on_progress:
                            on_progress(completed, len(applicant_ids))
                        return resp.json()
                    except httpx.TimeoutException:
                        if attempt == 2:
                            raise ValidationError("Не удалось связаться с Потоком (таймаут)")
                    except httpx.NetworkError:
                        if attempt == 2:
                            raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")
                return None

        # Выполняем запросы батчами для контроля нагрузки
        batch_size = 10
        for i in range(0, len(applicant_ids), batch_size):
            batch_ids = applicant_ids[i:i + batch_size]
            tasks = [_fetch_applicant(aid) for aid in batch_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Ошибка получения applicant: {result}")
                    continue
                if result:
                    applicants.append(result)

            # Небольшая пауза между батчами
            if i + batch_size < len(applicant_ids):
                await asyncio.sleep(0.2)

        logger.info(f"Potok: успешно загружено {len(applicants)} кандидатов из {len(applicant_ids)}")
        return applicants


async def list_applicants(token: str, page: int = 1, per_page: int = 100) -> Dict[str, Any]:
    """
    LEGACY: Совместимость с существующим API

    Вызывает новый get_all_applicants() и эмулирует старую пагинацию
    """
    logger.warning("Вызван legacy list_applicants - используйте get_all_applicants()")

    # Получаем всех кандидатов
    all_applicants = await get_all_applicants(token)

    # Эмулируем пагинацию
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_applicants = all_applicants[start_idx:end_idx]

    total_pages = (len(all_applicants) + per_page - 1) // per_page

    return {
        "data": page_applicants,
        "page": page,
        "per_page": per_page,
        "pages": total_pages,
        "total": len(all_applicants)
    }


async def test_connection(token: str) -> bool:
    """
    Тестирование соединения с Potok API

    Args:
        token: API токен

    Returns:
        True если соединение успешное, False иначе
    """
    try:
        # Пробуем получить первый батч кандидатов
        await get_all_applicants(token)
        return True
    except Exception:
        return False