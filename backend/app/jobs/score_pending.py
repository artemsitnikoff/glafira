"""
Cron 2 — ОЦЕНКА неоценённых кандидатов (полностью отвязана от импорта).

Глафира оценивает ЛЮБЫЕ заявки без оценки, которые НЕ в «Отказе» (stage != 'rejected'),
у активной/приостановленной вакансии. Источник кандидата (hh, ручной, импорт) и этап
значения не имеют — оцениваем всех «незаоценённых и не отказанных». Логика в
services/glafira/scoring.py::score_pending_applications (дедуп, per-candidate commit,
запись в журнал оценок). За проход — до settings.GLAFIRA_AUTOSCORE_BATCH заявок на
компанию (потолок расхода LLM).

Запуск: cron на VPS, раз в 5 минут (flock — не запускать поверх ещё идущего):
*/5 * * * * /usr/bin/flock -n /tmp/glafira-score.lock -c 'cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.score_pending' >> /var/www/glafira/score.log 2>&1
"""

import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import Application, Vacancy
from ..services.glafira.scoring import score_pending_applications
from ..services.glafira.auto_qa import ask_auto_qa_questions

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """Оценивает неоценённых не-отказанных кандидатов по всем компаниям."""
    logger.info("Запуск авто-оценки неоценённых кандидатов")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    # expire_on_commit=False — score_pending_applications коммитит покандидатно.
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    total = {"scored": 0, "failed": 0, "companies": 0}

    try:
        async with async_session() as session:
            # Только компании, где реально есть что оценивать (есть заявка без
            # оценки и не в терминальном этапе) — чтобы вхолостую не дёргать остальных.
            result = await session.execute(
                select(Application.company_id)
                .where(
                    Application.ai_score.is_(None),
                    Application.stage.notin_(("rejected", "hired")),
                )
                .distinct()
            )
            company_ids = [row[0] for row in result]
            logger.info(f"Компаний с неоценёнными заявками: {len(company_ids)}")

            for company_id in company_ids:
                try:
                    stats = await score_pending_applications(session, company_id)
                    total["scored"] += stats.get("scored", 0)
                    total["failed"] += stats.get("failed", 0)
                    total["companies"] += 1
                    if stats.get("scored") or stats.get("failed"):
                        logger.info(
                            f"Компания {company_id}: оценено {stats.get('scored', 0)}, "
                            f"сбоев {stats.get('failed', 0)}"
                        )
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Ошибка авто-оценки компании {company_id}: {e}")

        logger.info(
            f"Оценка завершена: {total['companies']} компаний, "
            f"оценено {total['scored']}, сбоев {total['failed']}"
        )

        # П.2 — задать уточняющие вопросы (отдельный проход: не зависит от наличия
        # неоценённых; берём компании, где есть подходящие auto_qa-кандидаты на «Отклике»).
        qa_company_ids = (await session.execute(
            select(Application.company_id)
            .join(Vacancy, Application.vacancy_id == Vacancy.id)
            .where(
                Application.stage == "response",
                Application.auto_qa_asked_at.is_(None),
                Application.hh_negotiation_id.isnot(None),
                Vacancy.auto_qa.is_(True),
                Vacancy.glafira_mode.in_(("A", "B")),
                Vacancy.deleted_at.is_(None),
            )
            .distinct()
        )).scalars().all()
        qa_total = {"asked": 0}
        for company_id in qa_company_ids:
            try:
                qa_stats = await ask_auto_qa_questions(session, company_id)
                qa_total["asked"] += qa_stats.get("asked", 0)
            except Exception as e:
                await session.rollback()
                logger.error(f"Ошибка auto_qa (вопросы) компании {company_id}: {e}")
        if qa_total["asked"]:
            logger.info(f"Auto-QA: задано вопросов {qa_total['asked']}")

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
