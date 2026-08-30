"""Разовая склейка накопленных дублей кандидатов (пункт 2 правки дедупа).

Пункт 1 (перекрытие «крана» при импорте hh-отклика — новые отклики не плодят дубль)
сделан в v1.7.22. Здесь — РАЗОВЫЙ проход по УЖЕ накопленным дублям: находим сильные
связные компоненты (см. `services/candidate_merge.py`), сливаем каждый в одного
«золотого» кандидата, спорное (слабые рёбра) — печатаем в REVIEW-список на глазной
просмотр (НЕ трогаем).

⚠️ Джоб ИНЕРТНЫЙ: по умолчанию DRY-RUN (ничего не пишет). Запуск разовый, руками, НЕ в
cron. Автодеплой лишь делает джоб доступным, не запускает.

Режимы / флаги:
  (без флагов)          DRY-RUN: всё вычисляет, печатает отчёт, НИ ОДНОЙ записи в БД.
  --execute             применить мерж (savepoint на компонент, commit пачками).
  --company <uuid>      только эта компания (иначе — все компании с кандидатами).
  --limit N             только первые N компонентов на компанию (проба).
  --include-review      подробнее печатать Tier-2 (review) кандидатов.

Запуск (VPS, разово):
  cd /var/www/glafira && docker compose -f docker-compose.prod.yml run --rm backend \
    python -m app.jobs.merge_duplicate_candidates 2>&1 | tee -a merge-dry.log      # проба
  … python -m app.jobs.merge_duplicate_candidates --execute 2>&1 | tee -a merge.log  # применить

Перед --execute на проде — БЭКАП БД (scripts/backup_all.sh).
"""

import argparse
import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..config import settings
from ..models import Candidate
from ..services.candidate_merge import (
    CompanyReport,
    ComponentResult,
    compute_components,
    load_company_candidates,
    merge_component,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("merge_duplicates")

COMMIT_BATCH = 25  # компонентов между commit-ами в режиме --execute


async def _company_ids(session, only_company: str | None) -> list[uuid.UUID]:
    if only_company:
        return [uuid.UUID(only_company)]
    res = await session.execute(
        select(Candidate.company_id)
        .where(Candidate.deleted_at.is_(None))
        .group_by(Candidate.company_id)
    )
    return [row[0] for row in res.all()]


async def process_company(
    session,
    company_id: uuid.UUID,
    *,
    execute: bool,
    limit: int | None,
) -> CompanyReport:
    candidates = await load_company_candidates(session, company_id)
    components, review = compute_components(candidates)

    report = CompanyReport(
        company_id=company_id,
        total_candidates=len(candidates),
        components_total=len(components),
        review=review,
    )

    to_process = components[:limit] if limit else components
    for comp_ids in to_process:
        report.components_processed += 1
        sp = await session.begin_nested()
        try:
            res = await merge_component(session, company_id, comp_ids)
        except Exception as exc:  # noqa: BLE001 — один битый компонент не валит остальные
            await sp.rollback()
            logger.exception("Компонент %s: ошибка мержа", [str(x) for x in comp_ids])
            report.errors += 1
            report.results.append(ComponentResult(company_id=company_id, error=str(exc)))
            continue

        if execute:
            await sp.commit()  # release savepoint; итог зафиксирует commit пачки ниже
        else:
            await sp.rollback()  # DRY-RUN: гарантированно ни одной записи
            session.expire_all()

        report.results.append(res)
        if not res.skipped and not res.error:
            report.merged_components += 1
            report.trashed += len(res.merged_ids)
            report.apps_reparented += res.apps_reparented
            report.app_collisions_resolved += res.app_collisions_resolved
            report.collision_details.extend(res.collision_details)

        if execute and report.components_processed % COMMIT_BATCH == 0:
            await session.commit()

    if execute:
        await session.commit()
    else:
        await session.rollback()
        session.expire_all()

    return report


def print_report(report: CompanyReport, *, execute: bool, include_review: bool) -> None:
    head = "ПРИМЕНЕНО" if execute else "DRY-RUN (ничего не записано)"
    print(f"\n=== Компания {report.company_id} — {head} ===")
    print(f"  Кандидатов (живых):           {report.total_candidates}")
    print(f"  Сильных компонентов (Tier-1): {report.components_total} "
          f"(обработано {report.components_processed})")
    print(f"  Слито компонентов:            {report.merged_components}")
    print(f"  Кандидатов в утиль:           {report.trashed}")
    print(f"  Заявок перенесено:            {report.apps_reparented}")
    print(f"  Коллизий «одна вакансия»:     {report.app_collisions_resolved}")
    if report.errors:
        print(f"  ⚠️ Ошибок компонентов:        {report.errors}")

    if report.collision_details:
        print("  Коллизии (какой этап победил):")
        for d in report.collision_details[:200]:
            print(f"    вакансия {d['vacancy_id']}: победил '{d['winning_stage']}' "
                  f"(проиграли: {', '.join(d['losing_stages'])})")

    if report.review:
        print(f"  Tier-2 REVIEW (на глазной просмотр, НЕ слито): {len(report.review)}")
        limit_rows = None if include_review else 40
        for item in report.review[:limit_rows] if limit_rows else report.review:
            print(f"    {item.candidate_id}  «{item.name}»  phone={item.phone}  "
                  f"email={item.email}  source={item.source}")
        if limit_rows and len(report.review) > limit_rows:
            print(f"    … ещё {len(report.review) - limit_rows} "
                  f"(покажет --include-review)")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Склейка дублей кандидатов (пункт 2 дедупа).")
    parser.add_argument("--execute", action="store_true",
                        help="применить мерж (без флага — DRY-RUN, ничего не пишется)")
    parser.add_argument("--company", type=str, default=None, help="UUID компании (иначе все)")
    parser.add_argument("--limit", type=int, default=None,
                        help="только первые N компонентов на компанию (проба)")
    parser.add_argument("--include-review", action="store_true",
                        help="печатать Tier-2 (review) кандидатов полностью")
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    logger.info("Старт merge_duplicate_candidates [%s]%s%s", mode,
                f" company={args.company}" if args.company else "",
                f" limit={args.limit}" if args.limit else "")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    totals = {"components": 0, "merged": 0, "trashed": 0, "apps": 0, "collisions": 0,
              "review": 0, "errors": 0}
    try:
        async with async_session() as session:
            company_ids = await _company_ids(session, args.company)
            logger.info("Компаний к обработке: %d", len(company_ids))
            for cid in company_ids:
                report = await process_company(
                    session, cid, execute=args.execute, limit=args.limit
                )
                print_report(report, execute=args.execute, include_review=args.include_review)
                totals["components"] += report.components_total
                totals["merged"] += report.merged_components
                totals["trashed"] += report.trashed
                totals["apps"] += report.apps_reparented
                totals["collisions"] += report.app_collisions_resolved
                totals["review"] += len(report.review)
                totals["errors"] += report.errors
    finally:
        await engine.dispose()

    print("\n=== ИТОГО по всем компаниям ===")
    print(f"  Сильных компонентов:   {totals['components']}")
    print(f"  Слито компонентов:     {totals['merged']}")
    print(f"  Кандидатов в утиль:    {totals['trashed']}")
    print(f"  Заявок перенесено:     {totals['apps']}")
    print(f"  Коллизий разрешено:    {totals['collisions']}")
    print(f"  Tier-2 review:         {totals['review']}")
    if totals["errors"]:
        print(f"  ⚠️ Ошибок компонентов: {totals['errors']}")
    if not args.execute:
        print("\nЭто был DRY-RUN — в БД НИЧЕГО не записано. Для применения: --execute "
              "(предварительно сделать бэкап БД).")


if __name__ == "__main__":
    asyncio.run(main())
