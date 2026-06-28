"""
Автоподбор — сервис сохранённых автопоисков резюме hh (saved searches).

Ф1: синхронизация списка сохранённых поисков работодателя с hh + чтение из кэша.
Не импортирует smart_search в обратную сторону — цикла нет
(smart_search НЕ импортирует auto_search).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qsl
from uuid import UUID

from sqlalchemy import select, desc, nullslast
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.auto_search import AutoSearch
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
