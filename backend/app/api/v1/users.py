from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...schemas.user import UserShort, UserCreate, UserUpdate
from ...schemas.base import Paginated
from ...services.user import get_users, get_user, create_user, update_user
from ...models import User
from ...core.errors import ForbiddenError

router = APIRouter()


@router.get("", response_model=Paginated[UserShort])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get paginated list of users for company"""
    from ...services.user import get_users_paginated
    result = await get_users_paginated(session, company_id, page, page_size)
    return result


@router.get("/{user_id}", response_model=UserShort)
async def get_user_by_id(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get user by ID"""
    user = await get_user(session, user_id, company_id)
    return UserShort.model_validate(user)


@router.post("/", response_model=UserShort, status_code=201)
async def create_new_user(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Create new user (admin only)"""
    if current_user.role != "admin":
        raise ForbiddenError("Только администратор может создавать пользователей")

    user, temp_password = await create_user(session, user_data, company_id, current_user.id)
    await session.commit()

    # Return user data with temp_password included once
    response_data = UserShort.model_validate(user).model_dump()
    response_data["temp_password"] = temp_password
    return response_data


@router.patch("/{user_id}", response_model=UserShort)
async def update_user_by_id(
    user_id: UUID,
    user_data: UserUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Update user (admin only)"""
    if current_user.role != "admin":
        raise ForbiddenError("Только администратор может редактировать пользователей")

    user = await update_user(session, user_id, user_data, company_id, current_user.id)
    await session.commit()

    return UserShort.model_validate(user)