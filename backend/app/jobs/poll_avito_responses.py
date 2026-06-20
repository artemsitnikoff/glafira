"""
Cron — ИМПОРТ откликов с Авито Работа (только для компаний с подключённым Авито
client_id/secret и привязанными вакансиями avito_vacancy_id).

OAuth: client_credentials — токен получается/рефрешится автоматически.
Телефон кандидата содержится в отклике БЕСПЛАТНО — /contacts НЕ вызывается.

Добавьте в crontab на VPS (запуск каждые 15 минут, flock — не запускать поверх):

*/15 * * * * /usr/bin/flock -n /tmp/glafira-avito-import.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.poll_avito_responses' >> /var/www/glafira/avito-import.log 2>&1
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models.avito_integration import AvitoIntegration
from ..services.integrations.avito import sync as avito_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_company(session, company_id) -> dict:
    """Опрос одной компании. Возвращает статистику."""
    try:
        result = await avito_sync.poll_avito_responses_now(session, company_id)
        await session.commit()
        logger.info(
            "Компания %s: Авито откликов импортировано=%d, обновлено=%d, пропущено=%d, ошибки=%d",
            company_id,
            result.get("imported", 0),
            result.get("updated", 0),
            result.get("skipped", 0),
            len(result.get("errors", [])),
        )
        return result
    except Exception as exc:
        await session.rollback()
        logger.error("Ошибка poll Авито компании %s: %s", company_id, exc)
        return {"imported": 0, "updated": 0, "skipped": 0, "errors": [str(exc)]}


async def main():
    logger.info("Запуск импорта откликов Авито Работа")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Все компании с AvitoIntegration (client_id непустой — значит подключено)
            result = await session.execute(
                select(AvitoIntegration.company_id).where(
                    AvitoIntegration.client_id.isnot(None),
                    AvitoIntegration.client_secret.isnot(None),
                )
            )
            company_ids = [row[0] for row in result]

        logger.info("Найдено %d компаний с интеграцией Авито", len(company_ids))

        total = {"imported": 0, "updated": 0, "skipped": 0}
        for cid in company_ids:
            async with async_session() as session:
                stats = await poll_company(session, cid)
                total["imported"] += stats.get("imported", 0)
                total["updated"] += stats.get("updated", 0)
                total["skipped"] += stats.get("skipped", 0)

        logger.info(
            "Импорт Авито завершён: %d компаний, импортировано=%d, обновлено=%d, пропущено=%d",
            len(company_ids),
            total["imported"],
            total["updated"],
            total["skipped"],
        )
    except Exception as exc:
        logger.error("Критическая ошибка: %s", exc)
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
