"""Постановка фоновых задач в durable-очередь (arq/Redis) с фолбэком на in-process.

Контракт прост: enqueue_*-функция возвращает True, если задача поставлена в очередь
(её выполнит отдельный воркер-контейнер), и False — если очередь выключена
(USE_JOB_QUEUE=false) ИЛИ Redis недоступен. В случае False вызывающий запускает
задачу как раньше (asyncio.create_task в backend-процессе).

Зачем фолбэк: миграция безопасна и обратима. Выкатили код — поведение не меняется
(флаг по умолчанию off). Подняли redis+worker и включили флаг — задачи переехали в
очередь, переживающую рестарты backend. Сломалось что-то с очередью — вернули флаг в
false, и всё работает по-старому. Никогда не бывает «задача в очереди, а воркер мёртв».
"""
from __future__ import annotations

import logging
from uuid import UUID

from ..config import settings

logger = logging.getLogger(__name__)


async def enqueue_auto_evaluate(
    run_id: UUID,
    company_id: UUID,
    auto_search_id: UUID,
    segment: str,
    n,
    skip_scored: bool,
) -> bool:
    """Поставить AI-оценку Автоподбора в очередь. True — поставлено (выполнит воркер);
    False — очередь выключена/недоступна → вызывающий запускает in-process."""
    if not settings.USE_JOB_QUEUE:
        return False
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        try:
            await pool.enqueue_job(
                "run_auto_evaluate",
                str(run_id),
                str(company_id),
                str(auto_search_id),
                segment,
                n,
                bool(skip_scored),
            )
        finally:
            await pool.aclose()
        logger.info("[jobq] enqueued run_auto_evaluate run=%s", run_id)
        return True
    except Exception as e:
        logger.warning("[jobq] enqueue failed (fallback to in-process): %s", e)
        return False
