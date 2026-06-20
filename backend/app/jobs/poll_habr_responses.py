"""
Cron — ИМПОРТ откликов с Хабр Карьера (только для компаний с подключённым Хабром
и привязанными вакансиями habr_vacancy_id).

⚠️ API Хабр Карьера требует одобренного приложения и пиннинга реальных эндпоинтов.
До пиннинга: poll будет возвращать ошибки (честно), не падать.

Добавьте в crontab на VPS:
*/15 * * * * /usr/bin/flock -n /tmp/glafira-habr-import.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.poll_habr_responses' >> /var/www/glafira/habr-import.log 2>&1

Рекомендуется flock (не запускать поверх ещё идущего джоба).
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models.habr_integration import HabrIntegration
from ..services.integrations.habr import sync as habr_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_company(session, company_id) -> dict:
    """Опрос одной компании. Возвращает статистику."""
    try:
        result = await habr_sync.poll_habr_responses_now(session, company_id)
        await session.commit()
        logger.info(
            "Компания %s: Хабр откликов импортировано=%d, пропущено=%d, ошибки=%d",
            company_id,
            result.get("imported", 0),
            result.get("skipped", 0),
            len(result.get("errors", [])),
        )
        return result
    except Exception as exc:
        await session.rollback()
        logger.error("Ошибка poll компании %s: %s", company_id, exc)
        return {"imported": 0, "skipped": 0, "errors": [str(exc)]}


async def main():
    logger.info("Запуск импорта откликов Хабр Карьера")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Все компании с HabrIntegration (access_token непустой)
            result = await session.execute(
                select(HabrIntegration.company_id).where(
                    HabrIntegration.access_token.isnot(None)
                )
            )
            company_ids = [row[0] for row in result]

        logger.info("Найдено %d компаний с интеграцией Хабр Карьера", len(company_ids))

        total = {"imported": 0, "skipped": 0}
        for cid in company_ids:
            async with async_session() as session:
                stats = await poll_company(session, cid)
                total["imported"] += stats.get("imported", 0)
                total["skipped"] += stats.get("skipped", 0)

        logger.info(
            "Импорт Хабр завершён: %d компаний, импортировано=%d, пропущено=%d",
            len(company_ids), total["imported"], total["skipped"],
        )
    except Exception as exc:
        logger.error("Критическая ошибка: %s", exc)
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
