"""Telegram-интеграция (бизнес-логика).

Конфиг — generic-таблица integrations (provider='telegram'), config JSONB.
State-машина входа: pending_code → (pending_password) → connected.
Сессия (StringSession = ПОЛНЫЙ доступ к аккаунту) шифруется Fernet и НИКОГДА
не возвращается наружу.
"""

import base64
import io
import logging
import re
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

import qrcode
import qrcode.image.svg

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Integration
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....core.errors import ValidationError
from . import client as tg_client

logger = logging.getLogger(__name__)

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
        "code_type": result.get("code_type"),
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
    return {"state": "pending_code", "code_type": result.get("code_type")}


async def connect_session(session: AsyncSession, company_id: UUID, user_id: UUID, *, session_string: str) -> dict:
    """Подключить Telegram ГОТОВОЙ строкой сессии (минуя номер/код).

    Сессия проверяется на авторизацию, шифруется Fernet и сохраняется. Наружу/в логи
    сама строка не попадает.
    """
    session_string = (session_string or "").strip()
    if not session_string:
        raise ValidationError("Вставьте строку сессии (StringSession)")

    result = await tg_client.connect_with_session(session_string)
    user = result.get("user") or {}
    config = {
        "phone": user.get("phone"),
        "session": encrypt_text(result["session"]),
        "phone_code_hash": None,
        "code_type": None,
        "state": "connected",
        "tg_user": user,
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
    }
    row = await _upsert(session, company_id, config, "connected")
    await audit(
        session, action="telegram_connected", entity_type="integration",
        entity_id=row.id, after={"tg_user_id": user.get("id"), "via": "session"},
        actor_user_id=user_id, company_id=company_id,
    )
    return {"state": "connected", "user": user}


async def resend_code(session: AsyncSession, company_id: UUID, user_id: UUID) -> dict:
    """Повторно запросить код (next_type, обычно App → SMS)."""
    row = await _get_row(session, company_id)
    if not row or not row.config or row.config.get("state") != "pending_code":
        raise ValidationError("Сначала запросите код (введите номер)")

    c = dict(row.config)
    session_str = decrypt_text(c["session"])
    result = await tg_client.resend_code(session_str, c["phone"], c["phone_code_hash"])

    c["session"] = encrypt_text(result["session"])
    c["phone_code_hash"] = result["phone_code_hash"]
    c["code_type"] = result.get("code_type")
    row.config = c
    await session.flush()
    await audit(
        session, action="telegram_code_resent", entity_type="integration",
        entity_id=row.id, after={"phone": c["phone"]}, actor_user_id=user_id, company_id=company_id,
    )
    return {"state": "pending_code", "code_type": result.get("code_type")}


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


def _qr_url_to_svg_data_uri(qr_url: str) -> str:
    """Рендерит tg:// QR-ссылку в SVG и возвращает data-URI (data:image/svg+xml;base64,...)."""
    img = qrcode.make(qr_url, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    svg_bytes = buf.getvalue()
    return "data:image/svg+xml;base64," + base64.b64encode(svg_bytes).decode()


async def qr_start(session: AsyncSession, company_id: UUID, user_id: UUID) -> dict:
    """Начать QR-вход: ExportLoginToken → сохранить qr_session/qr_token/qr_expires в конфиге.

    Возвращает {qr_image: data-uri SVG, expires: int epoch}.
    Сессия хранится только зашифрованной; qr_url в ответ НЕ идёт (только изображение).
    """
    export = await tg_client.qr_export()
    config = {
        "qr_session": encrypt_text(export["session"]),
        "qr_token": export["token"],
        "qr_expires": export["expires"],
        "state": "qr_pending",
        # сбрасываем остатки предыдущего подключения
        "phone": None,
        "session": None,
        "phone_code_hash": None,
        "code_type": None,
        "tg_user": None,
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
    }
    row = await _upsert(session, company_id, config, "disconnected")
    await audit(
        session, action="telegram_qr_started", entity_type="integration",
        entity_id=row.id, actor_user_id=user_id, company_id=company_id,
    )
    qr_image = _qr_url_to_svg_data_uri(export["qr_url"])
    return {"qr_image": qr_image, "expires": export["expires"]}


async def qr_status(session: AsyncSession, company_id: UUID, user_id: UUID) -> dict:
    """Поллинг QR-состояния: ImportLoginToken → обновить конфиг, вернуть состояние.

    Возможные state в ответе:
      'idle'           — QR-сессия не начата (нет qr_session)
      'waiting'        — QR не отсканирован (или текущий QR протух — тогда + qr_image/expires)
      'connected'      — авторизован; {user}
      'need_password'  — нужен пароль 2FA (далее — существующий confirm_password)
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("qr_session"):
        return {"state": "idle"}

    c = dict(row.config)
    session_str = decrypt_text(c["qr_session"])
    token_b64 = c["qr_token"]

    result = await tg_client.qr_poll(session_str, token_b64)
    status = result["status"]

    if status == "connected":
        # Авторизован — сохраняем реальную сессию так же, как confirm_code/connect_session
        c["session"] = encrypt_text(result["session"])
        c["state"] = "connected"
        c["tg_user"] = result.get("user")
        c["phone"] = (result.get("user") or {}).get("phone")
        c["phone_code_hash"] = None
        # Очищаем qr-поля
        c["qr_session"] = None
        c["qr_token"] = None
        c["qr_expires"] = None
        row.config = c
        row.status = "connected"
        await session.flush()
        await audit(
            session, action="telegram_connected", entity_type="integration",
            entity_id=row.id,
            after={"tg_user_id": (result.get("user") or {}).get("id"), "via": "qr"},
            actor_user_id=user_id, company_id=company_id,
        )
        return {"state": "connected", "user": result.get("user")}

    if status == "password_needed":
        # Частичную сессию кладём туда же, куда confirm_code при need_password —
        # confirm_password читает c["session"] в state="pending_password"
        c["session"] = encrypt_text(result["session"])
        c["state"] = "pending_password"
        c["qr_session"] = None
        c["qr_token"] = None
        c["qr_expires"] = None
        row.config = c
        row.status = "disconnected"
        await session.flush()
        await audit(
            session, action="telegram_need_password", entity_type="integration",
            entity_id=row.id, actor_user_id=user_id, company_id=company_id,
        )
        return {"state": "need_password"}

    if status == "expired":
        # Токен протух — qr_poll уже перевыпустил QR; сохраняем новые данные
        c["qr_session"] = encrypt_text(result["session"])
        c["qr_token"] = result["token"]
        c["qr_expires"] = result["expires"]
        row.config = c
        await session.flush()
        qr_image = _qr_url_to_svg_data_uri(result["qr_url"])
        return {"state": "waiting", "qr_image": qr_image, "expires": result["expires"]}

    # status == "waiting"
    return {"state": "waiting"}


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус. Сессия/секреты наружу НЕ отдаются."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("state"):
        return {
            "configured": False, "connected": False, "state": None,
            "phone": None, "tg_username": None, "code_type": None,
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
        "code_type": c.get("code_type"),
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


def extract_telegram_username(messengers: list) -> str | None:
    """Извлекает Telegram-username из поля messengers кандидата.

    Поддерживает объектный формат: [{type: 'tg'|'telegram', url: 'https://t.me/ivan'}].
    Строки-каналы ['telegram', 'whatsapp'] игнорируются — в них нет хэндла.
    Возвращает username без '@' (напр. 'ivan') или None.
    """
    for item in (messengers or []):
        if not isinstance(item, dict):
            continue
        item_type = (item.get("type") or "").lower()
        if item_type not in ("tg", "telegram"):
            continue
        url = (item.get("url") or "").strip()
        if not url or "t.me/" not in url:
            continue
        # Берём сегмент после последнего t.me/
        path = url.split("t.me/")[-1]
        # Убираем query-параметры и хвостовые слеши
        path = path.split("?")[0].rstrip("/").lstrip("@")
        if path:
            return path
    return None


async def send_to_candidate(
    session: AsyncSession,
    company_id: UUID,
    *,
    username: str | None,
    phone: str | None,
    text: str,
) -> dict:
    """Отправить сообщение кандидату через подключённый Telegram-аккаунт компании.

    Только читает зашифрованную строку сессии из БД — не пишет, не меняет конфиг.
    Audit делает вызывающий (send_message в message.py).
    Кидает ValidationError, если интеграция не подключена.
    Кидает AppError (TG_*) при сбое отправки.
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or row.config.get("state") != "connected":
        raise ValidationError("Telegram не подключён")
    session_str = decrypt_text(row.config["session"])
    logger.info("[tg_service] send_to_candidate: company_id=%s username_set=%s phone_set=%s",
                company_id, bool(username), bool(phone))
    return await tg_client.send_to_peer(session_str, username=username, phone=phone, text=text)
