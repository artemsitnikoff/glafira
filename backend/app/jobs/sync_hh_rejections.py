"""
Cron — СИНХРОНИЗАЦИЯ отказов hh-кандидатов с hh.ru.

Для каждой компании с hh-интеграцией:
1. Находит отклонённых кандидатов с hh_negotiation_id, но без hh_discard_synced_at
2. Отклоняет их на hh.ru (PUT /negotiations/discard/{nid})
3. Отправляет вежливое сообщение в чат
4. Помечает как синхронизированных (идемпотентность)

⚠️  Требует подключённого hh.ru + доступа работодателя к откликам и чатам.

Запуск: cron на VPS, раз в 5 минут (flock — не запускать поверх ещё идущего):
*/5 * * * * /usr/bin/flock -n /tmp/glafira-hh-reject.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.sync_hh_rejections' >> /var/www/glafira/hh-reject.log 2>&1
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from ..config import settings
from ..models import HhIntegration
from ..services.integrations.hh.service import sync_company_rejections

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """Главная функция джоба синхронизации отказов."""
    logger.info("Запуск синхронизации отказов hh.ru")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    total_stats = {"discarded": 0, "already_discarded": 0, "failed": 0, "companies": 0, "skipped_no_token": 0}

    try:
        async with async_session() as session:
            # Все компании с интеграцией hh.ru
            result = await session.execute(select(HhIntegration.company_id))
            company_ids = [row[0] for row in result]

            logger.info(f"Найдено {len(company_ids)} компаний с интеграцией hh.ru")

            for company_id in company_ids:
                try:
                    stats = await sync_company_rejections(session, company_id, limit=20)
                    total_stats["discarded"] += stats["discarded"]
                    total_stats["already_discarded"] += stats.get("already_discarded", 0)
                    total_stats["failed"] += stats["failed"]
                    if stats.get("skipped_no_token", 0) == -1:  # сентинел «нет токена»
                        total_stats["skipped_no_token"] += 1
                    total_stats["companies"] += 1

                except Exception as e:
                    logger.error(f"Ошибка синхронизации отказов компании {company_id}: {e}")
                    total_stats["failed"] += 1
                    continue

        logger.info(
            f"Синхронизация отказов завершена: {total_stats['companies']} компаний, "
            f"отклонено {total_stats['discarded']}, уже в отказе {total_stats['already_discarded']}, "
            f"ошибок {total_stats['failed']}, без токена {total_stats['skipped_no_token']}"
        )

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())