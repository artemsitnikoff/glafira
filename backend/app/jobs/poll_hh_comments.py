"""
Cron — ИМПОРТ комментариев работодателя к резюме с hh в блок «Комментарии».

Тянет заметки работодателя к соискателям на hh для всех кандидатов source='hh' и
сохраняет их как Comment(source='hh') — read-only, с пометкой источника. Дедуп по
external_id (повторный прогон не дублирует). ПЕРВЫЙ прогон = разовый перенос всех
существующих комментариев (идемпотентен по дедупу).

⚠️ Это ИМПОРТ, не действие пользователя: Event('comment', actor='human') и
mention-парсинг НЕ пишутся (§2.2). Company-scoped.

⚠️ Резолв applicant_id (owner.id) для НОВОГО кандидата тратит квоту просмотров резюме
hh (один раз на кандидата, далее из кэша extra['hh_applicant_id']). Сам
applicant_comments — бесплатный. При исчерпании квоты резолв деградирует в
{"imported":0} для кандидата и повторится в следующем прогоне (без падения).

Запуск: cron на VPS, flock — не запускать поверх ещё идущего (⚠️ крон на VPS
заказчик заводит РУКАМИ, в репозитории не декларируется — §6):
*/15 * * * * /usr/bin/flock -n /tmp/glafira-hh-comments.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.poll_hh_comments' >> /var/www/glafira/hh-comments.log 2>&1
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..config import settings
from ..models import Candidate, HhIntegration
from ..services.integrations.hh.comments import sync_candidate_hh_comments

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def poll_company_comments(session, company_id) -> dict:
    """Импортирует комментарии hh для всех hh-кандидатов одной компании.
    Returns {"imported": N, "candidates": M}."""
    stats = {"imported": 0, "candidates": 0}

    # hh-кандидаты компании (у остальных нет резюме на hh — тянуть нечего).
    result = await session.execute(
        select(Candidate.id).where(
            Candidate.company_id == company_id,
            Candidate.source == "hh",
            Candidate.deleted_at.is_(None),
        )
    )
    candidate_ids = [row[0] for row in result]
    logger.info(f"Компания {company_id}: {len(candidate_ids)} hh-кандидатов")

    for candidate_id in candidate_ids:
        try:
            res = await sync_candidate_hh_comments(
                session, company_id=company_id, candidate_id=candidate_id
            )
            imported = res.get("imported", 0)
            if imported:
                # Коммитим по кандидату — сбой одного не теряет уже импортированное.
                await session.commit()
                stats["imported"] += imported
            stats["candidates"] += 1
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка импорта комментариев кандидата {candidate_id}: {e}")
            continue

    # Финальный коммит на случай кэша applicant_id без новых комментариев.
    try:
        await session.commit()
    except Exception:
        await session.rollback()

    logger.info(
        f"Компания {company_id}: импортировано {stats['imported']} комментариев "
        f"по {stats['candidates']} кандидатам"
    )
    return stats


async def main():
    logger.info("Запуск импорта комментариев hh.ru")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    total = {"imported": 0, "companies": 0}
    try:
        async with async_session() as session:
            result = await session.execute(select(HhIntegration.company_id))
            company_ids = [row[0] for row in result]
            logger.info(f"Найдено {len(company_ids)} компаний с интеграцией hh.ru")

            for company_id in company_ids:
                stats = await poll_company_comments(session, company_id)
                total["imported"] += stats["imported"]
                total["companies"] += 1

        logger.info(
            f"Импорт комментариев завершён: {total['companies']} компаний, "
            f"новых комментариев {total['imported']}"
        )
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
