"""
Диагностика отклика hh ПОД ТОКЕНОМ ПРАВИЛЬНОЙ КОМПАНИИ.

Аргумент — ЛИБО hh negotiation_id (число из hh-reject.log), ЛИБО наш candidate_id
(UUID из URL карточки). Скрипт находит Application, берёт токен ИМЕННО его компании
и печатает НАШЕ состояние + ПОЛНЫЙ ответ hh (state/employer_state/actions[]/resume/
manager/vacancy + сырой JSON), чтобы понять, почему discard падает resume_not_found,
хотя в вебе hh отказ доступен.

Запуск:
docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.hh_diag_negotiation <hh_negotiation_id | candidate_id>
"""

import asyncio
import json
import logging
import sys
import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import HhIntegration, Application, Candidate, Vacancy
from ..services.integrations.hh import client as hh_client
from ..services.integrations.hh.service import get_valid_access_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _is_uuid(s: str) -> bool:
    try:
        _uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.jobs.hh_diag_negotiation <hh_negotiation_id | candidate_id>")
        return
    arg = str(sys.argv[1])

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with async_session() as session:
            # Ищем Application: по candidate_id (UUID) ИЛИ по hh_negotiation_id (число).
            base = (
                select(Application, Candidate, Vacancy)
                .join(Candidate, Candidate.id == Application.candidate_id)
                .join(Vacancy, Vacancy.id == Application.vacancy_id)
                .where(Application.hh_negotiation_id.isnot(None))
            )
            if _is_uuid(arg):
                q = base.where(Application.candidate_id == _uuid.UUID(arg)).order_by(
                    Application.updated_at.desc()
                )
            else:
                q = base.where(Application.hh_negotiation_id == arg)

            rows = (await session.execute(q)).all()

            if not rows:
                # Fallback: возможно, дали hh_negotiation_id, которого у нас нет —
                # берём первую компанию (результат может быть неточным на чужом токене).
                if _is_uuid(arg):
                    print(f"❌ Application с candidate_id={arg} и hh_negotiation_id в БД не найден")
                    return
                company_id = (await session.execute(
                    select(HhIntegration.company_id)
                )).scalars().first()
                print(f"⚠️ Application с hh_negotiation_id={arg} в БД НЕ найден — токен первой компании {company_id}")
                if not company_id:
                    print("Нет компаний с интеграцией hh.ru")
                    return
                nid = arg
            else:
                if len(rows) > 1:
                    print(f"ℹ️ Найдено {len(rows)} откликов кандидата — беру самый свежий:")
                app, cand, vac = rows[0]
                company_id = app.company_id
                nid = str(app.hh_negotiation_id)
                print("=== НАШЕ состояние (из БД) ===")
                print("кандидат:", cand.full_name)
                print("вакансия:", vac.name)
                print("company_id:", company_id)
                print("hh_negotiation_id:", nid)
                print("stage:", app.stage)
                print("hh_chat_id:", app.hh_chat_id)
                print("hh_discard_synced_at:", app.hh_discard_synced_at)
                print("auto_reject_message (флаг вакансии):", vac.auto_reject_message)
                print("hh_vacancy_id (вакансии):", getattr(vac, "hh_vacancy_id", None))

            token = await get_valid_access_token(session, company_id)
            nego = await hh_client.get_negotiation(token, nid)

        print(f"\n=== hh negotiation {nid} (токен company {company_id}) ===")
        print("state:", nego.get("state"))
        print("employer_state:", nego.get("employer_state"))
        print("messaging_status:", nego.get("messaging_status"))
        print("has_updates:", nego.get("has_updates"))
        print("hidden:", nego.get("hidden"))
        print("decline_allowed:", nego.get("decline_allowed"))
        resume = nego.get("resume") or {}
        print("--- resume ---")
        print("resume.id:", resume.get("id"))
        print("resume.hidden:", resume.get("hidden"))
        print("resume.url:", resume.get("url") or resume.get("alternate_url"))
        vjob = nego.get("vacancy") or {}
        print("--- vacancy у отклика ---")
        print("vacancy.id:", vjob.get("id"))
        print("vacancy.name:", vjob.get("name"))
        mgr = nego.get("employer_manager") or nego.get("manager") or {}
        print("manager:", mgr)
        print("=== actions[] (что hh разрешает) ===")
        print(json.dumps(nego.get("actions"), ensure_ascii=False, indent=2))
        print("\n=== СЫРОЙ JSON отклика (для разбора) ===")
        print(json.dumps(nego, ensure_ascii=False, indent=2)[:6000])
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
