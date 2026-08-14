"""
Диагностика отклика hh: дамп employer_state + actions[] (id, enabled, method, url,
arguments) ПОД ТОКЕНОМ ПРАВИЛЬНОЙ КОМПАНИИ. Нужен, чтобы понять, КАК правильно
отклонять отклик (напр. discard_by_employer вернул resume_not_found).

Аргумент — hh negotiation_id (тот, что в hh-reject.log). Скрипт находит Application
с этим hh_negotiation_id в НАШЕЙ базе, берёт токен ИМЕННО его компании (важно: с
несколькими компаниями токен первой попавшейся дал бы ложный resume_not_found), и
печатает и hh-состояние, и наше (stage / hh_chat_id / hh_discard_synced_at / флаг).

Запуск:
docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.hh_diag_negotiation <hh_negotiation_id>
"""

import asyncio
import json
import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ..config import settings
from ..models import HhIntegration, Application, Candidate, Vacancy
from ..services.integrations.hh import client as hh_client
from ..services.integrations.hh.service import get_valid_access_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.jobs.hh_diag_negotiation <hh_negotiation_id>")
        return
    nid = str(sys.argv[1])

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with async_session() as session:
            # 1) Находим отклик в НАШЕЙ базе → его компания (правильный токен!)
            row = (await session.execute(
                select(Application, Candidate, Vacancy)
                .join(Candidate, Candidate.id == Application.candidate_id)
                .join(Vacancy, Vacancy.id == Application.vacancy_id)
                .where(Application.hh_negotiation_id == nid)
            )).first()

            if row:
                app, cand, vac = row
                company_id = app.company_id
                print("=== НАШЕ состояние (из БД) ===")
                print("кандидат:", cand.full_name)
                print("вакансия:", vac.name)
                print("company_id:", company_id)
                print("stage:", app.stage)
                print("hh_chat_id:", app.hh_chat_id)
                print("hh_discard_synced_at:", app.hh_discard_synced_at)
                print("auto_reject_message (флаг вакансии):", vac.auto_reject_message)
            else:
                # Отклика с таким hh_negotiation_id у нас нет — берём первую компанию
                # (диагностика будет под её токеном, возможен ложный resume_not_found).
                company_id = (await session.execute(
                    select(HhIntegration.company_id)
                )).scalars().first()
                print(f"⚠️ Application с hh_negotiation_id={nid} в БД НЕ найден — "
                      f"токен первой компании {company_id} (результат может быть неточным)")
                if not company_id:
                    print("Нет компаний с интеграцией hh.ru")
                    return

            token = await get_valid_access_token(session, company_id)
            nego = await hh_client.get_negotiation(token, nid)

        print(f"\n=== hh negotiation {nid} (под токеном company {company_id}) ===")
        print("state:", nego.get("state"))
        print("employer_state:", nego.get("employer_state"))
        print("messaging_status:", nego.get("messaging_status"))
        print("has_updates:", nego.get("has_updates"))
        print("=== actions[] (как отклонять / что доступно) ===")
        print(json.dumps(nego.get("actions"), ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
