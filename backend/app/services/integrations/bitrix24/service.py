"""Битрикс24-интеграция (бизнес-логика).

Конфиг — в generic-таблице `integrations` (provider='bitrix24'), config JSONB.
URL вебхука содержит секретный код → шифруется Fernet и НИКОГДА не возвращается
наружу (в статусе — только домен портала). `status='connected'` — только после
успешной проверки подключения.
"""

import re
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Integration
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....core.errors import ValidationError
from . import client as b24_client

PROVIDER = "bitrix24"

# https://портал.bitrix24.ru/rest/<user_id>/<secret_code>/
WEBHOOK_RE = re.compile(r"^https?://[^/\s]+/rest/\d+/[^/\s]+/?$")


def _portal_from_url(webhook_url: str) -> Optional[str]:
    m = re.match(r"^https?://([^/\s]+)/rest/", webhook_url.strip())
    return m.group(1) if m else None


async def _get_row(session: AsyncSession, company_id: UUID) -> Optional[Integration]:
    result = await session.execute(
        select(Integration).where(
            Integration.provider == PROVIDER,
            Integration.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


def _simplify_user(u: dict) -> dict:
    """B24-пользователь → компактная форма для превью (без чувствительных полей)."""
    active = u.get("ACTIVE")
    # B24 отдаёт ACTIVE как bool или строку 'Y'/'N'
    is_active = active is True or (isinstance(active, str) and active.upper() in ("Y", "TRUE", "1"))
    return {
        "id": str(u.get("ID", "")),
        "name": (u.get("NAME") or "").strip(),
        "last_name": (u.get("LAST_NAME") or "").strip(),
        "position": (u.get("WORK_POSITION") or "").strip() or None,
        "email": (u.get("EMAIL") or "").strip() or None,
        "active": is_active,
    }


async def save_config(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    *,
    webhook_url: str,
) -> Integration:
    """Сохраняет URL входящего вебхука (шифруется). Сбрасывает verified."""
    webhook_url = (webhook_url or "").strip()
    if not WEBHOOK_RE.match(webhook_url):
        raise ValidationError(
            "Неверный формат URL вебхука. Ожидается "
            "https://портал.bitrix24.ru/rest/<id>/<код>/"
        )

    portal = _portal_from_url(webhook_url)
    encrypted_url = encrypt_text(webhook_url)

    new_config = {
        "webhook_url": encrypted_url,  # зашифрован, наружу не отдаётся
        "portal": portal,
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
        "user_count": None,
    }

    row = await _get_row(session, company_id)
    if row:
        row.config = new_config
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
        action="bitrix24_config_saved",
        entity_type="integration",
        entity_id=row.id,
        after={"portal": portal},
        actor_user_id=user_id,
        company_id=company_id,
    )

    return row


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус интеграции. URL вебхука/секрет НЕ возвращаются — только домен портала."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        return {
            "configured": False,
            "verified": False,
            "portal": None,
            "user_count": None,
            "last_test_at": None,
            "last_test_ok": False,
            "last_test_error": None,
        }

    c = row.config
    return {
        "configured": True,
        "verified": row.status == "connected" and bool(c.get("last_test_ok")),
        "portal": c.get("portal"),
        "user_count": c.get("user_count"),
        "last_test_at": c.get("last_test_at"),
        "last_test_ok": bool(c.get("last_test_ok")),
        "last_test_error": c.get("last_test_error"),
    }


async def _decrypted_webhook(row: Integration) -> str:
    return decrypt_text(row.config["webhook_url"])


async def test_connection(
    session: AsyncSession, company_id: UUID, user_id: UUID
) -> dict:
    """Реальная проверка: user.get на портале. Фиксирует результат (коммитит сам)."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен — сначала сохраните URL вебхука")

    webhook = await _decrypted_webhook(row)
    now = datetime.now(timezone.utc)

    try:
        data = await b24_client.get_users_page(webhook, start=0)
    except Exception as e:
        cfg = dict(row.config)
        cfg["last_test_at"] = now.isoformat()
        cfg["last_test_ok"] = False
        cfg["last_test_error"] = getattr(e, "message", None) or str(e)
        row.config = cfg
        row.status = "disconnected"
        await session.flush()
        await audit(
            session,
            action="bitrix24_test_failed",
            entity_type="integration",
            entity_id=row.id,
            after={"error": cfg["last_test_error"]},
            actor_user_id=user_id,
            company_id=company_id,
        )
        await session.commit()
        raise

    total = data.get("total")

    cfg = dict(row.config)
    cfg["last_test_at"] = now.isoformat()
    cfg["last_test_ok"] = True
    cfg["last_test_error"] = None
    cfg["user_count"] = total
    row.config = cfg
    row.status = "connected"
    await session.flush()
    await audit(
        session,
        action="bitrix24_test_ok",
        entity_type="integration",
        entity_id=row.id,
        after={"portal": cfg.get("portal"), "user_count": total},
        actor_user_id=user_id,
        company_id=company_id,
    )
    await session.commit()

    return {"portal": cfg.get("portal"), "user_count": total}


async def preview_users(session: AsyncSession, company_id: UUID, limit: int = 20) -> dict:
    """Реальное чтение первой страницы сотрудников с портала (для превью).

    НЕ импортирует в Глафиру — это следующий этап (нужно решение по модели данных,
    куда складывать сотрудников Б24 и как считать «Текучку»).
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    webhook = await _decrypted_webhook(row)
    data = await b24_client.get_users_page(webhook, start=0)
    raw = data.get("result") or []
    users = [_simplify_user(u) for u in raw[:limit]]
    return {"total": data.get("total"), "users": users}


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID) -> None:
    """Отключает (status=disconnected, verified сбрасывается). Конфиг оставляем."""
    row = await _get_row(session, company_id)
    if not row:
        raise ValidationError("Битрикс24 не настроен")

    row.status = "disconnected"
    cfg = dict(row.config) if row.config else {}
    cfg["last_test_ok"] = False
    row.config = cfg

    await session.flush()
    await audit(
        session,
        action="bitrix24_disconnected",
        entity_type="integration",
        entity_id=row.id,
        actor_user_id=user_id,
        company_id=company_id,
    )
