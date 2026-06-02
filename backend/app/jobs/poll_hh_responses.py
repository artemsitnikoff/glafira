"""
Джоб для регулярного опроса откликов с hh.ru

⚠️  Требует подключённого hh.ru + ПЛАТНОГО доступа работодателя (emp_paid)
⚠️  НЕ проверено без реального токена hh.ru
⚠️  Точные имена полей resume — TODO (используются .get() с фолбэками)

Запуск: cron на VPS
*/5 * * * * docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.poll_hh_responses
"""

import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import HhIntegration, Vacancy
from ..services.integrations.hh import service as hh_service, client as hh_client
from ..services.glafira.scoring import score_pending_applications
from sqlalchemy import select

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_company_responses(session, company_id):
    """
    Опрашивает отклики для одной компании

    Args:
        session: AsyncSession
        company_id: UUID компании

    Returns:
        dict: статистика {imported: int, skipped: int}
    """
    stats = {"imported": 0, "skipped": 0, "scored": 0}

    try:
        # Тот же забор, что по кнопке в UI: коллекции «Отклик» + «Отказ», полный
        # маппинг резюме. poll_responses_now сам проверяет подключение/токен/вакансии.
        result = await hh_service.poll_responses_now(session, company_id)
        await session.commit()
        stats["imported"] = result.get("imported", 0)
        stats["skipped"] = result.get("skipped", 0)
        logger.info(f"Компания {company_id}: импортировано {stats['imported']}, пропущено {stats['skipped']}")
    except Exception as e:
        # Сессия одна на все компании в цикле — после сбоя commit её обязательно
        # откатить, иначе следующий шаг (авто-оценка) и следующая компания получат
        # «грязную» сессию.
        await session.rollback()
        logger.error(f"Ошибка обработки компании {company_id}: {e}")

    # Фоновая авто-оценка: Глафира оценивает неоценённые отклики «Отклик» пачкой
    # (отдельными коммитами внутри). Делаем даже если забор упал — могли остаться
    # неоценённые с прошлых проходов. Отказы и вакансии без описания не трогает.
    try:
        score_stats = await score_pending_applications(session, company_id, limit=10)
        stats["scored"] = score_stats.get("scored", 0)
        if stats["scored"]:
            logger.info(f"Компания {company_id}: авто-оценено {stats['scored']}")
    except Exception as e:
        logger.error(f"Ошибка авто-оценки компании {company_id}: {e}")

    return stats


async def main():
    """Главная функция джоба"""
    logger.info("Запуск опроса откликов hh.ru")

    # Создаём сессию
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    # expire_on_commit=False — как в app/database.py: объекты не протухают после
    # commit (per-candidate коммиты в авто-оценке + ORM-объекты в импорте).
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    total_stats = {"imported": 0, "skipped": 0, "scored": 0, "companies": 0}

    try:
        async with async_session() as session:
            # Получаем все компании с интеграцией hh.ru
            result = await session.execute(select(HhIntegration.company_id))
            company_ids = [row[0] for row in result]

            logger.info(f"Найдено {len(company_ids)} компаний с интеграцией hh.ru")

            for company_id in company_ids:
                stats = await poll_company_responses(session, company_id)
                total_stats["imported"] += stats["imported"]
                total_stats["skipped"] += stats["skipped"]
                total_stats["scored"] += stats["scored"]
                total_stats["companies"] += 1

        logger.info(
            f"Опрос завершён: {total_stats['companies']} компаний, "
            f"импортировано {total_stats['imported']}, пропущено {total_stats['skipped']}, "
            f"авто-оценено {total_stats['scored']}"
        )

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())