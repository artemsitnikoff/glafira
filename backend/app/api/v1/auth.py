from fastapi import APIRouter, Depends, Response, HTTPException, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from ...config import settings
from ...database import get_db
from ...deps import get_current_user
from ...schemas.auth import LoginRequest, TokenResponse, UserMe
from ...schemas.base import MessageResult
from ...services.auth import authenticate_user, create_tokens
from ...core.security import decode_token
from ...core.errors import InvalidCredentialsError
from ...models import User

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db)
):
    """Login with email and password"""
    user = await authenticate_user(session, login_data.email, login_data.password)
    access_token, refresh_token = create_tokens(str(user.id))

    # Set refresh token in HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/api/v1/auth/refresh",
        max_age=14 * 24 * 60 * 60  # 14 days
    )

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    session: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(None)
):
    """Refresh access token using refresh token from cookie"""
    if refresh_token is None:
        raise InvalidCredentialsError()

    try:
        payload = decode_token(refresh_token)
        user_id = payload.get("sub")
        if user_id is None:
            raise InvalidCredentialsError()

        # Check that this is a refresh token, not an access token
        if payload.get("type") != "refresh":
            raise InvalidCredentialsError()

        # Convert to UUID safely
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise InvalidCredentialsError()

    except ValueError:
        raise InvalidCredentialsError()

    # Load user from database and check if active
    result = await session.execute(
        select(User).where(User.id == user_uuid)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise InvalidCredentialsError()

    if not user.is_active:
        raise InvalidCredentialsError()

    # Create new tokens
    new_access_token, new_refresh_token = create_tokens(user_id)

    # Update refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/api/v1/auth/refresh",
        max_age=14 * 24 * 60 * 60
    )

    return TokenResponse(access_token=new_access_token)


@router.post("/logout", response_model=MessageResult)
async def logout(response: Response):
    """Logout and clear refresh token"""
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth/refresh"
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserMe)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return UserMe.model_validate(current_user)