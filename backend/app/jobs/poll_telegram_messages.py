"""
Cron 4 — ИМПОРТ входящих сообщений из Telegram (Telethon user-аккаунт).

Тянет новые входящие сообщения от кандидатов для всех компаний с подключённым
Telegram-аккаунтом. Дедуплицирует по external_id (tg:{peer_id}:{msg_id}),
сохраняет только входящие от кандидатов (direction='in', sender_type='candidate').

⚠️  Требует подключённой Telegram-интеграции (статус 'connected').
⚠️  Автоматизация user-аккаунта против ToS Telegram — осознанное решение заказчика.

Запуск: cron на VPS, раз в 3 минуты (flock — не запускать поверх ещё идущего):
*/3 * * * * /usr/bin/flock -n /tmp/glafira-tg-messages.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.poll_telegram_messages' >> /var/www/glafira/tg-messages.log 2>&1
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from ..config import settings
from ..models import Integration
from ..services.integrations.telegram import service as tg_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_company_telegram(session, company_id) -> dict:
    """Импортирует входящие Telegram-сообщения для одной компании.

    Не кидает — сбои одной компании не рушат остальные.
    Returns {"imported": int, "connected": bool}.
    """
    try:
        result = await tg_service.sync_inbound(session, company_id)
        await session.commit()
        logger.info(
            "Компания %s: telegram входящих импортировано=%d connected=%s",
            company_id,
            result["imported"],
            result["connected"],
        )
        return result
    except Exception as e:
        await session.rollback()
        logger.error("Ошибка импорта Telegram-сообщений компании %s: %s", company_id, e)
        return {"imported": 0, "connected": False}


async def main():
    """Главная функция джоба импорта Telegram-сообщений."""
    logger.info("Запуск импорта входящих Telegram-сообщений")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    total_imported = 0
    total_companies = 0

    try:
        async with async_session() as session:
            # Все компании с подключённым Telegram (status='connected')
            result = await session.execute(
                select(Integration.company_id).where(
                    Integration.provider == "telegram",
                    Integration.status == "connected",
                )
            )
            company_ids = [row[0] for row in result]

        logger.info("Найдено %d компаний с подключённым Telegram", len(company_ids))

        for company_id in company_ids:
            async with async_session() as session:
                stats = await poll_company_telegram(session, company_id)
                total_imported += stats["imported"]
                total_companies += 1

        logger.info(
            "Импорт Telegram завершён: %d компаний, импортировано %d сообщений",
            total_companies,
            total_imported,
        )

    except Exception as e:
        logger.error("Критическая ошибка джоба Telegram: %s", e)
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
