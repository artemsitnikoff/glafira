"""Сервис для получения ленты событий"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...models import Event
from ...schemas.home import EventOut


async def list_recent_events(session: AsyncSession, company_id: UUID, limit: int = 30) -> list[EventOut]:
    """Получает список последних событий компании"""
    query = select(Event).where(
        Event.company_id == company_id
    ).order_by(
        Event.created_at.desc(),
        Event.id.desc()
    ).limit(limit)

    result = await session.execute(query)
    events = result.scalars().all()

    return [
        EventOut(
            id=event.id,
            type=event.type,
            text=event.text,
            entities=event.entities,
            created_at=event.created_at
        )
        for event in events
    ]