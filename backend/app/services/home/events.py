"""Сервис для получения ленты событий"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID

from ...models import Event
from ...schemas.home import EventOut


async def list_recent_events(session: AsyncSession, company_id: UUID, limit: int = 30, candidate_id: UUID | None = None) -> list[EventOut]:
    """Получает список последних событий компании"""
    query = select(Event).where(
        Event.company_id == company_id
    ).options(
        selectinload(Event.actor_user)
    )

    if candidate_id:
        query = query.where(Event.candidate_id == candidate_id)

    query = query.order_by(
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
            created_at=event.created_at,
            actor_type=event.actor_type,
            actor_name=event.actor_user.full_name if event.actor_user else None
        )
        for event in events
    ]