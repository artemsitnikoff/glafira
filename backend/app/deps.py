from typing import AsyncGenerator
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from .database import get_db
from .config import settings
from .core.security import decode_token
from .core.errors import InvalidCredentialsError, UserInactiveError, SubscriptionExpiredError
from .models import User, Company

oauth2_scheme = HTTPBearer()


def company_subscription_active(company: "Company | None") -> bool:
    """Тариф компании активен: запись есть и paid_until сегодня/в будущем.
    NULL paid_until → НЕ активен (биллинг fail-closed: не оплачено = заблокировано)."""
    if company is None or company.paid_until is None:
        return False
    return company.paid_until >= datetime.now(timezone.utc).date()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from JWT token"""
    try:
        payload = decode_token(token.credentials)
        user_id = payload.get("sub")
        if user_id is None:
            raise InvalidCredentialsError()

        # Check that this is an access token, not a refresh token
        if payload.get("type") != "access":
            raise InvalidCredentialsError()

        # Convert to UUID safely
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise InvalidCredentialsError()

    except ValueError:
        raise InvalidCredentialsError()

    # Query user from database
    result = await session.execute(
        select(User).where(User.id == user_uuid)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise InvalidCredentialsError()

    if not user.is_active:
        raise UserInactiveError()

    # Billing gate: компания юзера должна иметь активный тариф (scoped по company_id)
    company = await session.get(Company, user.company_id)
    if not company_subscription_active(company):
        raise SubscriptionExpiredError()

    return user


async def get_current_company_id(
    user: User = Depends(get_current_user)
) -> UUID:
    """Get company_id from current user"""
    return user.company_id