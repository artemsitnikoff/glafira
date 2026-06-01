"""Telegram-интеграция (бизнес-логика).

Конфиг — generic-таблица integrations (provider='telegram'), config JSONB.
State-машина входа: pending_code → (pending_password) → connected.
Сессия (StringSession = ПОЛНЫЙ доступ к аккаунту) шифруется Fernet и НИКОГДА
не возвращается наружу.
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
from . import client as tg_client

PROVIDER = "telegram"
PHONE_RE = re.compile(r"^\+?\d{7,15}$")


async def _get_row(session: AsyncSession, company_id: UUID) -> Optional[Integration]:
    result = await session.execute(
        select(Integration).where(
            Integration.provider == PROVIDER,
            Integration.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


async def _upsert(session: AsyncSession, company_id: UUID, config: dict, status: str) -> Integration:
    row = await _get_row(session, company_id)
    if row:
        row.config = config
        row.status = status
    else:
        row = Integration(company_id=company_id, provider=PROVIDER, status=status, config=config)
        session.add(row)
    await session.flush()
    return row


async def send_code(session: AsyncSession, company_id: UUID, user_id: UUID, *, phone: str) -> dict:
    """Шаг 1: запросить SMS-код на номер."""
    # Нормализуем: пробелы/скобки/дефисы убираем, ведущий + сохраняем
    # (+7 (999) 123-45-67 → +79991234567).
    raw = (phone or "").strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    phone = ("+" + digits) if has_plus else digits
    if not PHONE_RE.match(phone):
        raise ValidationError("Укажите корректный номер в международном формате (напр. +79991234567)")

    result = await tg_client.send_code(phone)  # {session, phone_code_hash}

    config = {
        "phone": phone,
        "session": encrypt_text(result["session"]),
        "phone_code_hash": result["phone_code_hash"],
        "state": "pending_code",
        "tg_user": None,
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
    }
    row = await _upsert(session, company_id, config, "disconnected")
    await audit(
        session, action="telegram_code_sent", entity_type="integration",
        entity_id=row.id, after={"phone": phone}, actor_user_id=user_id, company_id=company_id,
    )
    return {"state": "pending_code"}


async def confirm_code(session: AsyncSession, company_id: UUID, user_id: UUID, *, code: str) -> dict:
    """Шаг 2: ввод кода. Может вернуть state='pending_password' (если 2FA)."""
    row = await _get_row(session, company_id)
    if not row or not row.config or row.config.get("state") != "pending_code":
        raise ValidationError("Сначала запросите код (введите номер)")

    c = dict(row.config)
    session_str = decrypt_text(c["session"])
    result = await tg_client.sign_in_code(session_str, c["phone"], (code or "").strip(), c["phone_code_hash"])

    if result["status"] == "need_password":
        c["session"] = encrypt_text(result["session"])
        c["state"] = "pending_password"
        row.config = c
        row.status = "disconnected"
        await session.flush()
        await audit(session, action="telegram_need_password", entity_type="integration", entity_id=row.id, actor_user_id=user_id, company_id=company_id)
        return {"state": "pending_password"}

    c["session"] = encrypt_text(result["session"])
    c["state"] = "connected"
    c["tg_user"] = result.get("user")
    c["phone_code_hash"] = None
    row.config = c
    row.status = "connected"
    await session.flush()
    await audit(session, action="telegram_connected", entity_type="integration", entity_id=row.id, after={"tg_user_id": (result.get("user") or {}).get("id")}, actor_user_id=user_id, company_id=company_id)
    return {"state": "connected", "user": result.get("user")}


async def confirm_password(session: AsyncSession, company_id: UUID, user_id: UUID, *, password: str) -> dict:
    """Шаг 2б: облачный пароль 2FA."""
    row = await _get_row(session, company_id)
    if not row or not row.config or row.config.get("state") != "pending_password":
        raise ValidationError("Шаг пароля 2FA недоступен — начните вход заново")

    c = dict(row.config)
    session_str = decrypt_text(c["session"])
    result = await tg_client.sign_in_password(session_str, password or "")

    c["session"] = encrypt_text(result["session"])
    c["state"] = "connected"
    c["tg_user"] = result.get("user")
    c["phone_code_hash"] = None
    row.config = c
    row.status = "connected"
    await session.flush()
    await audit(session, action="telegram_connected", entity_type="integration", entity_id=row.id, after={"tg_user_id": (result.get("user") or {}).get("id")}, actor_user_id=user_id, company_id=company_id)
    return {"state": "connected", "user": result.get("user")}


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус. Сессия/секреты наружу НЕ отдаются."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("state"):
        return {
            "configured": False, "connected": False, "state": None,
            "phone": None, "tg_username": None,
            "last_test_at": None, "last_test_ok": False, "last_test_error": None,
        }
    c = row.config
    tg_user = c.get("tg_user") or {}
    return {
        "configured": True,
        "connected": c.get("state") == "connected",
        "state": c.get("state"),
        "phone": c.get("phone"),
        "tg_username": tg_user.get("username"),
        "last_test_at": c.get("last_test_at"),
        "last_test_ok": bool(c.get("last_test_ok")),
        "last_test_error": c.get("last_test_error"),
    }


async def send_test(session: AsyncSession, company_id: UUID, user_id: UUID) -> dict:
    """Тест: отправить себе сообщение. Коммитит сам (оба пути)."""
    row = await _get_row(session, company_id)
    if not row or not row.config or row.config.get("state") != "connected":
        raise ValidationError("Telegram не подключён")

    c = dict(row.config)
    session_str = decrypt_text(c["session"])
    now = datetime.now(timezone.utc)
    text = "Тест от ATS «Глафира Рекрутёр» — отправка из-под вашего Telegram-аккаунта работает. ✅"

    try:
        await tg_client.send_to_self(session_str, text)
    except Exception as e:
        c["last_test_at"] = now.isoformat()
        c["last_test_ok"] = False
        c["last_test_error"] = getattr(e, "message", None) or str(e)
        row.config = c
        await session.flush()
        await audit(session, action="telegram_test_failed", entity_type="integration", entity_id=row.id, after={"error": c["last_test_error"]}, actor_user_id=user_id, company_id=company_id)
        await session.commit()
        raise

    c["last_test_at"] = now.isoformat()
    c["last_test_ok"] = True
    c["last_test_error"] = None
    row.config = c
    await session.flush()
    await audit(session, action="telegram_test_sent", entity_type="integration", entity_id=row.id, actor_user_id=user_id, company_id=company_id)
    await session.commit()
    return {"sent": True}


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID) -> None:
    """Отключение: полностью забываем сессию (это доступ к аккаунту)."""
    row = await _get_row(session, company_id)
    if not row:
        raise ValidationError("Telegram не настроен")

    phone = (row.config or {}).get("phone")
    row.config = {
        "phone": phone, "session": None, "phone_code_hash": None,
        "state": "disconnected", "tg_user": None,
        "last_test_at": None, "last_test_ok": False, "last_test_error": None,
    }
    row.status = "disconnected"
    await session.flush()
    await audit(session, action="telegram_disconnected", entity_type="integration", entity_id=row.id, actor_user_id=user_id, company_id=company_id)
