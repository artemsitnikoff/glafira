"""OAuth-токены Talantix per-company (хранятся в TalantixIntegration, Fernet).

По образцу glafiraeuro/app/services/talantix_token.py, но:
* токены лежат в БД (TalantixIntegration), а не в файле;
* refresh_token ОДНОРАЗОВЫЙ — новый обязательно персистится обратно (commit),
  иначе следующий refresh упадёт «invalid_grant»;
* refresh идёт в СВОЕЙ короткой сессии (AsyncSessionLocal) и коммитится сразу —
  чтобы ротация не потерялась, если импортная задача умрёт между запросами;
* защита от гонки одновременных refresh — per-company asyncio.Lock в процессе.

Refresh: POST /oauth/token, form grant_type=refresh_token&refresh_token=<rt> →
{access_token, refresh_token(НОВЫЙ), expires_in≈86400}. Header запросов —
Authorization: Bearer <access>. access живёт ~24ч.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import select

from ....config import settings
from ....core.errors import ValidationError
from ....database import AsyncSessionLocal
from ....models import TalantixIntegration
from ....services.settings.crypto import encrypt_text, decrypt_text

logger = logging.getLogger(__name__)

# Рефрешим заранее — за 10 минут до истечения access_token.
_REFRESH_BUFFER_SEC = 600

# Один лок на компанию: два параллельных _gql не должны рефрешить одновременно
# (иначе двойная ротация refresh_token → второй запрос получит invalid_grant).
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(company_id: UUID) -> asyncio.Lock:
    key = str(company_id)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def save_tokens(
    company_id: UUID,
    *,
    access_token: str,
    refresh_token: str,
    expires_at: datetime | None,
    user_id: UUID | None = None,
) -> None:
    """Upsert зашифрованных токенов Talantix компании (своя короткая сессия + commit)."""
    async with AsyncSessionLocal() as session:
        integration = (
            await session.execute(
                select(TalantixIntegration).where(
                    TalantixIntegration.company_id == company_id
                )
            )
        ).scalar_one_or_none()
        if integration is None:
            integration = TalantixIntegration(company_id=company_id)
            session.add(integration)
        integration.access_token = encrypt_text(access_token) if access_token else None
        integration.refresh_token = encrypt_text(refresh_token) if refresh_token else None
        integration.expires_at = expires_at
        if user_id is not None:
            integration.connected_by_user_id = user_id
        await session.commit()


async def _do_refresh(refresh_token: str) -> dict:
    """POST /oauth/token → новая пара токенов. Кидает ValidationError при сбое."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                settings.TALANTIX_TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": settings.TALANTIX_USER_AGENT,
                },
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ValidationError("Не удалось связаться с Talantix (сеть/таймаут)") from exc

    if resp.status_code in (400, 401):
        raise ValidationError(
            "Talantix отклонил токен — проверьте токен Talantix "
            "(refresh_token просрочен/уже использован; получите новую пару в ЛК)"
        )
    if not resp.is_success:
        raise ValidationError(f"Talantix вернул ошибку при обновлении токена (HTTP {resp.status_code})")

    try:
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("Talantix вернул некорректный ответ при обновлении токена") from exc

    new_access = body.get("access_token")
    new_refresh = body.get("refresh_token")
    if not new_access or not new_refresh:
        raise ValidationError("Talantix не вернул новую пару токенов")
    return body


async def _refresh_and_store(company_id: UUID, integration: TalantixIntegration) -> str:
    """Обновить токены компании и ПЕРСИСТИТЬ новую пару (своя сессия + commit)."""
    if not integration.refresh_token:
        raise ValidationError("Talantix не подключён — сохраните токены в Настройки → Интеграции")

    refresh_token = decrypt_text(integration.refresh_token)
    body = await _do_refresh(refresh_token)

    new_access = body["access_token"]
    new_refresh = body["refresh_token"]
    try:
        expires_in = int(body.get("expires_in", 86400))
    except (TypeError, ValueError):
        expires_in = 86400
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    await save_tokens(
        company_id,
        access_token=new_access,
        refresh_token=new_refresh,
        expires_at=expires_at,
    )
    logger.info("[talantix] токен обновлён company=%s (истекает через %dч)", company_id, expires_in // 3600)
    return new_access


async def _load_integration(company_id: UUID) -> TalantixIntegration:
    async with AsyncSessionLocal() as session:
        integration = (
            await session.execute(
                select(TalantixIntegration).where(
                    TalantixIntegration.company_id == company_id
                )
            )
        ).scalar_one_or_none()
    if integration is None or not integration.refresh_token:
        raise ValidationError("Talantix не подключён — сохраните токены в Настройки → Интеграции")
    return integration


async def get_access_token(company_id: UUID) -> str:
    """Свежий access_token компании. Рефреш если истёк/скоро истечёт."""
    async with _lock_for(company_id):
        integration = await _load_integration(company_id)

        now = datetime.now(timezone.utc)
        if integration.access_token and integration.expires_at:
            expires_at = integration.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now < expires_at - timedelta(seconds=_REFRESH_BUFFER_SEC):
                return decrypt_text(integration.access_token)

        # Истёк/нет — рефрешим (ротирует refresh_token, персистит новую пару).
        return await _refresh_and_store(company_id, integration)


async def force_refresh_on_401(company_id: UUID) -> str:
    """Принудительный рефреш при 401 от GraphQL (локально токен «живой», но сервер забраковал)."""
    async with _lock_for(company_id):
        integration = await _load_integration(company_id)
        return await _refresh_and_store(company_id, integration)


async def connect_and_store(
    company_id: UUID,
    *,
    refresh_token: str,
    user_id: UUID | None = None,
) -> datetime:
    """Подключение: валидировать пару из ЛК через реальный refresh и сохранить СВЕЖУЮ пару.

    Валидация = успешный обмен refresh_token → новая пара (доказывает, что токен рабочий).
    Ротированную пару персистим (пастнутый refresh становится недействителен — так и надо,
    одноразовый). Возвращает момент истечения нового access_token.

    Raises:
        ValidationError: refresh_token невалиден/просрочен/сеть.
    """
    if not refresh_token or not refresh_token.strip():
        raise ValidationError("Укажите refresh_token Talantix (из json в ЛК)")

    body = await _do_refresh(refresh_token.strip())
    new_access = body["access_token"]
    new_refresh = body["refresh_token"]
    try:
        expires_in = int(body.get("expires_in", 86400))
    except (TypeError, ValueError):
        expires_in = 86400
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    await save_tokens(
        company_id,
        access_token=new_access,
        refresh_token=new_refresh,
        expires_at=expires_at,
        user_id=user_id,
    )
    return expires_at
