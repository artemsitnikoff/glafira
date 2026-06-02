"""
Cron 3 — ИМПОРТ входящих сообщений с hh.ru.

Тянет новые сообщения от соискателей для всех переписок (Applications с hh_negotiation_id).
Дедуплицирует по external_id, сохраняет только входящие от соискателей.

⚠️  Требует подключённого hh.ru + доступа работодателя к откликам.

Запуск: cron на VPS, раз в 2 минуты (flock — не запускать поверх ещё идущего):
*/2 * * * * /usr/bin/flock -n /tmp/glafira-hh-messages.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.poll_hh_messages' >> /var/www/glafira/hh-messages.log 2>&1
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from ..config import settings
from ..models import HhIntegration, Application, Message
from ..services.integrations.hh import client as hh_client
from ..services.integrations.hh.service import get_valid_access_token

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_negotiation_messages(session, company_id, negotiation_id, candidate_id, application_id, access_token):
    """
    Импортирует новые входящие сообщения для одной переписки.
    Returns количество импортированных сообщений.
    """
    imported = 0

    try:
        # Получить все сообщения переписки
        messages_data = await hh_client.get_negotiation_messages(access_token, negotiation_id)
        messages = messages_data.get("items", [])

        for msg in messages:
            # Определить автора - ищем поле автора в различных вариантах
            author = msg.get("author", {})
            participant_type = author.get("participant_type")
            author_type = author.get("type")

            # Сохраняем только сообщения от соискателя
            if participant_type != "applicant" and author_type != "applicant":
                continue

            # Проверить дедуп по external_id
            msg_id = msg.get("id")
            if not msg_id:
                continue

            # Проверяем, что сообщение с таким external_id ещё не существует в этой компании
            existing = await session.execute(
                select(Message.id)
                .where(
                    Message.external_id == str(msg_id),
                    Message.company_id == company_id
                )
            )
            if existing.scalar_one_or_none():
                continue  # Уже импортировано

            # Извлечь содержимое и время
            body = msg.get("text", "").strip()
            if not body:
                continue

            # Время отправки
            created_at_str = msg.get("created_at")
            sent_at = datetime.now(timezone.utc)
            if created_at_str:
                try:
                    # hh возвращает время в ISO формате
                    sent_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                except:
                    pass

            # Создать входящее сообщение
            message = Message(
                company_id=company_id,
                candidate_id=candidate_id,
                application_id=application_id,
                channel="hh",
                direction="in",
                sender_type="candidate",
                sender_user_id=None,
                body=body,
                sent_at=sent_at,
                created_at=datetime.now(timezone.utc),
                external_id=str(msg_id)
            )

            session.add(message)
            imported += 1

    except Exception as e:
        logger.error(f"Ошибка импорта сообщений переписки {negotiation_id}: {e}")

    return imported


async def poll_company_messages(session, company_id):
    """Импортирует входящие сообщения для одной компании. Returns {imported}."""
    stats = {"imported": 0, "negotiations": 0}

    try:
        # Получить токен
        access_token = await get_valid_access_token(session, company_id)

        # Найти все заявки с hh_negotiation_id
        result = await session.execute(
            select(Application.hh_negotiation_id, Application.candidate_id, Application.id)
            .where(
                Application.company_id == company_id,
                Application.hh_negotiation_id.isnot(None)
            )
        )

        negotiations = result.fetchall()
        logger.info(f"Компания {company_id}: найдено {len(negotiations)} переписок hh")

        for negotiation_id, candidate_id, application_id in negotiations:
            try:
                imported = await poll_negotiation_messages(
                    session,
                    company_id,
                    negotiation_id,
                    candidate_id,
                    application_id,
                    access_token
                )
                stats["imported"] += imported
                stats["negotiations"] += 1
            except Exception as e:
                logger.error(f"Ошибка обработки переписки {negotiation_id}: {e}")
                continue

        await session.commit()
        logger.info(f"Компания {company_id}: импортировано {stats['imported']} новых сообщений из {stats['negotiations']} переписок")

    except Exception as e:
        # Откат при сбое commit для изоляции ошибок
        await session.rollback()
        logger.error(f"Ошибка импорта сообщений компании {company_id}: {e}")

    return stats


async def main():
    """Главная функция джоба импорта сообщений."""
    logger.info("Запуск импорта сообщений hh.ru")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    total_stats = {"imported": 0, "negotiations": 0, "companies": 0}

    try:
        async with async_session() as session:
            # Все компании с интеграцией hh.ru
            result = await session.execute(select(HhIntegration.company_id))
            company_ids = [row[0] for row in result]

            logger.info(f"Найдено {len(company_ids)} компаний с интеграцией hh.ru")

            for company_id in company_ids:
                stats = await poll_company_messages(session, company_id)
                total_stats["imported"] += stats["imported"]
                total_stats["negotiations"] += stats["negotiations"]
                total_stats["companies"] += 1

        logger.info(
            f"Импорт сообщений завершён: {total_stats['companies']} компаний, "
            f"новых сообщений {total_stats['imported']}, переписок {total_stats['negotiations']}"
        )

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())