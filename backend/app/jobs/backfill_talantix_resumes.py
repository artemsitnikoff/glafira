"""
Разовый бэкфилл резюме кандидатов Talantix (опыт/навыки/зарплата).

Кандидаты, импортированные из Talantix ДО фикса v1.7.3, лежат с пустым резюме
(маппер тянул только пустой `skills`). Эта джоба берёт ТОЛЬКО `source='talantix'`
без структурного опыта, перезапрашивает резюме с Talantix и дозаливает опыт/навыки/
зарплату тем, у кого они есть на Talantix. У кого на Talantix реально нет опыта
(только «о себе»/навыки) — остаётся как есть (это не сбой).

Строго по пустым Talantix-кандидатам — potok/hh/прочие источники НЕ трогает.
Идемпотентно: перед вставкой ещё раз проверяет отсутствие опыта (повторный запуск/
гонка не задваивают). Параллелит запросы (semaphore), пачками — company-scoped.

⚠️ НЕ запускать поверх идущего импорта Talantix (спор за один OAuth-токен —
refresh_token одноразовый-ротируемый). Импорт должен быть завершён.

Запуск (VPS, разово — НЕ крон):
  cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend \
    python -m app.jobs.backfill_talantix_resumes 2>&1 | tee -a talantix-backfill.log

Опционально ограничить прогон (для пробы): TALANTIX_BACKFILL_LIMIT=100
"""

import asyncio
import logging
import os

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..config import settings
from ..models import Candidate, CandidateExperience, CandidateSkill
from ..services.candidate_import import _create_talantix_child_records
from ..services.integrations.talantix import mapper as tmap
from ..services.integrations.talantix.client import TalantixClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CONCURRENCY = int(os.environ.get("TALANTIX_BACKFILL_CONCURRENCY", "6"))
BATCH = 300


async def main():
    limit = int(os.environ.get("TALANTIX_BACKFILL_LIMIT", "0"))  # 0 = все
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    st = {"done": 0, "filled": 0, "empty_ok": 0, "err": 0}
    try:
        async with async_session() as session:
            cid = (await session.execute(
                text("SELECT company_id FROM talantix_integrations LIMIT 1")
            )).scalar()
            if cid is None:
                logger.error("Интеграция Talantix не найдена — нечего бэкфиллить")
                return
            sql = (
                "SELECT c.id, c.talantix_person_id FROM candidates c "
                "WHERE c.company_id = :cid AND c.source = 'talantix' "
                "AND c.talantix_person_id IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM candidate_experience e WHERE e.candidate_id = c.id)"
            )
            if limit > 0:
                sql += f" LIMIT {limit}"
            rows = (await session.execute(text(sql), {"cid": cid})).all()
        targets = [(r[0], r[1]) for r in rows]
        logger.info("Компания %s: пустых Talantix-кандидатов к дозаливке — %d", cid, len(targets))
        if not targets:
            return

        client = TalantixClient(cid)
        sem = asyncio.Semaphore(CONCURRENCY)

        async def worker(cand_id, tpid):
            async with sem:
                try:
                    node = await client.get_person_full(int(tpid))
                    if node is None:
                        st["err"] += 1
                        return
                    mapped = tmap.map_person(node)
                    exp = mapped.get("experience") or []
                    skl = mapped.get("skills") or []
                    async with async_session() as s:
                        cand = await s.get(Candidate, cand_id)
                        if cand is None:
                            return
                        # Идемпотентность: если уже есть опыт ИЛИ навыки (повторный запуск/
                        # гонка/кандидат только с навыками) — не дублируем секции.
                        has = await s.scalar(
                            select(CandidateExperience.id)
                            .where(CandidateExperience.candidate_id == cand_id)
                            .limit(1)
                        )
                        if has is None:
                            has = await s.scalar(
                                select(CandidateSkill.id)
                                .where(CandidateSkill.candidate_id == cand_id)
                                .limit(1)
                            )
                        if has:
                            return
                        if mapped.get("resume_text"):
                            cand.resume_text = mapped["resume_text"]
                        if mapped.get("last_position") and not cand.last_position:
                            cand.last_position = mapped["last_position"][:255]
                        if mapped.get("salary_expectation") and not cand.salary_expectation:
                            cand.salary_expectation = mapped["salary_expectation"]
                            cand.salary_from = mapped["salary_expectation"]
                            cand.salary_to = mapped["salary_expectation"]
                        if exp or skl:
                            await _create_talantix_child_records(s, cid, cand_id, mapped)
                            st["filled"] += 1
                        else:
                            st["empty_ok"] += 1  # на Talantix реально нет опыта — так и оставляем
                        await s.commit()
                except Exception as e:  # noqa: BLE001
                    st["err"] += 1
                    logger.warning("Ошибка бэкфилла person=%s: %s", tpid, e)
                finally:
                    st["done"] += 1
                    if st["done"] % 200 == 0:
                        logger.info(
                            "%d/%d  дозалито=%d  реально_пусто=%d  ошибок=%d",
                            st["done"], len(targets), st["filled"], st["empty_ok"], st["err"],
                        )

        try:
            for i in range(0, len(targets), BATCH):
                await asyncio.gather(*(worker(c, t) for c, t in targets[i:i + BATCH]))
        finally:
            await client.close()

        logger.info(
            "ГОТОВО. обработано=%d  дозалито опытом/навыками=%d  реально_пусто=%d  ошибок=%d",
            st["done"], st["filled"], st["empty_ok"], st["err"],
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
