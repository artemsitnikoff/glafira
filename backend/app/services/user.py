from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError
from uuid import UUID
import math
import secrets
from typing import Optional

from ..models import User, Vacancy, Employee
from ..schemas.user import UserCreate, UserUpdate, UserShort, UserListItem
from ..schemas.base import Paginated
from ..core.security import get_password_hash
from ..core.errors import NotFoundError, ConflictError, ForbiddenError
from ..services.audit import audit



async def get_users_paginated(
    session: AsyncSession,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Paginated[UserListItem]:
    """Get paginated list of users with filters"""
    # Build filters
    filters = [User.company_id == company_id]

    if search:
        search_term = f"%{search.strip()}%"
        filters.append(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        )

    if role:
        filters.append(User.role == role)

    if is_active is not None:
        filters.append(User.is_active == is_active)

    where_clause = and_(*filters)

    # Count total
    total_result = await session.execute(
        select(func.count(User.id)).where(where_clause)
    )
    total = total_result.scalar_one()

    # Get paginated data
    offset = (page - 1) * page_size
    result = await session.execute(
        select(User)
        .where(where_clause)
        .order_by(User.full_name)
        .offset(offset)
        .limit(page_size)
    )
    users = result.scalars().all()

    # Convert to UserListItem schemas
    items = [UserListItem.model_validate(user) for user in users]

    pages = math.ceil(total / page_size) if total > 0 else 0

    return Paginated[UserListItem](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages
    )


async def get_user(session: AsyncSession, user_id: UUID, company_id: UUID) -> User:
    """Get user by ID"""
    result = await session.execute(
        select(User)
        .where(User.id == user_id, User.company_id == company_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("Пользователь")
    return user


async def create_user(
    session: AsyncSession,
    user_data: UserCreate,
    company_id: UUID,
    actor_user_id: UUID
) -> tuple[User, str]:
    """Create new user"""
    # Check if email already exists globally (unique constraint is global)
    existing_user_result = await session.execute(
        select(User).where(User.email == user_data.email)
    )
    existing_user = existing_user_result.scalar_one_or_none()
    if existing_user:
        raise ConflictError("Пользователь с таким email уже существует")

    # Generate temp password (should be changed on first login)
    temp_password = secrets.token_urlsafe(16)

    user = User(
        company_id=company_id,
        email=user_data.email,
        password_hash=get_password_hash(temp_password),
        full_name=user_data.full_name,
        role=user_data.role,
        position=user_data.position,
    )

    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # Defense-in-depth: catch race condition
        raise ConflictError("Пользователь с таким email уже существует")

    # Audit log
    await audit(
        session,
        action="create",
        entity_type="user",
        entity_id=user.id,
        after={
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "position": user.position,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return user, temp_password


async def update_user(
    session: AsyncSession,
    user_id: UUID,
    user_data: UserUpdate,
    company_id: UUID,
    actor_user_id: UUID
) -> User:
    """Update user"""
    user = await get_user(session, user_id, company_id)

    # Guard: cannot deactivate yourself
    if (user_data.is_active is False and user_id == actor_user_id):
        raise ForbiddenError("Нельзя деактивировать самого себя")

    # Guard: cannot deactivate the last active admin
    if (user_data.is_active is False and user.role == "admin"):
        # Count active admins in the company
        admin_count_result = await session.execute(
            select(func.count(User.id)).where(
                and_(
                    User.company_id == company_id,
                    User.role == "admin",
                    User.is_active == True,
                    User.id != user_id  # Exclude current user
                )
            )
        )
        active_admin_count = admin_count_result.scalar_one()
        if active_admin_count == 0:
            raise ConflictError("Нельзя деактивировать последнего активного администратора. Сначала назначьте другого администратора.")

    # Save old values for audit
    before = {
        "full_name": user.full_name,
        "role": user.role,
        "position": user.position,
        "is_active": user.is_active,
    }

    # Update fields
    if user_data.full_name is not None:
        user.full_name = user_data.full_name
    if user_data.role is not None:
        user.role = user_data.role
    if user_data.position is not None:
        user.position = user_data.position
    if user_data.is_active is not None:
        user.is_active = user_data.is_active

    await session.flush()

    # Audit log
    await audit(
        session,
        action="update",
        entity_type="user",
        entity_id=user.id,
        before=before,
        after={
            "full_name": user.full_name,
            "role": user.role,
            "position": user.position,
            "is_active": user.is_active,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return user


async def delete_user(
    session: AsyncSession,
    user_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> None:
    """Delete user"""
    user = await get_user(session, user_id, company_id)

    # Guard: cannot delete yourself
    if user_id == actor_user_id:
        raise ForbiddenError("Нельзя удалить самого себя")

    # Guard: cannot delete the last admin
    if user.role == "admin":
        # Count active admins in the company
        admin_count_result = await session.execute(
            select(func.count(User.id)).where(
                and_(
                    User.company_id == company_id,
                    User.role == "admin",
                    User.is_active == True,
                    User.id != user_id  # Exclude current user
                )
            )
        )
        active_admin_count = admin_count_result.scalar_one()
        if active_admin_count == 0:
            raise ConflictError("Нельзя удалить последнего администратора. Сначала назначьте другого администратора.")

    # FK на User (responsible/manager/recruiter) = SET NULL, удалить технически можно.
    # Но не осиротляем молча: если за юзером закреплены НЕархивные вакансии или
    # сотрудники — блокируем, просим переназначить.
    vacancy_count_result = await session.execute(
        select(func.count(Vacancy.id)).where(
            and_(
                Vacancy.company_id == company_id,
                Vacancy.responsible_user_id == user_id,
                Vacancy.status != "archived"
            )
        )
    )
    vacancy_count = vacancy_count_result.scalar_one()

    # Check employees as manager
    managed_count_result = await session.execute(
        select(func.count(Employee.id)).where(
            and_(
                Employee.company_id == company_id,
                Employee.manager_user_id == user_id
            )
        )
    )
    managed_count = managed_count_result.scalar_one()

    # Check employees as recruiter
    recruited_count_result = await session.execute(
        select(func.count(Employee.id)).where(
            and_(
                Employee.company_id == company_id,
                Employee.recruiter_user_id == user_id
            )
        )
    )
    recruited_count = recruited_count_result.scalar_one()

    if vacancy_count > 0 or managed_count > 0 or recruited_count > 0:
        details = []
        if vacancy_count > 0:
            details.append(f"ответственный за {vacancy_count} вакансий")
        if managed_count > 0:
            details.append(f"менеджер {managed_count} сотрудников")
        if recruited_count > 0:
            details.append(f"рекрутёр {recruited_count} сотрудников")

        message = f"Пользователь {details[0]}"
        if len(details) > 1:
            message += f" и {', '.join(details[1:])}"
        message += ". Сначала переназначьте ответственность."

        raise ConflictError(message)

    # Audit log before deletion
    await audit(
        session,
        action="delete",
        entity_type="user",
        entity_id=user.id,
        before={
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "position": user.position,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    # Delete user (FK constraints will SET NULL automatically)
    await session.delete(user)
    await session.flush()