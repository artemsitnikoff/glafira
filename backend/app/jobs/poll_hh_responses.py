"""
Cron 1 — ИМПОРТ откликов с hh.ru (только импорт, без оценки).

Тянет НОВЫЕ отклики привязанных вакансий (по hh_negotiation_id определяем, что уже
есть, и полное резюме догружаем только для новых — см. poll_responses_now).
Оценка вынесена в отдельный джоб app/jobs/score_pending.py (cron 2), полностью
отвязана от импорта.

⚠️  Требует подключённого hh.ru + доступа работодателя к откликам.

Запуск: cron на VPS, раз в 5 минут (flock — не запускать поверх ещё идущего):
*/5 * * * * /usr/bin/flock -n /tmp/glafira-hh-import.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.poll_hh_responses' >> /var/www/glafira/hh-import.log 2>&1
"""

import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import HhIntegration
from ..services.integrations.hh import service as hh_service
from sqlalchemy import select

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_company_responses(session, company_id):
    """Импортирует НОВЫЕ отклики для одной компании. Returns {imported, skipped}."""
    stats = {"imported": 0, "skipped": 0}

    try:
        # Коллекции «Отклик» + «Отказ». poll_responses_now сам проверяет
        # подключение/токен/вакансии и грузит полное резюме ТОЛЬКО для новых
        # откликов (существующие по hh_negotiation_id пропускает без фетча).
        result = await hh_service.poll_responses_now(session, company_id)
        await session.commit()
        stats["imported"] = result.get("imported", 0)
        stats["skipped"] = result.get("skipped", 0)
        logger.info(
            f"Компания {company_id}: импортировано новых {stats['imported']}, "
            f"пропущено существующих {stats['skipped']}"
        )
    except Exception as e:
        # Сессия одна на все компании в цикле — после сбоя commit её обязательно
        # откатить, иначе следующая компания получит «грязную» сессию.
        await session.rollback()
        logger.error(f"Ошибка импорта откликов компании {company_id}: {e}")

    return stats


async def main():
    """Главная функция джоба импорта."""
    logger.info("Запуск импорта откликов hh.ru")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    # expire_on_commit=False — как в app/database.py (ORM-объекты импорта живут после commit).
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    total_stats = {"imported": 0, "skipped": 0, "companies": 0}

    try:
        async with async_session() as session:
            # Все компании с интеграцией hh.ru
            result = await session.execute(select(HhIntegration.company_id))
            company_ids = [row[0] for row in result]

            logger.info(f"Найдено {len(company_ids)} компаний с интеграцией hh.ru")

            for company_id in company_ids:
                stats = await poll_company_responses(session, company_id)
                total_stats["imported"] += stats["imported"]
                total_stats["skipped"] += stats["skipped"]
                total_stats["companies"] += 1

        logger.info(
            f"Импорт завершён: {total_stats['companies']} компаний, "
            f"новых {total_stats['imported']}, пропущено {total_stats['skipped']}"
        )

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
