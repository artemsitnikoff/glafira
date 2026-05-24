from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User
from ..core.security import verify_password, create_access_token, create_refresh_token
from ..core.errors import InvalidCredentialsError, UserInactiveError


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    """Authenticate user by email and password"""
    result = await session.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    if not user.is_active:
        raise UserInactiveError()

    return user


def create_tokens(user_id: str) -> tuple[str, str]:
    """Create access and refresh tokens"""
    access_token = create_access_token(data={"sub": user_id})
    refresh_token = create_refresh_token(data={"sub": user_id})
    return access_token, refresh_token