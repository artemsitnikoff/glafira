"""Подключение/статус интеграции Talantix (per-company).

Токены (пара access/refresh из ЛК Talantix) шифруются Fernet и НИКОГДА не
возвращаются наружу. Подключение валидируется реальным refresh + GraphQL-проверкой.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.errors import ValidationError
from ....models import TalantixIntegration
from ....services.audit import audit
from . import token as talantix_token
from .client import TalantixClient, TalantixError

logger = logging.getLogger(__name__)


async def save_config(
    session: AsyncSession,
    company_id: UUID,
    *,
    refresh_token: str,
    user_id: UUID,
) -> None:
    """Подключить Talantix: валидировать токен, сохранить свежую пару (Fernet), audit.

    Порядок: refresh (валидирует refresh_token и минтит свежий access, персистит новую
    пару) → лёгкая GraphQL-проверка соединения. Сбой любого шага → ValidationError,
    фейкового «подключено» нет.

    audit фиксирует ФАКТ подключения (НЕ значения токенов).
    """
    # 1. Валидация + сохранение свежей пары (в своей короткой сессии, commit внутри).
    await talantix_token.connect_and_store(
        company_id, refresh_token=refresh_token, user_id=user_id
    )

    # 2. Проверка соединения реальным GraphQL-запросом (свежий access уже в БД).
    try:
        async with TalantixClient(company_id) as client:
            await client.check_connection()
    except (TalantixError, ValidationError) as exc:
        raise ValidationError(
            f"Токен Talantix сохранён, но проверка соединения не прошла: {exc}"
        ) from exc

    # 3. audit (без значений токенов).
    integration = (
        await session.execute(
            select(TalantixIntegration).where(
                TalantixIntegration.company_id == company_id
            )
        )
    ).scalar_one_or_none()
    await audit(
        session,
        action="talantix_connected",
        entity_type="integration",
        entity_id=integration.id if integration else company_id,
        after={"provider": "talantix", "action": "tokens_saved"},
        actor_user_id=user_id,
        company_id=company_id,
    )


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус интеграции Talantix для компании (БЕЗ раскрытия токенов)."""
    integration = (
        await session.execute(
            select(TalantixIntegration).where(
                TalantixIntegration.company_id == company_id
            )
        )
    ).scalar_one_or_none()

    connected = bool(integration and integration.refresh_token)
    return {
        "connected": connected,
        "connected_at": integration.created_at.isoformat()
        if (integration and connected and integration.created_at)
        else None,
        "expires_at": integration.expires_at.isoformat()
        if (integration and connected and integration.expires_at)
        else None,
    }


async def is_connected(session: AsyncSession, company_id: UUID) -> bool:
    integration = (
        await session.execute(
            select(TalantixIntegration).where(
                TalantixIntegration.company_id == company_id
            )
        )
    ).scalar_one_or_none()
    return bool(integration and integration.refresh_token)
