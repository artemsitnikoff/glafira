from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from ...models import User
from ...core.errors import NotFoundError, ValidationError, ConflictError
from ...core.security import get_password_hash, verify_password
from ...services.audit import audit
from ...services.phone import normalize_phone_e164


async def get_profile(session: AsyncSession, user_id: UUID) -> User:
    """Get user profile by ID"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("Пользователь")
    return user


async def update_profile(session: AsyncSession, user_id: UUID, data, company_id: UUID) -> User:
    """Update user profile"""
    user = await get_profile(session, user_id)

    # Store original values for audit
    before = {
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "position": user.position,
        "timezone": user.timezone,
        "language": user.language,
        "date_format": user.date_format,
        "avatar_url": user.avatar_url,
    }

    # Email — нормализуем (trim+lower), иначе User@x.com и user@x.com — почти-дубли,
    # а вход по email регистрозависимо путается. Проверка глобальной уникальности (исключая
    # себя) — без неё смена на занятый email падала бы IntegrityError → 500.
    new_email = data.email.strip().lower() if data.email is not None else None
    if new_email is not None and new_email != user.email:
        existing = (await session.execute(
            select(User).where(User.email == new_email, User.id != user.id)
        )).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("Пользователь с таким email уже существует")

    # Update fields
    if data.full_name is not None:
        if not data.full_name.strip():
            raise ValidationError("ФИО не может быть пустым")
        user.full_name = data.full_name.strip()
    if new_email is not None:
        user.email = new_email
    if data.phone is not None:
        user.phone = normalize_phone_e164(data.phone)
    if data.position is not None:
        user.position = data.position
    if data.timezone is not None:
        user.timezone = data.timezone
    if data.language is not None:
        user.language = data.language
    if data.date_format is not None:
        user.date_format = data.date_format
    if data.avatar_url is not None:
        user.avatar_url = data.avatar_url

    await session.flush()

    # Audit log
    after = {
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "position": user.position,
        "timezone": user.timezone,
        "language": user.language,
        "date_format": user.date_format,
        "avatar_url": user.avatar_url,
    }

    await audit(
        session,
        action="update_profile",
        entity_type="user",
        entity_id=user.id,
        before=before,
        after=after,
        actor_user_id=user_id,
        company_id=company_id,
    )

    return user


async def change_password(
    session: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
    new_password_confirm: str,
    company_id: UUID,
) -> User:
    """Change user password"""
    if new_password != new_password_confirm:
        raise ValidationError("Пароли не совпадают")

    if not verify_password(current_password, user.password_hash):
        raise ValidationError("Неверный текущий пароль")

    user.password_hash = get_password_hash(new_password)

    await session.flush()

    # Audit log
    await audit(
        session,
        action="change_password",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        company_id=company_id,
    )

    return user