"""
Автоподбор — сервис сохранённых автопоисков резюме hh (saved searches).

Ф1: синхронизация списка сохранённых поисков работодателя с hh + чтение из кэша.
Не импортирует smart_search в обратную сторону — цикла нет
(smart_search НЕ импортирует auto_search).
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qsl
from uuid import UUID

from sqlalchemy import select, desc, nullslast, update, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError, ValidationError, ConflictError, GlafiraParseError
from ..database import AsyncSessionLocal
from ..models.auto_search import AutoSearch, AutoSearchRun
from ..models.candidate import Candidate
from ..models import Vacancy
from .candidate import format_duration
from .integrations.hh import client as hh_client
from .integrations.hh.service import get_valid_access_token
from .smart_search import check_access, _parse_api_quota, _is_ai_credits_error
from .base_search import _create_synthetic_vacancy_for_scoring, GLAFIRA_MAX_EVALUATE
from .glafira.scoring import score_resume_dict
from .settings.glafira import get_company_openrouter_key, get_company_llm_model

logger = logging.getLogger(__name__)

_auto_active_tasks: dict = {}
AUTO_STUCK_RECONCILE_SECONDS = 270


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_saved_search_url(url: str) -> list[tuple[str, str]]:
    """Разбирает query-строку saved_search-URL в список пар (без page/per_page).

    Понадобится в Ф2 для перенаправления параметров поиска в /resumes.
    Определяем сейчас, чтобы зафиксировать контракт.
    """
    if not url:
        return []
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    return [(k, v) for k, v in pairs if k not in ("page", "per_page")]


async def sync_saved_searches(session: AsyncSession, company_id: UUID) -> list[AutoSearch]:
    """Синхронизирует сохранённые автопоиски резюме hh в локальную таблицу auto_searches.

    UPSERT по (company_id, hh_saved_search_id). При обновлении не трогает
    пользовательские поля basis/auto_eval/last_seen_at — только то, что приходит из hh.
    """
    token = await get_valid_access_token(session, company_id)
    raw = await hh_client.list_saved_resume_searches(token)

    items = raw.get("items") or [] if isinstance(raw, dict) else []

    for item in items:
        if not isinstance(item, dict):
            continue

        hh_id = item.get("id")
        if hh_id is None:
            continue
        hh_id = str(hh_id)

        name = item.get("name") or "Без названия"

        items_obj = item.get("items") or {}
        if not isinstance(items_obj, dict):
            items_obj = {}
        new_obj = item.get("new_items") or {}
        if not isinstance(new_obj, dict):
            new_obj = {}

        items_url = items_obj.get("url")
        new_items_url = new_obj.get("url")

        total = items_obj.get("count")
        if total is None:
            total = item.get("found")

        new_count = new_obj.get("count")
        if new_count is None:
            new_count = 0

        subscribed = bool(item.get("subscription", False))

        # region best-effort: hh может отдать area как dict {name}, как строку, или не отдать
        area = item.get("area") or item.get("region")
        if isinstance(area, dict):
            region = area.get("name")
        elif isinstance(area, str):
            region = area
        else:
            region = None

        existing = (
            await session.execute(
                select(AutoSearch).where(
                    AutoSearch.company_id == company_id,
                    AutoSearch.hh_saved_search_id == hh_id,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.name = name
            existing.region = region
            existing.items_url = items_url
            existing.new_items_url = new_items_url
            existing.total = total
            existing.new_count = new_count
            existing.subscribed = subscribed
            existing.last_synced_at = _utc_naive_now()
            # НЕ трогаем basis / auto_eval / last_seen_at — это пользовательские поля
        else:
            obj = AutoSearch(
                company_id=company_id,
                hh_saved_search_id=hh_id,
                name=name,
                region=region,
                items_url=items_url,
                new_items_url=new_items_url,
                total=total,
                new_count=new_count,
                subscribed=subscribed,
                auto_eval=False,
                basis=None,
                last_synced_at=_utc_naive_now(),
            )
            session.add(obj)

    await session.commit()
    return await list_auto_searches(session, company_id)


async def list_auto_searches(session: AsyncSession, company_id: UUID) -> list[AutoSearch]:
    """Читает автопоиски компании из кэша. Сортировка: сначала с новыми (new_count desc), затем по имени."""
    result = await session.execute(
        select(AutoSearch)
        .where(AutoSearch.company_id == company_id)
        .order_by(nullslast(desc(AutoSearch.new_count)), AutoSearch.name)
    )
    return list(result.scalars().all())


async def get_auto_access(session: AsyncSession, company_id: UUID) -> dict:
    """Доступ к Автоподбору: hh подключён + (best-effort) остаток платного пула."""
    has_access, has_paid_access, reason = await check_access(session, company_id)

    pool_left = None
    if has_access:
        try:
            token = await get_valid_access_token(session, company_id)
            me = await hh_client.get_me(token)
            employer_id = (me.get("employer") or {}).get("id")
            if employer_id:
                quota = await hh_client.get_payable_api_actions(token, str(employer_id))
                _u, limited_remaining, _h = _parse_api_quota(quota)
                # ⚠️ pool_left = limited_remaining (остаток платных API-действий) —
                # ПРИБЛИЗИТЕЛЬНО; точное поле контактного пула пиннится на живом токене.
                pool_left = limited_remaining
        except Exception as e:
            pool_left = None
            logger.warning("[auto] pool_left best-effort failed: %s", e)

    return {
        "has_access": has_access,
        "has_paid_access": has_paid_access,
        "reason": reason,
        "pool_left": pool_left,
    }


async def get_auto_candidates(
    session: AsyncSession,
    company_id: UUID,
    auto_search_id: UUID,
    segment: str = "all",
    page: int = 0,
    sort: str = "updated",
) -> dict:
    """Кандидаты автопоиска на БЕСПЛАТНЫХ полях hh, синхронно, с пагинацией по 10.

    Читает items_url (segment='all') или new_items_url (segment='new') сохранённого
    автопоиска hh и отдаёт страницу резюме без открытия контактов/чтения полного резюме.
    sort принимается, пока игнорируется (резюме отдаёт hh в порядке поиска).
    """
    auto_search = (
        await session.execute(
            select(AutoSearch).where(
                AutoSearch.company_id == company_id,
                AutoSearch.id == auto_search_id,
            )
        )
    ).scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")

    url = auto_search.new_items_url if segment == "new" else auto_search.items_url
    if not url:
        return {"items": [], "total": 0, "page": page, "pages": 0, "per_page": 10}

    params = parse_saved_search_url(url) + [("per_page", "10"), ("page", str(page))]

    token = await get_valid_access_token(session, company_id)
    raw = await hh_client.search_resumes(token, params)

    items = raw.get("items") or []
    # ДИАГ-ЛОГ: только КЛЮЧИ первого item (структура ответа), НЕ значения (PII).
    if items and isinstance(items[0], dict):
        logger.info("[auto] resume item keys=%s", list(items[0].keys()))

    # БАТЧ-дедуп: один запрос по всем валидным hh_resume_id страницы.
    resume_ids = [str(item.get("id")) for item in items
                  if isinstance(item, dict) and item.get("id") is not None]
    taken_ids: set[str] = set()
    if resume_ids:
        rows = await session.execute(
            select(Candidate.extra["hh_resume_id"].astext).where(
                Candidate.company_id == company_id,
                Candidate.extra["hh_resume_id"].astext.in_(resume_ids),
                Candidate.deleted_at.is_(None),
            )
        )
        taken_ids = {r for r in rows.scalars().all() if r is not None}

    items_mapped: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = item.get("id")
        if rid is None:
            continue
        hh_resume_id = str(rid)

        area = item.get("area") or {}
        salary_obj = item.get("salary") or {}
        total_exp = item.get("total_experience") or {}

        last_job = None
        experience_list = item.get("experience") or []
        if isinstance(experience_list, list):
            for exp in experience_list:
                if not isinstance(exp, dict):
                    continue
                position = exp.get("position")
                company = exp.get("company")
                parts = [p for p in (position, company) if p]
                last_job = " · ".join(parts) if parts else None
                break

        items_mapped.append({
            "hh_resume_id": hh_resume_id,
            "title": item.get("title"),
            "age": item.get("age"),
            "city": area.get("name") if isinstance(area, dict) else None,
            "anonymous": bool(item.get("hidden_fields")),
            "salary": salary_obj.get("amount") if isinstance(salary_obj, dict) else None,
            "experience": format_duration((total_exp.get("months") if isinstance(total_exp, dict) else None) or 0),
            "skills": item.get("skill_set") or [],
            "last_job": last_job,
            "updated_at": item.get("updated_at"),
            "is_new": segment == "new",
            "score": None,
            "taken": hh_resume_id in taken_ids,
        })

    total = min(raw.get("found", 0) or 0, 2000)
    pages = math.ceil(total / 10) if total else 0

    if segment == "new":
        auto_search.last_seen_at = _utc_naive_now()
        await session.commit()

    # Инжектируем score из последнего завершённого прогона
    last_run_result = await session.execute(
        select(AutoSearchRun)
        .where(
            AutoSearchRun.company_id == company_id,
            AutoSearchRun.auto_search_id == auto_search_id,
            AutoSearchRun.status == "done",
        )
        .order_by(desc(AutoSearchRun.created_at))
        .limit(1)
    )
    last_run = last_run_result.scalar_one_or_none()
    if last_run and last_run.scored_candidates:
        score_map = {
            str(c.get("hh_resume_id")): c.get("score")
            for c in last_run.scored_candidates
            if isinstance(c, dict) and c.get("score") is not None
        }
        for it in items_mapped:
            if str(it.get("hh_resume_id", "")) in score_map:
                it["score"] = score_map[str(it["hh_resume_id"])]
    if sort == "score":
        items_mapped.sort(
            key=lambda x: (x.get("score") is None, -(x.get("score") or 0))
        )

    return {
        "items": items_mapped,
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": 10,
    }


# === ФАЗА 3: Основа оценки + AI-оценка в фоне ===

async def set_basis(session: AsyncSession, company_id: UUID, auto_search_id: UUID, basis: dict) -> AutoSearch:
    """Задать основу оценки для автопоиска (vacancy или prompt)."""
    from uuid import UUID as _UUID

    result = await session.execute(
        select(AutoSearch).where(
            AutoSearch.company_id == company_id,
            AutoSearch.id == auto_search_id,
        )
    )
    auto_search = result.scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")

    kind = basis.get("kind")
    if kind == "vacancy":
        vacancy_id_raw = basis.get("vacancy_id")
        try:
            vacancy_uuid = _UUID(str(vacancy_id_raw))
        except Exception:
            raise NotFoundError("Вакансия")
        vacancy_result = await session.execute(
            select(Vacancy).where(
                Vacancy.id == vacancy_uuid,
                Vacancy.company_id == company_id,
                Vacancy.deleted_at.is_(None),
            )
        )
        if vacancy_result.scalar_one_or_none() is None:
            raise NotFoundError("Вакансия")
    elif kind == "prompt":
        prompt = (basis.get("prompt") or "").strip()
        if len(prompt) < 3:
            raise ValidationError("Укажите промпт не короче 3 символов")
    else:
        raise ValidationError("Некорректная основа оценки")

    auto_search.basis = basis
    await session.commit()
    return auto_search


async def set_auto_eval(session: AsyncSession, company_id: UUID, auto_search_id: UUID, enabled: bool) -> AutoSearch:
    """Включить/выключить AI-оценку для автопоиска."""
    result = await session.execute(
        select(AutoSearch).where(
            AutoSearch.company_id == company_id,
            AutoSearch.id == auto_search_id,
        )
    )
    auto_search = result.scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")
    if enabled and auto_search.basis is None:
        raise ValidationError("Сначала задайте основу оценки")
    auto_search.auto_eval = enabled
    await session.commit()
    return auto_search


async def start_auto_evaluate(
    session: AsyncSession,
    company_id: UUID,
    auto_search_id: UUID,
    segment: str = "all",
    n: int | None = None,
) -> UUID:
    """TOCTOU-безопасный старт фонового прогона AI-оценки."""
    result = await session.execute(
        select(AutoSearch).where(
            AutoSearch.company_id == company_id,
            AutoSearch.id == auto_search_id,
        )
    )
    auto_search = result.scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")
    if auto_search.basis is None:
        raise ValidationError("Сначала задайте основу оценки")

    to_eval = min(n or GLAFIRA_MAX_EVALUATE, GLAFIRA_MAX_EVALUATE)
    run = AutoSearchRun(
        company_id=company_id,
        auto_search_id=auto_search_id,
        status="running",
        stage="evaluating",
        basis=dict(auto_search.basis),
        to_evaluate=to_eval,
        evaluated=0,
        scored_candidates=[],
    )
    session.add(run)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("Оценка уже идёт")

    run_id = run.id
    task = asyncio.create_task(
        _run_auto_evaluate(run_id, company_id, auto_search_id, segment, n)
    )
    _auto_active_tasks[run_id] = task
    task.add_done_callback(lambda t: _auto_active_tasks.pop(run_id, None))
    return run_id


async def _run_auto_evaluate(
    run_id: UUID,
    company_id: UUID,
    auto_search_id: UUID,
    segment: str,
    n: int | None,
) -> None:
    """Фоновая AI-оценка кандидатов автопоиска ТОЛЬКО по бесплатным полям hh (без get_resume_by_id)."""

    async def _inner() -> None:
        token = None
        basis: dict = {}
        vacancy_proxy = None
        url = None
        api_key = None
        model = None

        # INIT: короткая сессия
        async with AsyncSessionLocal() as session:
            run = await session.get(AutoSearchRun, run_id)
            if run is None:
                return
            basis = run.basis or {}

            try:
                token = await get_valid_access_token(session, company_id)
            except Exception as e:
                run.status = "error"
                run.error = f"Ошибка hh-токена: {str(e)[:300]}"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return

            as_result = await session.execute(
                select(AutoSearch).where(
                    AutoSearch.company_id == company_id,
                    AutoSearch.id == auto_search_id,
                )
            )
            auto_search = as_result.scalar_one_or_none()
            if auto_search is None:
                run.status = "error"
                run.error = "Автопоиск не найден"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return

            url = auto_search.new_items_url if segment == "new" else auto_search.items_url

            try:
                api_key = await get_company_openrouter_key(session, company_id)
            except Exception as e:
                run.status = "error"
                run.error = f"OpenRouter не настроен: {str(e)[:300]}"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return

            model = await get_company_llm_model(session, company_id)

            kind = basis.get("kind")
            if kind == "vacancy":
                from uuid import UUID as _UUID
                try:
                    vacancy_uuid = _UUID(str(basis.get("vacancy_id")))
                except Exception:
                    run.status = "error"
                    run.error = "Некорректный ID вакансии-основы"
                    run.finished_at = _utc_naive_now()
                    await session.commit()
                    return
                vac_result = await session.execute(
                    select(Vacancy).where(
                        Vacancy.id == vacancy_uuid,
                        Vacancy.company_id == company_id,
                        Vacancy.deleted_at.is_(None),
                    )
                )
                vacancy = vac_result.scalar_one_or_none()
                if vacancy is None:
                    run.status = "error"
                    run.error = "Вакансия-основа удалена"
                    run.finished_at = _utc_naive_now()
                    await session.commit()
                    return
                vacancy_data = {
                    "name": getattr(vacancy, "name", None),
                    "city": getattr(vacancy, "city", None),
                    "salary_from": getattr(vacancy, "salary_from", None),
                    "salary_to": getattr(vacancy, "salary_to", None),
                    "currency": getattr(vacancy, "currency", None),
                    "description": getattr(vacancy, "description", None),
                    "recruiter_scoring_instructions": getattr(
                        vacancy, "recruiter_scoring_instructions", None
                    ),
                    "glafira_mode": getattr(vacancy, "glafira_mode", "A"),
                    "auto_move": getattr(vacancy, "auto_move", False),
                    "auto_move_threshold": getattr(vacancy, "auto_move_threshold", None),
                }
                vacancy_proxy = type("AutoVacancyProxy", (), vacancy_data)()
            elif kind == "prompt":
                vacancy_proxy = _create_synthetic_vacancy_for_scoring(
                    basis.get("prompt", "")
                )
            else:
                run.status = "error"
                run.error = "Некорректная основа оценки"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return
        # INIT-сессия закрыта

        if not url:
            try:
                async with AsyncSessionLocal() as session:
                    run = await session.get(AutoSearchRun, run_id)
                    if run:
                        run.status = "done"
                        run.stage = "done"
                        run.note = "Нет кандидатов в автопоиске"
                        run.finished_at = _utc_naive_now()
                        await session.commit()
            except Exception as e:
                logger.error("[auto_eval] Не удалось финализировать пустой прогон: %s", e)
            return

        cap = min(n or GLAFIRA_MAX_EVALUATE, GLAFIRA_MAX_EVALUATE)
        accumulated: list[dict] = []
        for page in range(20):
            try:
                params = parse_saved_search_url(url) + [
                    ("per_page", "50"),
                    ("page", str(page)),
                ]
                res = await asyncio.wait_for(
                    hh_client.search_resumes(token, params), timeout=45
                )
                page_items = res.get("items") or []
                if not page_items:
                    break
                accumulated.extend(page_items)
                if len(accumulated) >= cap:
                    break
            except asyncio.TimeoutError:
                logger.warning("[auto_eval] Таймаут пагинации на странице %d", page)
                break
            except Exception as e:
                logger.warning("[auto_eval] Ошибка пагинации: %s", e)
                break

        items = accumulated[:cap]

        if not items:
            try:
                async with AsyncSessionLocal() as session:
                    run = await session.get(AutoSearchRun, run_id)
                    if run:
                        run.status = "done"
                        run.stage = "done"
                        run.note = "Нет кандидатов для оценки"
                        run.finished_at = _utc_naive_now()
                        await session.commit()
            except Exception as e:
                logger.error("[auto_eval] Не удалось финализировать пустой список: %s", e)
            return

        # Обновить to_evaluate реальным числом
        try:
            async with AsyncSessionLocal() as session:
                run = await session.get(AutoSearchRun, run_id)
                if run:
                    run.to_evaluate = len(items)
                    await session.commit()
        except Exception as e:
            logger.warning("[auto_eval] Не удалось обновить to_evaluate: %s", e)

        scored_candidates: list[dict] = []
        evaluated = 0
        credits_note: str | None = None

        for item in items:
            try:
                result = await asyncio.wait_for(
                    score_resume_dict(item, vacancy_proxy, company_id, api_key, model),
                    timeout=180,
                )
                record = {
                    "hh_resume_id": str(item.get("id")),
                    "title": item.get("title"),
                    "score": result.get("score"),
                    "verdict": result.get("verdict"),
                    "summary": result.get("summary"),
                }
                scored_candidates.append(record)
                evaluated += 1
                try:
                    async with AsyncSessionLocal() as session:
                        run = await session.get(AutoSearchRun, run_id)
                        if run:
                            run.scored_candidates = list(scored_candidates)
                            run.evaluated = evaluated
                            await session.commit()
                except Exception as e:
                    logger.warning("[auto_eval] Не удалось обновить прогресс: %s", e)
            except asyncio.TimeoutError:
                logger.warning("[auto_eval] Таймаут оценки резюме %s", item.get("id"))
                continue
            except Exception as e:
                reason = str(e)
                if _is_ai_credits_error(reason, None):
                    credits_note = "AI-кредиты исчерпаны"
                    break
                else:
                    logger.warning(
                        "[auto_eval] Ошибка оценки резюме %s: %s", item.get("id"), e
                    )
                    continue

        # ФИНАЛ
        try:
            async with AsyncSessionLocal() as session:
                run = await session.get(AutoSearchRun, run_id)
                if run:
                    run.status = "done"
                    run.stage = "done"
                    run.scored_candidates = list(scored_candidates)
                    run.evaluated = evaluated
                    run.finished_at = _utc_naive_now()
                    if credits_note:
                        run.note = credits_note
                    await session.commit()
        except Exception as e:
            logger.error("[auto_eval] Не удалось сохранить финал: %s", e)

    try:
        timeout_s = max(900, (n or GLAFIRA_MAX_EVALUATE) * 200)
        await asyncio.wait_for(_inner(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            async with AsyncSessionLocal() as s:
                run = await s.get(AutoSearchRun, run_id)
                if run and run.status == "running":
                    run.status = "error"
                    run.error = "timeout"
                    run.finished_at = _utc_naive_now()
                    await s.commit()
        except Exception as e:
            logger.error("[auto_eval] Финал по таймауту: %s", e)
    except Exception as e:
        try:
            async with AsyncSessionLocal() as s:
                run = await s.get(AutoSearchRun, run_id)
                if run and run.status == "running":
                    run.status = "error"
                    run.error = str(e)[:500]
                    run.finished_at = _utc_naive_now()
                    await s.commit()
        except Exception as fe:
            logger.error("[auto_eval] Двойной сбой: %s", fe)
    finally:
        _auto_active_tasks.pop(run_id, None)


async def get_auto_run_status(session: AsyncSession, company_id: UUID, run_id: UUID) -> AutoSearchRun:
    """Статус прогона AI-оценки с reconcile застрявших."""
    result = await session.execute(
        select(AutoSearchRun).where(
            AutoSearchRun.id == run_id,
            AutoSearchRun.company_id == company_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise NotFoundError("Прогон")

    # Reconcile застрявших
    if run.status == "running" and run.updated_at is not None:
        updated = run.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        scored = run.scored_candidates or []
        if age >= AUTO_STUCK_RECONCILE_SECONDS and scored:
            run_pk = run.id
            run.status = "done"
            run.stage = "done"
            run.evaluated = len(scored)
            run.finished_at = _utc_naive_now()
            if not run.note:
                run.note = (
                    "Авто-финализация при чтении: фоновая задача не обновила статус"
                )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                re_result = await session.execute(
                    select(AutoSearchRun).where(AutoSearchRun.id == run_pk)
                )
                run = re_result.scalar_one_or_none()

    return run


async def sweep_orphaned_auto_runs() -> None:
    """Закрывает зависшие прогоны AI-оценки при старте сервера."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
        async with AsyncSessionLocal() as session:
            stmt = (
                update(AutoSearchRun)
                .where(
                    AutoSearchRun.status == "running",
                    AutoSearchRun.updated_at < cutoff,
                )
                .values(
                    status="error",
                    error="Прервано (зависание/перезапуск)",
                    finished_at=_utc_naive_now(),
                )
                .returning(AutoSearchRun.id)
            )
            result = await session.execute(stmt)
            ids = result.scalars().all()
            if ids:
                await session.commit()
                logger.info(
                    "[auto_eval] sweep: закрыто %d зависших прогонов: %s",
                    len(ids),
                    ids,
                )
    except Exception as e:
        logger.error("[auto_eval] sweep_orphaned_auto_runs ошибка: %s", e)
