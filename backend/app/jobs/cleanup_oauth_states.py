"""
Очистка истёкших OAuth state для hh.ru интеграции.

Удаляет записи из hh_oauth_states где expires_at < now() — одноразовые токены, больше
не нужны. Безопасно: используются только для OAuth-flow, после exchange на access_token
можно удалить.

Запуск: cron на VPS, раз в сутки (flock — не запускать поверх ещё идущего):
0 4 * * * /usr/bin/flock -n /tmp/glafira-oauth-cleanup.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.cleanup_oauth_states' >> /var/www/glafira/oauth-cleanup.log 2>&1
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import HhOauthState

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """Главная функция джоба очистки OAuth states."""
    logger.info("Запуск очистки истёкших OAuth states")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Удаляем истёкшие записи
            now = datetime.now(timezone.utc)
            result = await session.execute(
                delete(HhOauthState).where(HhOauthState.expires_at < now)
            )
            await session.commit()

            deleted_count = result.rowcount
            logger.info(f"Удалено {deleted_count} истёкших OAuth state записей")

    except Exception as e:
        logger.error(f"Ошибка очистки OAuth states: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())