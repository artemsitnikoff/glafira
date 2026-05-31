"""Сервис для работы с hh.ru интеграцией"""

import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import HhIntegration, HhOauthState
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....core.errors import ValidationError, NotFoundError
from . import client as hh_client


async def get_integration(session: AsyncSession, company_id: UUID) -> Optional[HhIntegration]:
    """Получает интеграцию hh.ru для компании"""
    result = await session.execute(
        select(HhIntegration).where(HhIntegration.company_id == company_id)
    )
    return result.scalar_one_or_none()


async def start_oauth(session: AsyncSession, company_id: UUID, user_id: UUID) -> str:
    """
    Начинает OAuth flow, создает state запись и возвращает authorize URL

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя

    Returns:
        str: URL для редиректа в браузер

    Raises:
        ValidationError: при ошибке конфигурации
    """
    # Генерируем уникальный state
    state = secrets.token_urlsafe(32)

    # Создаем запись state (expires через 10 минут)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    oauth_state = HhOauthState(
        state=state,
        company_id=company_id,
        user_id=user_id,
        expires_at=expires_at
    )

    session.add(oauth_state)
    await session.commit()

    # Строим authorize URL
    authorize_url = hh_client.build_authorize_url(state)

    return authorize_url


async def complete_oauth(session: AsyncSession, code: str, state: str) -> HhIntegration:
    """
    Завершает OAuth flow, обменивает код на токены и создает/обновляет интеграцию

    Args:
        session: DB session
        code: authorization code от hh.ru
        state: state для проверки CSRF

    Returns:
        HhIntegration: созданная/обновленная интеграция

    Raises:
        ValidationError: при невалидном state или ошибке API
    """
    # Находим state запись
    result = await session.execute(
        select(HhOauthState).where(HhOauthState.state == state)
    )
    oauth_state = result.scalar_one_or_none()

    if not oauth_state:
        raise ValidationError("Невалидный или истекший state")

    # Проверяем срок действия
    if datetime.now(timezone.utc) > oauth_state.expires_at:
        # Удаляем истекший state
        await session.delete(oauth_state)
        await session.commit()
        raise ValidationError("Истекший state")

    company_id = oauth_state.company_id
    user_id = oauth_state.user_id

    try:
        # Обмениваем код на токены
        token_data = await hh_client.exchange_code(code)

        # Получаем информацию о пользователе
        me_data = await hh_client.get_me(token_data["access_token"])

        # Извлекаем employer_id
        hh_employer_id = None
        if "employer" in me_data and me_data["employer"] and "id" in me_data["employer"]:
            hh_employer_id = str(me_data["employer"]["id"])

        # Вычисляем время истечения токена
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

        # Шифруем токены
        encrypted_access = encrypt_text(token_data["access_token"])
        encrypted_refresh = encrypt_text(token_data["refresh_token"])

        # Проверяем существующую интеграцию
        existing = await get_integration(session, company_id)

        if existing:
            # Обновляем существующую
            existing.access_token = encrypted_access
            existing.refresh_token = encrypted_refresh
            existing.expires_at = expires_at
            existing.hh_employer_id = hh_employer_id
            existing.connected_by_user_id = user_id
            integration = existing
        else:
            # Создаем новую
            integration = HhIntegration(
                company_id=company_id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                hh_employer_id=hh_employer_id,
                connected_by_user_id=user_id
            )
            session.add(integration)

        # Удаляем использованный state
        await session.delete(oauth_state)

        # Сохраняем изменения
        await session.commit()

        # Записываем в аудит
        if user_id:
            await audit(
                session,
                action="hh_connected",
                entity_type="hh_integration",
                entity_id=integration.id,
                after={"hh_employer_id": hh_employer_id},
                actor_user_id=user_id,
                company_id=company_id
            )
            await session.commit()  # audit() добавляет запись после основного commit — персистим её

        return integration

    except Exception as e:
        # Удаляем state при ошибке
        await session.delete(oauth_state)
        await session.commit()
        raise


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID):
    """
    Отключает интеграцию hh.ru

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя

    Raises:
        NotFoundError: если интеграция не найдена
    """
    integration = await get_integration(session, company_id)

    if not integration:
        raise NotFoundError("Интеграция hh.ru не найдена")

    integration_id = integration.id

    await session.delete(integration)
    await session.commit()

    # Записываем в аудит
    await audit(
        session,
        action="hh_disconnected",
        entity_type="hh_integration",
        entity_id=integration_id,
        actor_user_id=user_id,
        company_id=company_id
    )
    await session.commit()  # audit() после delete-commit — персистим audit-запись


async def get_valid_access_token(session: AsyncSession, company_id: UUID) -> str:
    """
    Получает валидный access token, обновляя при необходимости

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        str: валидный access token

    Raises:
        NotFoundError: если интеграция не найдена
        ValidationError: при ошибке обновления токенов
    """
    integration = await get_integration(session, company_id)

    if not integration:
        raise NotFoundError("Интеграция hh.ru не найдена")

    # Проверяем срок действия токена (с запасом 5 минут)
    now = datetime.now(timezone.utc)
    expires_soon = integration.expires_at - timedelta(minutes=5)

    if now >= expires_soon:
        # Токен истек или истечет скоро, обновляем
        try:
            current_refresh = decrypt_text(integration.refresh_token)
            token_data = await hh_client.refresh_tokens(current_refresh)

            # Обновляем токены
            integration.access_token = encrypt_text(token_data["access_token"])
            integration.refresh_token = encrypt_text(token_data["refresh_token"])
            integration.expires_at = now + timedelta(seconds=token_data["expires_in"])

            await session.commit()

            return token_data["access_token"]

        except Exception as e:
            raise ValidationError(f"Не удалось обновить токены hh.ru: {e}")

    else:
        # Токен еще валидный
        return decrypt_text(integration.access_token)


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """
    Получает статус интеграции hh.ru

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        dict: статус интеграции
    """
    integration = await get_integration(session, company_id)

    if not integration:
        return {"connected": False}

    return {
        "connected": True,
        "hh_employer_id": integration.hh_employer_id,
        "connected_at": integration.created_at,
        "expires_at": integration.expires_at
    }