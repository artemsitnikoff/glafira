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
    stats = {"imported": 0, "skipped": 0}

    try:
        # Получаем интеграцию
        integration = await hh_service.get_integration(session, company_id)
        if not integration or not integration.hh_employer_id:
            logger.info(f"Компания {company_id}: нет интеграции hh.ru")
            return stats

        # Получаем токен
        access_token = await hh_service.get_valid_access_token(session, company_id)

        # Получаем вакансии с hh_vacancy_id
        result = await session.execute(
            select(Vacancy).where(
                Vacancy.company_id == company_id,
                Vacancy.hh_vacancy_id.isnot(None),
                Vacancy.status == "active"  # Только активные
            )
        )
        vacancies = result.scalars().all()

        if not vacancies:
            logger.info(f"Компания {company_id}: нет вакансий с hh_vacancy_id")
            return stats

        logger.info(f"Компания {company_id}: обрабатываем {len(vacancies)} вакансий")

        # Обрабатываем каждую вакансию
        for vacancy in vacancies:
            try:
                vacancy_stats = await poll_vacancy_responses(
                    session, access_token, vacancy
                )
                stats["imported"] += vacancy_stats["imported"]
                stats["skipped"] += vacancy_stats["skipped"]

            except Exception as e:
                logger.error(f"Ошибка обработки вакансии {vacancy.id} ({vacancy.name}): {e}")
                continue

        logger.info(f"Компания {company_id}: импортировано {stats['imported']}, пропущено {stats['skipped']}")

    except Exception as e:
        logger.error(f"Ошибка обработки компании {company_id}: {e}")

    return stats


async def poll_vacancy_responses(session, access_token, vacancy):
    """
    Опрашивает отклики для одной вакансии

    Args:
        session: AsyncSession
        access_token: hh.ru access token
        vacancy: объект Vacancy

    Returns:
        dict: статистика {imported: int, skipped: int}
    """
    stats = {"imported": 0, "skipped": 0}
    page = 0

    while True:
        try:
            # Получаем страницу откликов
            data = await hh_client.get_negotiation_responses(
                access_token, vacancy.hh_vacancy_id, page=page, per_page=50
            )

            items = data.get("items", [])
            if not items:
                break

            # Обрабатываем каждый отклик
            for item in items:
                try:
                    imported = await hh_service.import_response(
                        session, vacancy.company_id, vacancy, item
                    )
                    if imported:
                        stats["imported"] += 1
                    else:
                        stats["skipped"] += 1

                except Exception as e:
                    logger.error(f"Ошибка импорта отклика {item.get('id')}: {e}")
                    continue

            # Коммитим после каждой страницы
            await session.commit()

            # Проверяем, есть ли ещё страницы
            if page >= data.get("pages", 1) - 1:
                break

            page += 1

        except Exception as e:
            logger.error(f"Ошибка получения откликов для вакансии {vacancy.hh_vacancy_id}: {e}")
            break

    return stats


async def main():
    """Главная функция джоба"""
    logger.info("Запуск опроса откликов hh.ru")

    # Создаём сессию
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine)

    total_stats = {"imported": 0, "skipped": 0, "companies": 0}

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
                total_stats["companies"] += 1

        logger.info(
            f"Опрос завершён: {total_stats['companies']} компаний, "
            f"импортировано {total_stats['imported']}, пропущено {total_stats['skipped']}"
        )

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())