"""Подключение/статус интеграции Talantix (per-company).

Токены (пара access/refresh из ЛК Talantix) шифруются Fernet и НИКОГДА не
возвращаются наружу/в логи. На connect пользователь вставляет ЦЕЛИКОМ JSON токенов
из ЛК (страница токена — SPA, серверный GET отдаёт HTML-шелл без токенов, поэтому
«сходить по ссылке» на бэке нельзя — принимаем именно текст JSON).
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.errors import ValidationError
from ....models import TalantixIntegration
from ....services.audit import audit
from . import token as talantix_token
from .client import TalantixClient, TalantixError, probe_access_token

logger = logging.getLogger(__name__)


def _parse_connect_input(raw: str) -> tuple[str | None, str, datetime | None]:
    """Разобрать вход connect → (access_token|None, refresh_token, access_expires_at|None).

    Форматы:
    1. JSON-блок из ЛК `{access_token, expires_in, refresh_token, created_at, ...}` →
       (access, refresh, expires_at). expires_at = (created_at/1000 если есть, иначе now)
       + expires_in.
    2. Ссылка на страницу токена (talantix.ru/docs/pages/token…) → ValidationError 400
       (это SPA, токенов в URL нет; не делаем вид, что «сходили по ссылке»).
    3. Просто строка → трактуем как refresh_token (прежнее поведение), access=None.

    НЕ логирует значения токенов.
    """
    s = (raw or "").strip()
    if not s:
        raise ValidationError("Вставьте JSON токенов из ЛК Talantix (весь блок {…})")

    # 2. Ссылка на страницу токена — токенов там нет (SPA).
    if "docs/pages/token" in s.lower():
        raise ValidationError(
            "Это ссылка на страницу токена. Откройте её в браузере и вставьте JSON "
            "целиком (весь блок {…})."
        )

    # 1. Попытка распарсить JSON-блок.
    parsed = None
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    if isinstance(parsed, dict):
        refresh = str(parsed.get("refresh_token") or "").strip()
        if not refresh:
            raise ValidationError(
                "В JSON нет refresh_token — вставьте весь блок токенов из ЛК Talantix"
            )
        access = str(parsed.get("access_token") or "").strip() or None
        expires_at = None
        expires_in = parsed.get("expires_in")
        if expires_in:
            try:
                created_at = parsed.get("created_at")
                base = (
                    datetime.fromtimestamp(int(created_at) / 1000, tz=timezone.utc)
                    if created_at
                    else datetime.now(timezone.utc)
                )
                expires_at = base + timedelta(seconds=int(expires_in))
            except (TypeError, ValueError, OSError):
                expires_at = None
        return access, refresh, expires_at

    # 3. Просто строка → refresh_token.
    return None, s, None


async def save_config(
    session: AsyncSession,
    company_id: UUID,
    *,
    token_input: str,
    user_id: UUID,
) -> None:
    """Подключить Talantix: разобрать JSON-блок, валидировать, сохранить пару (Fernet), audit.

    Валидация access-first (не ротируем свежий refresh зря): пробуем ПЕРЕДАННЫЙ
    access_token лёгким GraphQL-запросом. Если сработал → сохраняем пару как есть
    (свежий refresh не тратится). Если нет/access не передан → фолбэк на refresh
    (обмен валидирует refresh + минтит свежий access, ротирует, персистит) + GraphQL-
    проверка. Сбой обоих путей → ValidationError, фейкового «подключено» нет.

    audit фиксирует ФАКТ подключения (НЕ значения токенов).
    """
    access, refresh, expires_at = _parse_connect_input(token_input)

    # 1. access-first: пробуем пастнутый access напрямую (без рефреша).
    validated_by_access = False
    if access:
        validated_by_access = await probe_access_token(access)

    if validated_by_access:
        # Свежий refresh не трогаем — сохраняем пару как есть.
        await talantix_token.save_tokens(
            company_id,
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            user_id=user_id,
        )
    else:
        # 2. Фолбэк: обмен refresh (валидирует + минтит свежий access + ротирует + персистит).
        await talantix_token.connect_and_store(
            company_id, refresh_token=refresh, user_id=user_id
        )
        # Финальная GraphQL-проверка свежего access (не рефрешит — токен свежий).
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
