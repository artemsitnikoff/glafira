"""
Разовая догрузка ОТСУТСТВУЮЩИХ кандидатов Talantix.

При большом импорте часть персон упала транзиентно (блип БД/сети под нагрузкой) —
в счётчике «Ошибок», кандидат не создан. Эта джоба перечисляет всех персон Talantix,
берёт множество уже известных `talantix_person_id` в базе (ЛЮБОЙ source — включая
контакт-совпавших potok/hh, которым id проставлен при импорте) и создаёт ТОЛЬКО тех,
кого в базе нет. Фетчит лишь реально отсутствующих — не перебирает всю базу.

Создание идёт штатным `_process_talantix_person` в режиме «skip»: новый → создаётся
с полным резюме (StructuredResume/CustomResume) + комментариями + согласием; если
вдруг совпал по контакту — пропускается. company_id ВЕЗДЕ. Идемпотентно (повторный
запуск не задваивает — созданные обретают talantix_person_id и уходят из «missing»).

⚠️ НЕ запускать поверх идущего импорта Talantix (спор за один OAuth-токен).

Запуск (VPS, разово):
  cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend \
    python -m app.jobs.create_missing_talantix 2>&1 | tee -a talantix-missing.log
"""

import asyncio
import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..config import settings
from ..services.candidate_import import _process_talantix_person
from ..services.integrations.talantix import mapper as tmap
from ..services.integrations.talantix.client import TalantixClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CONCURRENCY = int(os.environ.get("TALANTIX_MISSING_CONCURRENCY", "6"))
BATCH = 200
MAX_PAGES = 5000  # 5000*50 = 250k, с запасом над реальным объёмом


async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    st = {"done": 0, "created": 0, "skipped": 0, "errors": 0}
    try:
        async with async_session() as session:
            cid = (await session.execute(
                text("SELECT company_id FROM talantix_integrations LIMIT 1")
            )).scalar()
            if cid is None:
                logger.error("Интеграция Talantix не найдена")
                return
            rows = (await session.execute(
                text("SELECT talantix_person_id FROM candidates "
                     "WHERE company_id = :cid AND talantix_person_id IS NOT NULL"),
                {"cid": cid},
            )).all()
        existing = {str(r[0]) for r in rows if r[0] is not None}
        logger.info("Уже в базе (по talantix_person_id, любой источник): %d", len(existing))

        client = TalantixClient(cid)
        logger.info("Перечисляем всех персон Talantix…")
        person_ids = await client.collect_person_ids(max_pages=MAX_PAGES)
        missing = [p for p in person_ids if str(p) not in existing]
        logger.info("Всего персон: %d | отсутствуют в базе (создаём): %d", len(person_ids), len(missing))
        if not missing:
            await client.close()
            return

        sem = asyncio.Semaphore(CONCURRENCY)

        async def worker(pid):
            async with sem:
                try:
                    node = await client.get_person_full(int(pid))
                    if node is None:
                        st["errors"] += 1
                        return
                    mapped = tmap.map_person(node)
                    try:
                        events = await client.fetch_all_history(int(pid))
                    except Exception:  # noqa: BLE001
                        events = []
                    pd = node.get("personalDataAgreement")
                    stats: dict = {}
                    async with async_session() as s:
                        await _process_talantix_person(s, cid, mapped, events, pd, "skip", stats)
                        await s.commit()
                    st["created"] += stats.get("created", 0)
                    st["skipped"] += stats.get("skipped", 0)
                    st["errors"] += stats.get("errors", 0)
                except Exception as e:  # noqa: BLE001
                    st["errors"] += 1
                    logger.warning("person %s: %s", pid, e)
                finally:
                    st["done"] += 1
                    if st["done"] % 50 == 0:
                        logger.info(
                            "%d/%d  создано=%d  пропущено=%d  ошибок=%d",
                            st["done"], len(missing), st["created"], st["skipped"], st["errors"],
                        )

        try:
            for i in range(0, len(missing), BATCH):
                await asyncio.gather(*(worker(p) for p in missing[i:i + BATCH]))
        finally:
            await client.close()

        logger.info(
            "ГОТОВО. обработано=%d  создано=%d  пропущено=%d  ошибок=%d",
            st["done"], st["created"], st["skipped"], st["errors"],
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
