import math
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User
from ..core.security import verify_password, create_access_token, create_refresh_token
from ..core.errors import InvalidCredentialsError, UserInactiveError, AccountLockedError
from ..config import settings


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    """Authenticate user by email and password with account lockout protection.

    Защита от брутфорса: счётчик failed_login_attempts и locked_until хранятся
    в БД — работает надёжно при 2+ воркерах (в отличие от in-memory).

    Anti-enumeration: неизвестный email возвращает ту же ошибку 401, что и
    неверный пароль. locked_until раскрывается только когда аккаунт УЖЕ залочен
    (ошибка 429) — не раскрывает факт блокировки при новой неудачной попытке.
    """
    result = await session.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()

    # Неизвестный email — сразу 401, счётчик не трогаем (anti-enumeration)
    if user is None:
        raise InvalidCredentialsError()

    now = datetime.now(timezone.utc)

    # Проверяем lockout
    if user.locked_until is not None:
        # locked_until может быть naive (без tzinfo) — нормализуем
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)

        if locked_until > now:
            # Аккаунт залочен — раскрываем оставшееся время (пользователь уже знает о блокировке)
            remaining = locked_until - now
            minutes_left = math.ceil(remaining.total_seconds() / 60)
            raise AccountLockedError(minutes_left=minutes_left)
        else:
            # Окно истекло — сбрасываем и продолжаем проверку пароля
            user.failed_login_attempts = 0
            user.locked_until = None

    # Проверяем пароль
    password_correct = verify_password(password, user.password_hash)

    if not password_correct:
        # Инкрементируем счётчик неудач
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
            # Порог достигнут — блокируем аккаунт
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)

        await session.commit()

        # Не раскрываем статус блокировки — единый ответ «неверные учётные данные»
        raise InvalidCredentialsError()

    # Пароль верен
    if not user.is_active:
        # Не сбрасываем счётчик у заблокированного пользователя
        raise UserInactiveError()

    # Успешный вход — сбрасываем счётчик неудач
    if user.failed_login_attempts != 0 or user.locked_until is not None:
        user.failed_login_attempts = 0
        user.locked_until = None

    await session.commit()
    await session.refresh(user)

    return user


def create_tokens(user_id: str) -> tuple[str, str]:
    """Create access and refresh tokens"""
    access_token = create_access_token(data={"sub": user_id})
    refresh_token = create_refresh_token(data={"sub": user_id})
    return access_token, refresh_token
