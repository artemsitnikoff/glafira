"""Mango Office интеграция (бизнес-логика).

Конфиг — в generic-таблице `integrations` (provider='mango'), config JSONB.
Секреты (vpbx_api_key, vpbx_api_salt) шифруются Fernet и НИКОГДА не возвращаются
наружу (в статусе — только vpbx_api_url). `status='connected'` — только после
успешной проверки подключения.
"""

from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Integration
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....core.errors import ValidationError
from .client import MangoClient

PROVIDER = "mango"
DEFAULT_BASE_URL = "https://app.mango-office.ru/vpbx/"


async def _get_row(session: AsyncSession, company_id: UUID) -> Optional[Integration]:
    result = await session.execute(
        select(Integration).where(
            Integration.provider == PROVIDER,
            Integration.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


async def save_config(
    session: AsyncSession,
    company_id: UUID,
    *,
    api_key: Optional[str] = None,
    api_salt: Optional[str] = None,
    vpbx_api_url: Optional[str] = None,
    actor_user_id: UUID,
) -> Integration:
    """Сохраняет конфигурацию Mango Office. Секреты шифруются."""

    vpbx_api_url = (vpbx_api_url or "").strip()
    if not vpbx_api_url:
        vpbx_api_url = DEFAULT_BASE_URL

    row = await _get_row(session, company_id)
    old_config = dict(row.config) if row and row.config else {}

    # Write-only секреты: пустой ввод при PATCH → сохранить старое значение
    if api_key:
        encrypted_api_key = encrypt_text(api_key)
    else:
        encrypted_api_key = old_config.get("api_key")

    if api_salt:
        encrypted_api_salt = encrypt_text(api_salt)
    else:
        encrypted_api_salt = old_config.get("api_salt")

    if not encrypted_api_key:
        raise ValidationError("Укажите код продукта (vpbx_api_key)")

    if not encrypted_api_salt:
        raise ValidationError("Укажите ключ подписи (vpbx_api_salt)")

    new_config = {
        "api_key": encrypted_api_key,  # зашифрован
        "api_salt": encrypted_api_salt,  # зашифрован
        "vpbx_api_url": vpbx_api_url,  # открыто
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
    }

    if row:
        row.config = new_config  # переприсвоить целиком для отслеживания JSONB изменений
        row.status = "disconnected"
    else:
        row = Integration(
            company_id=company_id,
            provider=PROVIDER,
            status="disconnected",
            config=new_config,
        )
        session.add(row)

    await session.flush()

    await audit(
        session,
        action="mango_config_saved",
        entity_type="integration",
        entity_id=row.id,
        after={"vpbx_api_url": vpbx_api_url},  # ТОЛЬКО несекрет
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return row


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус интеграции Mango. Секреты НЕ возвращаются."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("api_key"):
        return {
            "configured": False,
            "verified": False,
            "vpbx_api_url": None,
            "last_test_at": None,
            "last_test_ok": False,
            "last_test_error": None,
        }

    c = row.config
    return {
        "configured": True,
        "verified": row.status == "connected" and bool(c.get("last_test_ok")),
        "vpbx_api_url": c.get("vpbx_api_url"),
        "last_test_at": c.get("last_test_at"),
        "last_test_ok": bool(c.get("last_test_ok")),
        "last_test_error": c.get("last_test_error"),
    }


async def test_connection(
    session: AsyncSession,
    company_id: UUID,
    *,
    actor_user_id: UUID
) -> dict:
    """Реальная проверка подключения к Mango Office через stats/request.

    Фиксирует результат (коммитит сам на ОБОИХ путях).
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("api_key"):
        raise ValidationError("Mango Office не настроен — сначала сохраните конфигурацию")

    c = row.config
    api_key = decrypt_text(c["api_key"])
    api_salt = decrypt_text(c["api_salt"])
    vpbx_api_url = c.get("vpbx_api_url", DEFAULT_BASE_URL)

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    client = MangoClient(api_key, api_salt, vpbx_api_url)

    try:
        try:
            await client.check_auth()
        finally:
            await client.close()
    except Exception as e:
        # Сбой — фиксируем ошибку и пробрасываем
        cfg = dict(row.config)
        cfg["last_test_at"] = now_naive.isoformat()
        cfg["last_test_ok"] = False
        cfg["last_test_error"] = getattr(e, "message", None) or str(e)
        if len(cfg["last_test_error"]) > 500:
            cfg["last_test_error"] = cfg["last_test_error"][:500]
        row.config = cfg
        row.status = "disconnected"
        await session.flush()
        await audit(
            session,
            action="mango_test_failed",
            entity_type="integration",
            entity_id=row.id,
            after={"error": cfg["last_test_error"]},
            actor_user_id=actor_user_id,
            company_id=company_id,
        )
        await session.commit()
        raise

    # Успех — фиксируем
    cfg = dict(row.config)
    cfg["last_test_at"] = now_naive.isoformat()
    cfg["last_test_ok"] = True
    cfg["last_test_error"] = None
    row.config = cfg
    row.status = "connected"
    await session.flush()
    await audit(
        session,
        action="mango_test_ok",
        entity_type="integration",
        entity_id=row.id,
        after={"vpbx_api_url": vpbx_api_url},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )
    await session.commit()

    return {"vpbx_api_url": vpbx_api_url, "last_test_at": cfg["last_test_at"]}


async def disconnect(
    session: AsyncSession,
    company_id: UUID,
    *,
    actor_user_id: UUID,
) -> None:
    """Отключает Mango Office: status='disconnected', verified сбрасывается.

    Конфиг оставляем (для повторного подключения).
    """
    row = await _get_row(session, company_id)
    if not row:
        raise ValidationError("Mango Office не настроен")

    row.status = "disconnected"
    cfg = dict(row.config) if row.config else {}
    cfg["last_test_ok"] = False
    row.config = cfg

    await session.flush()
    await audit(
        session,
        action="mango_disconnected",
        entity_type="integration",
        entity_id=row.id,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )