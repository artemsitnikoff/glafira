"""arq-воркер — durable фоновые задачи, переживающие рестарты backend.

Запускается ОТДЕЛЬНЫМ контейнером (docker-compose service `worker`, тот же образ
что backend, команда `arq app.worker.WorkerSettings`). Брокер/состояние — Redis,
поэтому при падении/перезапуске воркера джоб не теряется: arq повторяет его
(до max_tries), а сама задача резюмируемая (пропускает уже сделанное).

Сейчас обслуживает AI-оценку Автоподбора. Постепенно сюда переедут остальные
тяжёлые фоновые задачи (OSINT-верификация, реиндекс эмбеддингов, импорт и т.д.).
"""
from __future__ import annotations

import logging
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings

from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("glafira.worker")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def run_auto_evaluate(
    ctx: dict,
    run_id: str,
    company_id: str,
    auto_search_id: str,
    segment: str,
    n,
    skip_scored: bool,
) -> None:
    """Джоб AI-оценки Автоподбора.

    Резюмируемость: на ЛЮБОМ повторе (job_try>1 — после падения/перезапуска воркера)
    форсим skip_scored, чтобы пропустить уже оценённых из прошлого прогресса и НЕ
    переплачивать токенами. На первой попытке уважаем запрошенный режим
    (полная переоценка vs дооценка)."""
    from .services.auto_search import _run_auto_evaluate

    job_try = ctx.get("job_try", 1)
    effective_skip = bool(skip_scored) or job_try > 1
    logger.info(
        "[worker] run_auto_evaluate run=%s try=%s skip_scored=%s",
        run_id, job_try, effective_skip,
    )
    await _run_auto_evaluate(
        UUID(run_id),
        UUID(company_id),
        UUID(auto_search_id),
        segment,
        n,
        effective_skip,
    )
    logger.info("[worker] run_auto_evaluate done run=%s", run_id)


async def self_heal_cron(ctx: dict) -> None:
    """Cron в воркере: авто-продолжает прерванные оценки (деплой/рестарт/падение
    убили прогон) — skip_scored, только неоценённые, без переплаты. См.
    services.auto_search.self_heal_interrupted_evals (кап против death-loop внутри)."""
    from .services.auto_search import self_heal_interrupted_evals
    await self_heal_interrupted_evals()


class WorkerSettings:
    """Конфиг arq-воркера. Имя джоба = имя функции (`run_auto_evaluate`)."""

    functions = [run_auto_evaluate]
    # Self-heal прерванных оценок: при старте воркера (после деплоя/рестарта сразу
    # подхватит) + каждые 3 минуты.
    cron_jobs = [
        cron(self_heal_cron, minute=set(range(0, 60, 3)), second=0, run_at_startup=True)
    ]
    redis_settings = _redis_settings()
    # Параллельность джобов в одном воркере.
    max_jobs = 4
    # Оценка может идти часами (внутренний кап _run_auto_evaluate — 6ч). Берём с запасом,
    # иначе arq убьёт джоб по своему дефолтному таймауту (300с).
    job_timeout = 7 * 3600
    # ⚠️ max_tries=1: НЕ полагаемся на arq-авторетрай убитого джоба — иначе он бы
    # гонялся с self_heal_cron (оба продолжили бы один автопоиск → двойная оплата
    # хвоста). Возобновление прерванных оценок — ТОЛЬКО через self_heal_cron
    # (детерминированно: ловит мёртвый прогон, продолжает skip_scored, под капом).
    max_tries = 1
    keep_result = 3600
