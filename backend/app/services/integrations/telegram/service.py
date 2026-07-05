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

from sqlalchemy import cast, select, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Integration, Candidate, Message
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....services.chat_log import log_chat
from ....core.errors import ValidationError
from . import client as tg_client
from .client import _normalize_phone

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
    digits = re.sub(r"\D", "", raw)
    # Telegram-номер всегда международный → гарантируем E.164 с ведущим '+'
    # (фронт теперь шлёт цифры без '+', хранение тоже без '+').
    phone = ("+" + digits) if digits else ""
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


async def _store_inbound_message(session, company_id, candidate, *, peer_id, msg_id, text, date) -> int:
    """Сохранить одно входящее (dedup по external_id+company_id). Возвращает 1/0."""
    ext_id = f"tg:{peer_id}:{msg_id}"
    existing = await session.execute(
        select(Message.id).where(
            Message.external_id == ext_id,
            Message.company_id == company_id,
        )
    )
    if existing.scalar_one_or_none():
        return 0
    session.add(Message(
        company_id=company_id,
        candidate_id=candidate.id,
        application_id=None,
        channel="telegram",
        direction="in",
        sender_type="candidate",
        sender_user_id=None,
        body=text,
        sent_at=date,
        created_at=datetime.now(timezone.utc),
        external_id=ext_id,
    ))
    log_chat(f"telegram ← входящее: {text[:80]}")
    return 1


async def _sync_one_candidate(session, company_id, candidate_id, session_str) -> dict:
    """Синк входящих по ОДНОМУ кандидату через прямой резолв диалога (как при отправке).

    Работает и без сохранённого tg_user_id (резолвит по username/телефону), бэкфиллит
    tg_user_id — после чего company-wide cron начинает матчить его по uid.
    """
    cand = (await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if cand is None:
        return {"imported": 0, "connected": True}

    username = extract_telegram_username(cand.messengers or [])
    phone = cand.phone
    if not username and not phone:
        return {"imported": 0, "connected": True}  # нечем резолвить

    try:
        res = await tg_client.fetch_candidate_inbound(
            session_str, username=username, phone=phone,
            contact_first=cand.first_name, contact_last=cand.last_name,
            # Кому уже писали — резолвим по кэш peer-id, минуя ImportContacts (лимит).
            tg_user_id=(cand.extra or {}).get("tg_user_id"),
        )
    except Exception as e:
        logger.warning("[tg_sync] fetch_candidate_inbound не удался (cand=%s): %s", candidate_id, e)
        return {"imported": 0, "connected": True}

    peer_id = res.get("peer_id")
    if not peer_id:
        return {"imported": 0, "connected": True}

    # Бэкфилл tg_user_id (для company-wide cron и блока «Последние сообщения»)
    if str((cand.extra or {}).get("tg_user_id") or "") != str(peer_id):
        cand.extra = {**(cand.extra or {}), "tg_user_id": str(peer_id)}

    imported = 0
    for m in res.get("messages", []):
        imported += await _store_inbound_message(
            session, company_id, cand,
            peer_id=peer_id, msg_id=m["msg_id"], text=m["text"], date=m["date"],
        )
    await session.flush()
    return {"imported": imported, "connected": True}


async def sync_inbound(
    session: AsyncSession,
    company_id: UUID,
    *,
    candidate_id: UUID | None = None,
) -> dict:
    """Импортировать входящие Telegram-сообщения от кандидатов компании.

    Не кидает исключений при отключённой интеграции — возвращает {"imported":0,"connected":False}.
    Вызывающий обязан сделать session.commit() после успешного возврата.

    Args:
        session:      AsyncSession (не коммитит сам).
        company_id:   UUID компании (scoping — никаких чужих данных).
        candidate_id: ограничить поиск одним кандидатом (опционально).

    Returns:
        {"imported": int, "connected": bool}
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or row.config.get("state") != "connected":
        return {"imported": 0, "connected": False}

    session_str = decrypt_text(row.config["session"])

    # Синк ОДНОГО кандидата (открытие чата) — ПРЯМОЙ резолв диалога (как при отправке),
    # не зависит от сохранённого tg_user_id и окна топ-N диалогов. Бэкфиллит tg_user_id.
    if candidate_id is not None:
        return await _sync_one_candidate(session, company_id, candidate_id, session_str)

    # --- Company-wide синк (cron): обход диалогов аккаунта ---
    # --- Строим lookup-таблицы (company-scoped) ---
    filters = [
        Candidate.company_id == company_id,
        Candidate.deleted_at.is_(None),
        or_(
            Candidate.extra["tg_user_id"].astext.isnot(None),
            Candidate.phone.isnot(None),
            Candidate.messengers != cast("[]", JSONB),
        ),
    ]
    if candidate_id is not None:
        filters.append(Candidate.id == candidate_id)

    result = await session.execute(select(Candidate).where(*filters))
    candidates = result.scalars().all()

    by_uid: dict[str, Candidate] = {}
    by_username: dict[str, Candidate] = {}
    by_phone: dict[str, Candidate] = {}

    for cand in candidates:
        extra = cand.extra or {}
        uid = extra.get("tg_user_id")
        if uid and uid not in by_uid:
            by_uid[uid] = cand

        uname = extract_telegram_username(cand.messengers or [])
        if uname:
            uname_lower = uname.lower()
            if uname_lower not in by_username:
                by_username[uname_lower] = cand

        phone = cand.phone
        if phone:
            # Только цифры (без ведущего '+'): Telethon отдаёт entity.phone цифрами
            # без '+', поэтому ключи матчинга должны быть в том же виде.
            ph_norm = _normalize_phone(phone).lstrip("+")
            if ph_norm and ph_norm not in by_phone:
                by_phone[ph_norm] = cand

    if not by_uid and not by_username and not by_phone:
        # Нет кандидатов с какими-либо Telegram-реквизитами — нечего сканировать
        return {"imported": 0, "connected": True}

    # --- Запрашиваем входящие через Telethon ---
    try:
        inbound = await tg_client.fetch_inbound(
            session_str,
            peer_ids=set(by_uid.keys()),
            usernames=set(by_username.keys()),
            phones=set(by_phone.keys()),
        )
    except Exception as e:
        logger.warning("[tg_sync] fetch_inbound не удался (company=%s): %s", company_id, e)
        return {"imported": 0, "connected": True}

    # --- Дедуп и сохранение ---
    imported = 0
    now = datetime.now(timezone.utc)

    for msg_dict in inbound:
        peer_id: str = msg_dict["peer_id"]
        username_val: str | None = msg_dict.get("username")
        phone_val: str | None = msg_dict.get("phone")
        msg_id: str = msg_dict["msg_id"]
        text: str = msg_dict["text"]
        date = msg_dict["date"]  # tz-aware datetime

        # Матчинг кандидата: приоритет uid > username > phone
        cand = by_uid.get(peer_id)
        if cand is None and username_val:
            cand = by_username.get(username_val.lower())
        if cand is None and phone_val:
            cand = by_phone.get(phone_val)
        if cand is None:
            continue

        # external_id: "tg:{peer_id}:{msg_id}" — уникален в рамках аккаунта
        ext_id = f"tg:{peer_id}:{msg_id}"  # max len ≈ 3+1+20+1+20 = 45 < String(64)

        # Дедуп: проверяем наличие по external_id + company_id
        existing = await session.execute(
            select(Message.id).where(
                Message.external_id == ext_id,
                Message.company_id == company_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        message = Message(
            company_id=company_id,
            candidate_id=cand.id,
            application_id=None,
            channel="telegram",
            direction="in",
            sender_type="candidate",
            sender_user_id=None,
            body=text,
            sent_at=date,
            created_at=now,
            external_id=ext_id,
        )
        session.add(message)
        imported += 1
        log_chat(f"telegram ← входящее: {text[:80]}")

    await session.flush()
    return {"imported": imported, "connected": True}


async def send_to_candidate(
    session: AsyncSession,
    company_id: UUID,
    *,
    username: str | None,
    phone: str | None,
    text: str,
    tg_user_id: str | int | None = None,
    contact_first: str | None = None,
    contact_last: str | None = None,
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
    return await tg_client.send_to_peer(
        session_str, username=username, phone=phone, text=text, tg_user_id=tg_user_id,
        contact_first=contact_first, contact_last=contact_last,
    )
