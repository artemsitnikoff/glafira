from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import User, Candidate, Vacancy


async def get_billing(session: AsyncSession, company_id: UUID) -> dict:
    """Get billing information for company (MVP placeholder)"""
    # Реальные counts
    users_count = (await session.execute(
        select(func.count(User.id)).where(
            User.company_id == company_id,
            User.is_active == True  # учитываем is_active поле
        )
    )).scalar() or 0

    candidates_count = (await session.execute(
        select(func.count(Candidate.id)).where(
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)  # КРИТИЧНО: только живые
        )
    )).scalar() or 0

    vacancies_count = (await session.execute(
        select(func.count(Vacancy.id)).where(
            Vacancy.company_id == company_id,
            Vacancy.status == 'active',
            Vacancy.deleted_at.is_(None)  # учитываем soft-delete для vacancies
        )
    )).scalar() or 0

    return {
        "plan": "MVP",
        "is_demo": True,
        "users_limit": 10,
        "candidates_limit": 1000,
        "vacancies_limit": 50,
        "current_users": users_count,
        "current_candidates": candidates_count,
        "current_vacancies": vacancies_count,
        "billing_until": None,
    }