"""Сервис для анализа источников кандидатов"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...core.periods import parse_home_period
from ...models import Candidate
from ...schemas.home import SourceItem


async def top_sources(session: AsyncSession, company_id: UUID, period: str = 'month') -> list[SourceItem]:
    """Получает топ источников кандидатов за период"""
    period_days = parse_home_period(period)
    now = datetime.now(timezone.utc)

    query = select(
        Candidate.source,
        func.count(Candidate.id).label('count')
    ).where(
        Candidate.company_id == company_id
    )

    # Применяем фильтр по периоду если не 'all'
    if period_days is not None:
        start_date = now - timedelta(days=period_days)
        query = query.where(Candidate.created_at >= start_date)

    query = query.group_by(Candidate.source).order_by(func.count(Candidate.id).desc())

    result = await session.execute(query)
    rows = result.fetchall()

    return [
        SourceItem(source=source or 'Не указан', count=count)
        for source, count in rows
    ]