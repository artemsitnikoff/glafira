from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
import math

from ..models import User
from ..schemas.user import UserCreate, UserUpdate, UserShort
from ..schemas.base import Paginated
from ..core.security import get_password_hash
from ..core.errors import NotFoundError
from ..services.audit import audit


async def get_users(session: AsyncSession, company_id: UUID) -> list[User]:
    """Get all users for company"""
    result = await session.execute(
        select(User)
        .where(User.company_id == company_id)
        .order_by(User.full_name)
    )
    return result.scalars().all()


async def get_users_paginated(
    session: AsyncSession,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24
) -> Paginated[UserShort]:
    """Get paginated list of users"""
    # Count total
    total_result = await session.execute(
        select(func.count(User.id)).where(User.company_id == company_id)
    )
    total = total_result.scalar_one()

    # Get paginated data
    offset = (page - 1) * page_size
    result = await session.execute(
        select(User)
        .where(User.company_id == company_id)
        .order_by(User.full_name)
        .offset(offset)
        .limit(page_size)
    )
    users = result.scalars().all()

    # Convert to UserShort schemas
    items = [UserShort.model_validate(user) for user in users]

    pages = math.ceil(total / page_size) if total > 0 else 0

    return Paginated[UserShort](
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
) -> User:
    """Create new user"""
    # Generate temp password (should be changed on first login)
    temp_password = "change_me"

    user = User(
        company_id=company_id,
        email=user_data.email,
        password_hash=get_password_hash(temp_password),
        full_name=user_data.full_name,
        role=user_data.role,
        position=user_data.position,
    )

    session.add(user)
    await session.flush()

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

    return user


async def update_user(
    session: AsyncSession,
    user_id: UUID,
    user_data: UserUpdate,
    company_id: UUID,
    actor_user_id: UUID
) -> User:
    """Update user"""
    user = await get_user(session, user_id, company_id)

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