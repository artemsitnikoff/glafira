"""SMTP-интеграция (бизнес-логика).

Конфиг хранится в generic-таблице `integrations` (provider='smtp'), config — JSONB.
Пароль шифруется Fernet (как client_secret у hh) и НИКОГДА не возвращается наружу.
`status='connected'` выставляется только после УСПЕШНОЙ тест-отправки.

`send_email()` — переиспользуемое ядро (для будущих оповещений по событиям).
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
from .sender import send_via_smtp

PROVIDER = "smtp"
ENCRYPTION_MODES = ("tls", "ssl", "none")


def _is_valid_email(value: str) -> bool:
    """Лёгкая проверка email (полную валидацию даёт схема/email-validator)."""
    if not value or "@" not in value:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain


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
    user_id: UUID,
    *,
    host: str,
    port: int,
    encryption: str,
    username: str,
    password: str,
    from_email: str,
    from_name: str,
    reply_to: str,
) -> Integration:
    """Сохраняет/обновляет SMTP-конфиг компании.

    Пароль write-only: пустой ввод при существующей конфигурации → старый пароль
    сохраняется (в GET он маскируется, целиком наружу не отдаётся).
    Любое изменение конфига сбрасывает verified (надо проверить тестом заново).
    """
    host = (host or "").strip()
    if not host:
        raise ValidationError("Укажите SMTP-сервер (host)")
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        raise ValidationError("Порт должен быть числом от 1 до 65535")
    if encryption not in ENCRYPTION_MODES:
        raise ValidationError("Шифрование должно быть одним из: tls, ssl, none")

    from_email = (from_email or "").strip()
    if not _is_valid_email(from_email):
        raise ValidationError("Укажите корректный email отправителя")

    reply_to = (reply_to or "").strip()
    if reply_to and not _is_valid_email(reply_to):
        raise ValidationError("Reply-To должен быть корректным email")

    username = (username or "").strip()
    from_name = (from_name or "").strip()

    row = await _get_row(session, company_id)
    old_config = dict(row.config) if row and row.config else {}

    # Мердж пароля
    if password:
        encrypted_password = encrypt_text(password)
    else:
        encrypted_password = old_config.get("password")
    if not encrypted_password:
        raise ValidationError("Укажите пароль SMTP")

    new_config = {
        "host": host,
        "port": port,
        "encryption": encryption,
        "username": username,
        "password": encrypted_password,  # уже зашифрован
        "from_email": from_email,
        "from_name": from_name,
        "reply_to": reply_to,
        # тест-метаданные сбрасываются при смене конфигурации
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
    }

    if row:
        row.config = new_config  # переприсваивание — иначе JSONB-изменение не отследится
        row.status = "disconnected"  # до успешного теста
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
        action="smtp_config_saved",
        entity_type="integration",
        entity_id=row.id,
        after={
            "host": host,
            "port": port,
            "encryption": encryption,
            "from_email": from_email,
        },
        actor_user_id=user_id,
        company_id=company_id,
    )

    return row


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус SMTP-интеграции. Пароль НИКОГДА не отдаётся."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("host"):
        return {
            "configured": False,
            "verified": False,
            "host": None,
            "port": None,
            "encryption": None,
            "username": None,
            "from_email": None,
            "from_name": None,
            "reply_to": None,
            "last_test_at": None,
            "last_test_ok": False,
            "last_test_error": None,
        }

    c = row.config
    return {
        "configured": True,
        "verified": row.status == "connected" and bool(c.get("last_test_ok")),
        "host": c.get("host"),
        "port": c.get("port"),
        "encryption": c.get("encryption"),
        "username": c.get("username") or None,
        "from_email": c.get("from_email"),
        "from_name": c.get("from_name") or None,
        "reply_to": c.get("reply_to") or None,
        "last_test_at": c.get("last_test_at"),
        "last_test_ok": bool(c.get("last_test_ok")),
        "last_test_error": c.get("last_test_error"),
    }


async def send_email(
    session: AsyncSession,
    company_id: UUID,
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    """Переиспользуемое ядро отправки письма через настроенный SMTP компании.

    Используется тест-отправкой и (в будущем) оповещениями по событиям.
    Бросает ValidationError, если SMTP не настроен; AppError при сбое отправки.
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("host"):
        raise ValidationError("SMTP не настроен — сохраните настройки почтового сервера")

    c = row.config
    password = decrypt_text(c["password"]) if c.get("password") else ""

    await send_via_smtp(
        host=c["host"],
        port=int(c["port"]),
        encryption=c.get("encryption", "tls"),
        username=c.get("username") or "",
        password=password,
        from_email=c["from_email"],
        from_name=c.get("from_name") or "",
        reply_to=c.get("reply_to") or "",
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )


async def send_credentials_email(
    session: AsyncSession,
    company_id: UUID,
    *,
    to: str,
    full_name: str,
    temp_password: str,
) -> None:
    """Письмо новому пользователю с логином и временным паролем.

    Общий канал для ручного создания юзера и импорта из Битрикс24.
    Бросает ValidationError, если SMTP не настроен; AppError при сбое отправки.
    """
    subject = "Добро пожаловать в Глафира Рекрутёр"
    body_text = (
        f"Здравствуйте, {full_name}!\n\n"
        "Для вас создан аккаунт в системе Глафира Рекрутёр.\n\n"
        "Данные для входа:\n"
        f"Логин: {to}\n"
        f"Пароль: {temp_password}\n\n"
        "Рекомендуем сменить пароль после первого входа в систему.\n\n"
        "С уважением,\nКоманда Глафира Рекрутёр"
    )
    await send_email(session, company_id, to=to, subject=subject, body_text=body_text)


async def send_test_email(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    *,
    to: str,
) -> dict:
    """Отправляет тестовое письмо и фиксирует результат в last_test_*.

    Коммитит сам (на обоих путях), чтобы метаданные теста — в т.ч. ошибка —
    сохранились даже при сбое отправки (эндпоинт на ошибке не коммитит).
    """
    to = (to or "").strip()
    if not _is_valid_email(to):
        raise ValidationError("Укажите корректный email получателя теста")

    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("host"):
        raise ValidationError("SMTP не настроен — сначала сохраните настройки")

    subject = "Глафира · тестовое письмо"
    body_text = (
        "Это тестовое письмо от ATS «Глафира Рекрутёр».\n\n"
        "Если вы его получили — настройки SMTP корректны, и Глафира сможет "
        "отправлять уведомления через ваш почтовый сервер."
    )
    body_html = (
        "<p>Это тестовое письмо от ATS <b>«Глафира Рекрутёр»</b>.</p>"
        "<p>Если вы его получили — настройки SMTP корректны, и Глафира сможет "
        "отправлять уведомления через ваш почтовый сервер.</p>"
    )

    now = datetime.now(timezone.utc)

    try:
        await send_email(
            session,
            company_id,
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
    except Exception as e:
        # Фиксируем неуспех (с честной причиной) и пробрасываем
        cfg = dict(row.config)
        cfg["last_test_at"] = now.isoformat()
        cfg["last_test_ok"] = False
        cfg["last_test_error"] = getattr(e, "message", None) or str(e)
        row.config = cfg
        row.status = "disconnected"
        await session.flush()
        await audit(
            session,
            action="smtp_test_failed",
            entity_type="integration",
            entity_id=row.id,
            after={"to": to, "error": cfg["last_test_error"]},
            actor_user_id=user_id,
            company_id=company_id,
        )
        await session.commit()
        raise

    # Успех
    cfg = dict(row.config)
    cfg["last_test_at"] = now.isoformat()
    cfg["last_test_ok"] = True
    cfg["last_test_error"] = None
    row.config = cfg
    row.status = "connected"
    await session.flush()
    await audit(
        session,
        action="smtp_test_sent",
        entity_type="integration",
        entity_id=row.id,
        after={"to": to},
        actor_user_id=user_id,
        company_id=company_id,
    )
    await session.commit()

    return {"sent_to": to, "last_test_at": cfg["last_test_at"]}


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID) -> None:
    """Отключает SMTP: status='disconnected', verified сбрасывается. Конфиг оставляем."""
    row = await _get_row(session, company_id)
    if not row:
        raise ValidationError("SMTP не настроен")

    row.status = "disconnected"
    cfg = dict(row.config) if row.config else {}
    cfg["last_test_ok"] = False
    row.config = cfg

    await session.flush()
    await audit(
        session,
        action="smtp_disconnected",
        entity_type="integration",
        entity_id=row.id,
        actor_user_id=user_id,
        company_id=company_id,
    )
