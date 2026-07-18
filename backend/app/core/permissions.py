"""Permission utilities"""

import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists
from fastapi import Request, Depends

from ..models import User, VacancyTeam, Vacancy, Application
from ..deps import get_current_user
from ..core.errors import ForbiddenError


async def is_user_assigned_to_vacancy(
    session: AsyncSession,
    user_id: uuid.UUID,
    vacancy_id: uuid.UUID,
    company_id: uuid.UUID
) -> bool:
    """
    Check if user is assigned to vacancy.
    User is assigned if:
    1. There is a VacancyTeam record with this user_id and vacancy_id
    2. OR Vacancy.responsible_user_id == user_id
    """
    # Check VacancyTeam assignment
    team_check = await session.execute(
        select(exists().where(
            (VacancyTeam.user_id == user_id) &
            (VacancyTeam.vacancy_id == vacancy_id) &
            (VacancyTeam.company_id == company_id)
        ))
    )

    if team_check.scalar():
        return True

    # Check responsible_user_id assignment
    responsible_check = await session.execute(
        select(exists().where(
            (Vacancy.id == vacancy_id) &
            (Vacancy.responsible_user_id == user_id) &
            (Vacancy.company_id == company_id)
        ))
    )

    return responsible_check.scalar()


async def can_manager_access_candidate(
    session: AsyncSession,
    user_id: uuid.UUID,
    candidate_id: uuid.UUID,
    company_id: uuid.UUID
) -> bool:
    """
    Check if manager can access candidate.
    Manager can access candidate if they have applications in vacancies
    where the manager is assigned.
    """
    # Check if candidate has applications in vacancies where manager is assigned
    query = select(exists().where(
        (Application.candidate_id == candidate_id) &
        (Application.company_id == company_id) &
        (
            # Check via VacancyTeam assignment
            exists().select_from(VacancyTeam).where(
                (VacancyTeam.vacancy_id == Application.vacancy_id) &
                (VacancyTeam.user_id == user_id) &
                (VacancyTeam.company_id == company_id)
            ) |
            # Check via responsible_user_id assignment
            exists().select_from(Vacancy).where(
                (Vacancy.id == Application.vacancy_id) &
                (Vacancy.responsible_user_id == user_id) &
                (Vacancy.company_id == company_id)
            )
        )
    ))

    result = await session.execute(query)
    return result.scalar()


async def require_admin(current_user: User = Depends(get_current_user)) -> None:
    """Require user to have admin role"""
    if current_user.role != "admin":
        raise ForbiddenError("Требуется роль администратора")


async def require_settings_read_access(current_user: User = Depends(get_current_user)) -> None:
    """Require settings read access (admin or recruiter)"""
    if current_user.role not in ["admin", "recruiter"]:
        raise ForbiddenError("Недостаточно прав для чтения настроек")


async def settings_permission_dependency(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> None:
    """
    Settings permission dependency based on HTTP method:
    - GET (read): admin + recruiter
    - POST/PATCH/PUT/DELETE (write): admin only
    """
    # Свой профиль (/settings/profile*) доступен всем ролям — личный аккаунт
    # пользователя, а не «настройки системы».
    if "/settings/profile" in request.url.path:
        return

    method = request.method.upper()

    if method == "GET":
        # Read access: admin + recruiter
        if current_user.role not in ["admin", "recruiter"]:
            raise ForbiddenError("Недостаточно прав для чтения настроек")
    else:
        # Write access: admin only
        if current_user.role != "admin":
            raise ForbiddenError("Только администратор может изменять настройки")


async def require_recruiter_or_admin(current_user: User = Depends(get_current_user)) -> None:
    """Доступ только admin/recruiter (менеджер запрещён)."""
    if current_user.role not in ("admin", "recruiter"):
        raise ForbiddenError("Недостаточно прав")


async def forbid_hiring_manager(current_user: User = Depends(get_current_user)) -> None:
    """Deny-by-default гард для роли «нанимающий менеджер» (hiring_manager).

    Нанимающий менеджер — класс изоляции ВНУТРИ компании: видит ТОЛЬКО свои заявки
    (модуль /requests), больше ничего (ни кандидатов, ни вакансий, ни аналитики, ни
    настроек, ни пула). Навешивается на include_router ВСЕХ роутеров данных в
    api/v1/router.py; НЕ навешивается на auth, /requests и публичные роуты.

    Безопасно добавлять широко: hiring_manager — новая роль, существующих юзеров с ней
    ещё нет, поэтому гард никого не ломает, но делает изоляцию airtight (не зависит от
    того, что каждый эндпоинт правильно проверит роль внутри).
    """
    if current_user.role == "hiring_manager":
        raise ForbiddenError("Недостаточно прав")


async def integrations_permission_dependency(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> None:
    """
    Integrations permission dependency based on HTTP method:
    - GET (status): admin + recruiter
    - POST/PATCH/PUT/DELETE (config/test/disconnect/connect/import/link/publish): admin only
    """
    method = request.method.upper()

    if method == "GET":
        # Status read: admin + recruiter
        if current_user.role not in ["admin", "recruiter"]:
            raise ForbiddenError("Недостаточно прав для просмотра интеграций")
    else:
        # Configuration changes: admin only
        if current_user.role != "admin":
            raise ForbiddenError("Только администратор может управлять интеграциями")