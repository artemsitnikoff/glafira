"""Сервис OAuth-интеграции Хабр Карьера.

ТОЛЬКО подключение (получить + сохранить токен per-company).
Приём откликов / поиск резюме / синхронизация данных НЕ реализованы —
приложение ещё не одобрено Хабром, а хранить данные резюме нельзя по правилам Хабра.
"""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlencode, quote
from uuid import UUID

import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ....models.habr_integration import HabrIntegration, HabrOauthState
from ....config import settings
from ....services.settings.crypto import encrypt_text
from ....core.errors import ValidationError

logger = logging.getLogger(__name__)

# TTL временного state OAuth-флоу
_STATE_TTL_MINUTES = 10


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус интеграции Хабр Карьера для компании."""
    result = await session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.access_token:
        return {
            "connected": False,
            "habr_login": None,
            "expires_at": None,
        }

    return {
        "connected": True,
        "habr_login": integration.habr_login,
        "expires_at": integration.expires_at,
    }


async def start_oauth(session: AsyncSession, company_id: UUID, user_id: UUID) -> str:
    """Генерирует authorize URL для OAuth-флоу Хабр Карьера.

    Создаёт запись HabrOauthState (TTL 10 мин) и возвращает URL,
    на который нужно перенаправить браузер пользователя.

    Raises:
        ValidationError: если HABR_CLIENT_ID или HABR_REDIRECT_URI не заданы в env.
    """
    if not settings.HABR_CLIENT_ID or not settings.HABR_REDIRECT_URI:
        raise ValidationError(
            "Хабр Карьера не настроена: задайте HABR_CLIENT_ID и HABR_REDIRECT_URI в .env"
        )

    # Очистка истёкших state этой компании (company-scoped, как hh-идиом)
    await session.execute(
        delete(HabrOauthState).where(
            HabrOauthState.company_id == company_id,
            HabrOauthState.expires_at < datetime.now(timezone.utc),
        )
    )

    state = secrets.token_urlsafe(32)
    oauth_state = HabrOauthState(
        state=state,
        company_id=company_id,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=_STATE_TTL_MINUTES),
    )
    session.add(oauth_state)
    await session.flush()

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": settings.HABR_CLIENT_ID,
        "redirect_uri": settings.HABR_REDIRECT_URI,
        "state": state,
    }
    # scope добавляется ТОЛЬКО если задан (значение неизвестно до одобрения приложения)
    if settings.HABR_SCOPE:
        params["scope"] = settings.HABR_SCOPE

    authorize_url = f"{settings.HABR_AUTHORIZE_URL}?{urlencode(params, quote_via=quote)}"
    return authorize_url


async def handle_callback(
    session: AsyncSession, code: str, state: str
) -> UUID:
    """Обменивает code на токен, сохраняет per-company. Возвращает company_id.

    Потребляет (удаляет) запись HabrOauthState.

    Raises:
        ValidationError: state не найден/истёк, HTTP-ошибка обмена, нет access_token.
    """
    # Найти и проверить state
    result = await session.execute(
        select(HabrOauthState).where(HabrOauthState.state == state)
    )
    oauth_state = result.scalar_one_or_none()

    if oauth_state is None:
        raise ValidationError("Недействительный или истёкший state OAuth")

    if oauth_state.expires_at < datetime.now(timezone.utc):
        await session.delete(oauth_state)
        await session.flush()
        raise ValidationError("Недействительный или истёкший state OAuth")

    company_id = oauth_state.company_id
    connected_by_user_id = oauth_state.user_id

    # Удалить state (он одноразовый)
    await session.delete(oauth_state)
    await session.flush()

    # Обмен code → token
    # ⚠️ HABR_TOKEN_URL — конфигурируемый дефолт, пиннинг после одобрения приложения Хабром
    token_url = settings.HABR_TOKEN_URL
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.HABR_CLIENT_ID,
        "client_secret": settings.HABR_CLIENT_SECRET,
        "redirect_uri": settings.HABR_REDIRECT_URI,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                token_url,
                data=token_data,  # form-encoded (стандарт OAuth2)
            )
    except httpx.HTTPError as exc:
        # client_secret НЕ в логе
        logger.warning("Хабр OAuth token exchange: HTTP error — %s", exc)
        raise ValidationError(f"Ошибка соединения при обмене кода Хабра: {exc}") from exc

    # Проверяем HTTP-статус
    if resp.status_code >= 400:
        logger.warning(
            "Хабр OAuth token exchange: HTTP %d — %.200s",
            resp.status_code,
            resp.text,
        )
        raise ValidationError(
            f"Хабр Карьера вернул ошибку при обмене кода: HTTP {resp.status_code}"
        )

    # Парсим JSON
    try:
        token_json = resp.json()
    except Exception as exc:
        logger.warning("Хабр OAuth token exchange: не-JSON ответ — %s", exc)
        raise ValidationError("Хабр Карьера вернул непarseable ответ при обмене кода") from exc

    access_token = token_json.get("access_token")
    if not access_token:
        logger.warning(
            "Хабр OAuth token exchange: нет access_token в ответе, ключи: %s",
            list(token_json.keys()),
        )
        raise ValidationError("Хабр Карьера не вернул access_token в ответе")

    refresh_token: Optional[str] = token_json.get("refresh_token")
    expires_in: Optional[int] = token_json.get("expires_in")
    expires_at: Optional[datetime] = None
    if expires_in:
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            pass

    # Upsert HabrIntegration (UniqueConstraint company_id)
    result2 = await session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == company_id)
    )
    integration = result2.scalar_one_or_none()

    if integration is None:
        integration = HabrIntegration(company_id=company_id)
        session.add(integration)

    integration.access_token = encrypt_text(access_token)
    integration.refresh_token = encrypt_text(refresh_token) if refresh_token else None
    integration.expires_at = expires_at
    integration.connected_by_user_id = connected_by_user_id
    # habr_login не известен без отдельного API-вызова; оставляем None до одобрения

    await session.flush()
    return company_id


async def disconnect(session: AsyncSession, company_id: UUID) -> None:
    """Обнуляет токены интеграции (запись остаётся)."""
    result = await session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    if integration is not None:
        integration.access_token = None
        integration.refresh_token = None
        integration.expires_at = None
        integration.habr_login = None
        integration.connected_by_user_id = None
        await session.flush()
