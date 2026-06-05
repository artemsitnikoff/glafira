"""
Cron 3 — ИМПОРТ входящих сообщений с hh.ru через новый Chats API.

Тянет новые сообщения от соискателей для всех чатов (Applications с hh_chat_id).
Дедуплицирует по external_id, сохраняет только входящие от соискателей.

⚠️  Требует подключённого hh.ru + доступа работодателя к чатам.

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
from ..services.chat_log import log_chat
from ..services.integrations.hh import client as hh_client
from ..services.integrations.hh.service import get_valid_access_token

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_chat_messages(session, company_id, chat_id, candidate_id, application_id, access_token):
    """
    Импортирует новые входящие сообщения для одного чата через Chats API.
    Returns количество импортированных сообщений.
    """
    imported = 0

    try:
        # Получить все сообщения чата
        messages_data = await hh_client.get_chat_messages(access_token, chat_id, limit=50, order="prev")
        # hh Chats API отдаёт сообщения под "items" (см. docstring клиента); раньше читали
        # только "messages" → входящие молча не импортировались. Читаем оба ключа на устойчивость.
        messages = messages_data.get("items") or messages_data.get("messages") or []

        for msg in messages:
            # Определить тип сообщения и автора
            msg_type = msg.get("type")
            sender_info = msg.get("sender_display_info", {})
            sender_role = sender_info.get("role")

            # Сохраняем только SIMPLE сообщения от APPLICANT
            if msg_type != "SIMPLE" or sender_role != "APPLICANT":
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

            # Извлечь текст из payload
            payload = msg.get("payload", {})
            body = payload.get("text", "").strip() if payload.get("text") else ""
            if not body:
                continue

            # Время отправки
            created_at_str = msg.get("creation_time")
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
            log_chat(f"hh ← входящее (chat {chat_id}): {body[:80]}")

    except Exception as e:
        logger.error(f"Ошибка импорта сообщений чата {chat_id}: {e}")

    return imported


async def poll_company_messages(session, company_id):
    """Импортирует входящие сообщения для одной компании. Returns {imported}."""
    stats = {"imported": 0, "chats": 0}

    try:
        # Получить токен
        access_token = await get_valid_access_token(session, company_id)

        # Найти все заявки с hh_chat_id
        result = await session.execute(
            select(Application.hh_chat_id, Application.candidate_id, Application.id)
            .where(
                Application.company_id == company_id,
                Application.hh_chat_id.isnot(None)
            )
        )

        chats = result.fetchall()
        logger.info(f"Компания {company_id}: найдено {len(chats)} чатов hh")

        for chat_id, candidate_id, application_id in chats:
            try:
                imported = await poll_chat_messages(
                    session,
                    company_id,
                    chat_id,
                    candidate_id,
                    application_id,
                    access_token
                )
                stats["imported"] += imported
                stats["chats"] += 1
            except Exception as e:
                logger.error(f"Ошибка обработки чата {chat_id}: {e}")
                continue

        await session.commit()
        logger.info(f"Компания {company_id}: импортировано {stats['imported']} новых сообщений из {stats['chats']} чатов")

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
                total_stats["negotiations"] += stats["chats"]
                total_stats["companies"] += 1

        logger.info(
            f"Импорт сообщений завершён: {total_stats['companies']} компаний, "
            f"новых сообщений {total_stats['imported']}, чатов {total_stats['negotiations']}"
        )

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())