"""Тесты SMTP-интеграции (конфиг + тест-отправка).

Транспорт (send_via_smtp) ВСЕГДА замокан — тесты не ходят в сеть.
Проверяем реальную логику: шифрование/мердж пароля, отсутствие утечки пароля,
вызов транспорта с правильными аргументами, фиксацию результата теста.
"""

import pytest
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet

from app.services.integrations.smtp import service as smtp_service
from app.services.settings.crypto import decrypt_text
from app.core.errors import AppError, ValidationError
from app.models import Integration

SEND_TARGET = "app.services.integrations.smtp.service.send_via_smtp"


@pytest.fixture
def fernet_key(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.FERNET_KEY", test_key)
    return test_key


async def _save_basic(db_session, user, password="s3cret-pass", host="smtp.yandex.ru"):
    return await smtp_service.save_config(
        db_session,
        user.company_id,
        user.id,
        host=host,
        port=587,
        encryption="tls",
        username="hr@company.ru",
        password=password,
        from_email="hr@company.ru",
        from_name="HR · ООО Логос",
        reply_to="",
    )


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_config_encrypts_password(db_session, admin_user, fernet_key):
    row = await _save_basic(db_session, admin_user)
    assert row.provider == "smtp"
    assert row.status == "disconnected"  # до успешного теста
    # Пароль зашифрован, расшифровывается обратно
    assert row.config["password"] != "s3cret-pass"
    assert decrypt_text(row.config["password"]) == "s3cret-pass"
    # Тест-метаданные сброшены
    assert row.config["last_test_ok"] is False
    assert row.config["last_test_error"] is None


@pytest.mark.asyncio
async def test_save_config_merges_blank_password(db_session, admin_user, fernet_key):
    await _save_basic(db_session, admin_user, password="first-pass")
    # Повторное сохранение без пароля, но со сменой хоста — пароль сохраняется
    row = await _save_basic(db_session, admin_user, password="", host="smtp.gmail.com")
    assert row.config["host"] == "smtp.gmail.com"
    assert decrypt_text(row.config["password"]) == "first-pass"


@pytest.mark.asyncio
async def test_save_config_requires_password_first_time(db_session, admin_user, fernet_key):
    with pytest.raises(ValidationError):
        await _save_basic(db_session, admin_user, password="")


@pytest.mark.asyncio
async def test_save_config_validates_port_encryption_email(db_session, admin_user, fernet_key):
    with pytest.raises(ValidationError):
        await smtp_service.save_config(
            db_session, admin_user.company_id, admin_user.id,
            host="smtp.x.ru", port=70000, encryption="tls",
            username="", password="p", from_email="hr@company.ru",
            from_name="", reply_to="",
        )
    with pytest.raises(ValidationError):
        await smtp_service.save_config(
            db_session, admin_user.company_id, admin_user.id,
            host="smtp.x.ru", port=587, encryption="wat",
            username="", password="p", from_email="hr@company.ru",
            from_name="", reply_to="",
        )
    with pytest.raises(ValidationError):
        await smtp_service.save_config(
            db_session, admin_user.company_id, admin_user.id,
            host="smtp.x.ru", port=587, encryption="tls",
            username="", password="p", from_email="not-an-email",
            from_name="", reply_to="",
        )


# ---------------------------------------------------------------------------
# get_status — никогда не отдаёт пароль
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_never_returns_password(db_session, admin_user, fernet_key):
    await _save_basic(db_session, admin_user)
    status = await smtp_service.get_status(db_session, admin_user.company_id)
    assert "password" not in status
    assert status["configured"] is True
    assert status["verified"] is False
    assert status["host"] == "smtp.yandex.ru"
    assert status["from_email"] == "hr@company.ru"


@pytest.mark.asyncio
async def test_get_status_unconfigured(db_session, admin_user, fernet_key):
    status = await smtp_service.get_status(db_session, admin_user.company_id)
    assert status["configured"] is False
    assert status["verified"] is False
    assert "password" not in status


# ---------------------------------------------------------------------------
# send_test_email
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_test_email_success(db_session, admin_user, fernet_key):
    await _save_basic(db_session, admin_user, password="real-pass")

    with patch(SEND_TARGET, new=AsyncMock()) as mock_send:
        result = await smtp_service.send_test_email(
            db_session, admin_user.company_id, admin_user.id, to="me@company.ru"
        )

    assert result["sent_to"] == "me@company.ru"
    # Транспорт вызван с расшифрованным паролем и нужным получателем
    mock_send.assert_awaited_once()
    kwargs = mock_send.await_args.kwargs
    assert kwargs["to"] == "me@company.ru"
    assert kwargs["host"] == "smtp.yandex.ru"
    assert kwargs["password"] == "real-pass"  # расшифрован перед отправкой
    assert kwargs["from_email"] == "hr@company.ru"

    # Статус обновился на verified
    status = await smtp_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is True
    assert status["last_test_ok"] is True
    assert status["last_test_error"] is None
    assert status["last_test_at"] is not None


@pytest.mark.asyncio
async def test_send_test_email_failure_records_error(db_session, admin_user, fernet_key):
    await _save_basic(db_session, admin_user)

    boom = AsyncMock(side_effect=AppError(
        code="SMTP_AUTH_ERROR", message="Не удалось авторизоваться", status_code=400
    ))
    with patch(SEND_TARGET, new=boom):
        with pytest.raises(AppError):
            await smtp_service.send_test_email(
                db_session, admin_user.company_id, admin_user.id, to="me@company.ru"
            )

    # Ошибка зафиксирована (send_test_email коммитит на сбое)
    status = await smtp_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is False
    assert status["last_test_ok"] is False
    assert status["last_test_error"] == "Не удалось авторизоваться"


@pytest.mark.asyncio
async def test_send_test_email_invalid_recipient(db_session, admin_user, fernet_key):
    await _save_basic(db_session, admin_user)
    with patch(SEND_TARGET, new=AsyncMock()) as mock_send:
        with pytest.raises(ValidationError):
            await smtp_service.send_test_email(
                db_session, admin_user.company_id, admin_user.id, to="bad-address"
            )
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_test_email_not_configured(db_session, admin_user, fernet_key):
    with patch(SEND_TARGET, new=AsyncMock()) as mock_send:
        with pytest.raises(ValidationError):
            await smtp_service.send_test_email(
                db_session, admin_user.company_id, admin_user.id, to="me@company.ru"
            )
    mock_send.assert_not_awaited()


# ---------------------------------------------------------------------------
# send_email (переиспользуемое ядро) + disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_email_not_configured_raises(db_session, admin_user, fernet_key):
    with pytest.raises(ValidationError):
        await smtp_service.send_email(
            db_session, admin_user.company_id,
            to="x@y.ru", subject="s", body_text="b",
        )


@pytest.mark.asyncio
async def test_send_email_calls_transport_with_decrypted_password(db_session, admin_user, fernet_key):
    await _save_basic(db_session, admin_user, password="pw-123")
    with patch(SEND_TARGET, new=AsyncMock()) as mock_send:
        await smtp_service.send_email(
            db_session, admin_user.company_id,
            to="x@y.ru", subject="Subj", body_text="Body",
        )
    kwargs = mock_send.await_args.kwargs
    assert kwargs["password"] == "pw-123"
    assert kwargs["subject"] == "Subj"
    assert kwargs["body_text"] == "Body"


@pytest.mark.asyncio
async def test_disconnect_resets_verified(db_session, admin_user, fernet_key):
    await _save_basic(db_session, admin_user, password="real-pass")
    with patch(SEND_TARGET, new=AsyncMock()):
        await smtp_service.send_test_email(
            db_session, admin_user.company_id, admin_user.id, to="me@company.ru"
        )
    # verified=True после теста
    assert (await smtp_service.get_status(db_session, admin_user.company_id))["verified"] is True

    await smtp_service.disconnect(db_session, admin_user.company_id, admin_user.id)
    status = await smtp_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is False
    assert status["configured"] is True  # конфиг остался
