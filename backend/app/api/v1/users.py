from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...schemas.user import UserShort, UserCreate, UserCreateResult, UserUpdate, UserListItem
from ...schemas.base import Paginated, MessageResult
from ...services.user import get_user, create_user, update_user, delete_user, get_users_paginated
from ...services.integrations.smtp import service as smtp_service
from ...models import User
from ...core.errors import ForbiddenError

router = APIRouter()


@router.get("", response_model=Paginated[UserListItem])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by full name or email"),
    role: Optional[str] = Query(None, description="Filter by role (admin, recruiter, manager)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id)
):
    """Get paginated list of users for company with filters"""
    result = await get_users_paginated(
        session, company_id, page, page_size,
        search=search, role=role, is_active=is_active
    )
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


@router.post("/", response_model=UserCreateResult, status_code=201)
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

    # Отправляем доступы на email сотрудника (как при импорте из Б24). Если SMTP не
    # настроен/ошибка — не падаем: emailed=False, temp_password вернём для ручной передачи.
    emailed = False
    try:
        await smtp_service.send_credentials_email(
            session, company_id,
            to=user_data.email,
            full_name=user_data.full_name,
            temp_password=temp_password,
        )
        emailed = True
    except Exception:
        emailed = False

    # Return user data with temp_password included once
    response_data = UserShort.model_validate(user).model_dump()
    response_data["temp_password"] = temp_password
    response_data["emailed"] = emailed
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


@router.delete("/{user_id}", response_model=MessageResult)
async def delete_user_by_id(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id)
):
    """Delete user (admin only)"""
    if current_user.role != "admin":
        raise ForbiddenError("Только администратор может удалять пользователей")

    await delete_user(session, user_id, company_id, current_user.id)
    await session.commit()

    return MessageResult(message="Пользователь удалён")