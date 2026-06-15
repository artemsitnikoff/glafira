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


async def preview_applicants(token: str, sample: int = 50) -> tuple[int, List[Dict[str, Any]]]:
    """
    Быстрый превью кандидатов без полной загрузки всех ~15,700

    Args:
        token: API токен Potok.io
        sample: размер выборки (по умолчанию 50)

    Returns:
        Tuple (estimated_total, sample_data) где estimated_total = pages * per_page

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
        try:
            resp = await client.get(f"/api/v3/applicants.json?page=1&per_page={sample}")
            if not resp.is_success:
                await _handle_potok_error(resp)

            data = resp.json()
            sample_data = data.get("data", [])
            pages = data.get("pages", 1)
            per_page = data.get("per_page", sample)
            estimated_total = pages * per_page

            return estimated_total, sample_data
        except httpx.TimeoutException:
            raise ValidationError("Не удалось связаться с Потоком (таймаут)")
        except httpx.NetworkError:
            raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")


async def get_all_applicants(token: str, on_progress: Optional[Callable[[int, int], None]] = None) -> List[Dict[str, Any]]:
    """
    HYBRID получение всех кандидатов из Potok.io (~15,700 кандидатов)

    PHASE 1 (fast, full objects): /api/v3/applicants.json pages 1..99 (cap на 10k offset)
    PHASE 2 (remainder via jobs): jobs → ajs_joins → detail fetch оставшихся по id

    Args:
        token: API токен Potok.io
        on_progress: optional callback (done_count, total_count) для обновления UI

    Returns:
        Список всех applicant объектов (~15,700)

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
        # PHASE 1: быстрый список с полными объектами (до лимита 10k offset)
        by_id = {}
        page = 1

        while page <= 99:  # hard cap: page >= 100 returns 422
            try:
                resp = await client.get(f"/api/v3/applicants.json?page={page}&per_page=100")

                # Проверяем на ошибку лимита страниц (422)
                if resp.status_code == 422:
                    # Проверяем, что это именно ошибка лимита страниц
                    try:
                        error_data = resp.json() if resp.content else {}
                        if "page" in error_data.get("errors", {}):
                            logger.info(f"Potok: достигнут лимит пагинации на странице {page}, переходим к Phase 2")
                            break
                    except:
                        pass
                    # Если не page limit, обрабатываем как обычную ошибку
                    await _handle_potok_error(resp)

                if not resp.is_success:
                    await _handle_potok_error(resp)

                data = resp.json()
                candidates = data.get("data", [])

                if not candidates:
                    logger.info(f"Potok Phase 1: пустая страница {page}, завершаем")
                    break

                # Добавляем полные объекты в by_id
                for obj in candidates:
                    by_id[obj["id"]] = obj

                # Прогресс Phase 1
                if on_progress:
                    on_progress(len(by_id), len(by_id))

                page += 1

            except httpx.TimeoutException:
                raise ValidationError("Не удалось связаться с Потоком (таймаут)")
            except httpx.NetworkError:
                raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")

        logger.info(f"Potok Phase 1: получено {len(by_id)} кандидатов через список")

        # PHASE 2: получаем остальных через jobs → ajs_joins → detail fetch
        # 1. Получаем все job IDs
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

        job_ids = list(set(job_ids))

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

                    for obj in data.get("objects", []):
                        all_applicant_ids.add(obj["applicant_id"])

                    if not data.get("has_next_page"):
                        break
                    cursor = data.get("page_next_cursor")
                except httpx.TimeoutException:
                    raise ValidationError("Не удалось связаться с Потоком (таймаут)")
                except httpx.NetworkError:
                    raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")

        # 3. Определяем remainder (кандидаты НЕ в Phase 1)
        remainder = [aid for aid in all_applicant_ids if aid not in by_id]
        logger.info(f"Potok Phase 2: найдено {len(remainder)} дополнительных кандидатов через jobs")

        # Обновляем total для прогресса
        phase1_count = len(by_id)
        total = phase1_count + len(remainder)

        # 4. Detail fetch remainder
        if remainder:
            semaphore = asyncio.Semaphore(5)  # rate limit protection
            completed_remainder = 0

            async def _fetch_applicant(applicant_id: int) -> Optional[Dict[str, Any]]:
                nonlocal completed_remainder
                async with semaphore:
                    for attempt in range(3):  # retry on 429
                        try:
                            resp = await client.get(f"/api/v3/applicants/{applicant_id}.json")
                            if resp.status_code == 429 and attempt < 2:
                                delay = _parse_retry_after(resp.headers.get("Retry-After"))
                                await asyncio.sleep(delay)
                                continue
                            if not resp.is_success:
                                await _handle_potok_error(resp)
                            completed_remainder += 1
                            if on_progress:
                                on_progress(phase1_count + completed_remainder, total)
                            return resp.json()
                        except httpx.TimeoutException:
                            if attempt == 2:
                                raise ValidationError("Не удалось связаться с Потоком (таймаут)")
                        except httpx.NetworkError:
                            if attempt == 2:
                                raise ValidationError("Не удалось связаться с Потоком (сетевая ошибка)")
                    return None

            # Выполняем remainder запросы батчами
            batch_size = 10
            for i in range(0, len(remainder), batch_size):
                batch_ids = remainder[i:i + batch_size]
                tasks = [_fetch_applicant(aid) for aid in batch_ids]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Ошибка получения applicant: {result}")
                        continue
                    if result:
                        by_id[result["id"]] = result

                # Пауза между батчами
                if i + batch_size < len(remainder):
                    await asyncio.sleep(0.2)

        logger.info(f"Potok HYBRID: итого получено {len(by_id)} кандидатов (Phase1: {phase1_count}, Phase2: {len(remainder)})")
        return list(by_id.values())


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