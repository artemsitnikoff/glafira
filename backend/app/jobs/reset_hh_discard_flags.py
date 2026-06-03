"""
Сброс флага hh_discard_synced_at у ВСЕХ отклонённых hh-заявок — чтобы синхронизация
отказов (sync_hh_rejections) прошла заново. Нужен после исправления логики discard,
т.к. предыдущая версия ошибочно помечала активные отклики как синхронизированные.

Безопасно: state-aware синк сам разберётся — реально отклонённые на hh снова
пометятся, активные будут корректно отклонены.

Запуск:
docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.reset_hh_discard_flags
"""

import asyncio
import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import Application

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with async_session() as session:
            result = await session.execute(
                update(Application)
                .where(
                    Application.stage == "rejected",
                    Application.hh_negotiation_id.isnot(None),
                )
                .values(hh_discard_synced_at=None)
            )
            await session.commit()
            logger.info(f"Сброшен флаг hh_discard_synced_at у {result.rowcount} отклонённых hh-заявок")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
