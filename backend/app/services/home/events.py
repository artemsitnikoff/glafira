"""Сервис для получения ленты событий"""

from sqlalchemy import select, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID

from ...models import Event, Application, VacancyTeam, Vacancy
from ...schemas.home import EventOut


async def list_recent_events(session: AsyncSession, company_id: UUID, limit: int = 30, candidate_id: UUID | None = None, manager_user_id: UUID | None = None) -> list[EventOut]:
    """Получает список последних событий компании"""
    query = select(Event).where(
        Event.company_id == company_id,
        # События истории заявок (type='request') — только в карточке заявки, не в общей ленте.
        Event.request_id.is_(None),
    ).options(
        selectinload(Event.actor_user),
        selectinload(Event.candidate),
        selectinload(Event.vacancy)
    )

    if candidate_id:
        query = query.where(Event.candidate_id == candidate_id)

    if manager_user_id is not None:
        allowed_candidate_ids = (
            select(Application.candidate_id)
            .where(
                Application.company_id == company_id,
                or_(
                    exists().select_from(VacancyTeam).where(
                        (VacancyTeam.vacancy_id == Application.vacancy_id)
                        & (VacancyTeam.user_id == manager_user_id)
                        & (VacancyTeam.company_id == company_id)
                    ),
                    exists().select_from(Vacancy).where(
                        (Vacancy.id == Application.vacancy_id)
                        & (Vacancy.responsible_user_id == manager_user_id)
                        & (Vacancy.company_id == company_id)
                    ),
                ),
            )
        )
        query = query.where(Event.candidate_id.in_(allowed_candidate_ids))

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
            actor_name=event.actor_user.full_name if event.actor_user else None,
            candidate_id=event.candidate_id,
            candidate_name=event.candidate.full_name if event.candidate else None,
            vacancy_id=event.vacancy_id,
            vacancy_name=event.vacancy.name if event.vacancy else None
        )
        for event in events
    ]