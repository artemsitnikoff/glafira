"""
Диагностика отклика hh: дамп employer_state + actions[] (id, enabled, method, url,
arguments). Нужен, чтобы понять, КАК правильно отклонять активный отклик (голый
PUT /negotiations/discard/{nid} вернул wrong_state).

Запуск:
docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.hh_diag_negotiation <negotiation_id>
"""

import asyncio
import json
import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import HhIntegration
from ..services.integrations.hh import client as hh_client
from ..services.integrations.hh.service import get_valid_access_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.jobs.hh_diag_negotiation <negotiation_id>")
        return
    nid = sys.argv[1]

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with async_session() as session:
            company_id = (await session.execute(select(HhIntegration.company_id))).scalars().first()
            if not company_id:
                print("Нет компаний с интеграцией hh.ru")
                return
            token = await get_valid_access_token(session, company_id)
            nego = await hh_client.get_negotiation(token, nid)

        print(f"=== negotiation {nid} ===")
        print("state:", nego.get("state"))
        print("employer_state:", nego.get("employer_state"))
        print("messaging_status:", nego.get("messaging_status"))
        print("=== actions[] (как отклонять/что доступно) ===")
        print(json.dumps(nego.get("actions"), ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
