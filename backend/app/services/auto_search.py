"""
Автоподбор — сервис сохранённых автопоисков резюме hh (saved searches).

Ф1: синхронизация списка сохранённых поисков работодателя с hh + чтение из кэша.
Не импортирует smart_search в обратную сторону — цикла нет
(smart_search НЕ импортирует auto_search).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qsl
from uuid import UUID

from sqlalchemy import select, desc, nullslast
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError
from ..models.auto_search import AutoSearch
from ..models.candidate import Candidate
from .candidate import format_duration
from .integrations.hh import client as hh_client
from .integrations.hh.service import get_valid_access_token
from .smart_search import check_access, _parse_api_quota

logger = logging.getLogger(__name__)


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

    return {
        "items": items_mapped,
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": 10,
    }
