"""Тесты Telegram-интеграции (state-машина входа).

Telethon-клиент (tg_client.*) ЗАМОКАН — без сети. Проверяем логику сервиса:
переходы pending_code → (pending_password) → connected, шифрование/неутечку сессии,
тест-отправку. (Сами Telethon-вызовы проверяются только на живом аккаунте.)

VPS-only: импорт сервиса тянет telethon (на проде установлен через requirements).
"""

import pytest
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet

from app.services.integrations.telegram import service as tg
from app.services.settings.crypto import decrypt_text
from app.core.errors import ValidationError, AppError
from app.models import Integration
from sqlalchemy import select

SEND_CODE = "app.services.integrations.telegram.service.tg_client.send_code"
SIGN_CODE = "app.services.integrations.telegram.service.tg_client.sign_in_code"
SIGN_PWD = "app.services.integrations.telegram.service.tg_client.sign_in_password"
SEND_SELF = "app.services.integrations.telegram.service.tg_client.send_to_self"
QR_EXPORT = "app.services.integrations.telegram.service.tg_client.qr_export"
QR_POLL = "app.services.integrations.telegram.service.tg_client.qr_poll"


@pytest.fixture
def fernet_key(monkeypatch):
    monkeypatch.setattr("app.config.settings.FERNET_KEY", Fernet.generate_key().decode())


async def _row(db_session, company_id):
    return (await db_session.execute(
        select(Integration).where(Integration.provider == "telegram", Integration.company_id == company_id)
    )).scalar_one_or_none()


# --------------------------- send_code ---------------------------

async def test_send_code_stores_pending(db_session, admin_user, fernet_key):
    with patch(SEND_CODE, new=AsyncMock(return_value={"session": "sess-1", "phone_code_hash": "hash-1"})):
        res = await tg.send_code(db_session, admin_user.company_id, admin_user.id, phone="+79991234567")
    assert res["state"] == "pending_code"
    row = await _row(db_session, admin_user.company_id)
    assert row.config["state"] == "pending_code"
    assert row.config["phone"] == "+79991234567"
    # сессия зашифрована
    assert row.config["session"] != "sess-1"
    assert decrypt_text(row.config["session"]) == "sess-1"


async def test_send_code_bad_phone(db_session, admin_user, fernet_key):
    with patch(SEND_CODE, new=AsyncMock()) as m:
        with pytest.raises(ValidationError):
            await tg.send_code(db_session, admin_user.company_id, admin_user.id, phone="не номер")
    m.assert_not_awaited()


# --------------------------- confirm_code ---------------------------

async def test_confirm_code_connected(db_session, admin_user, fernet_key):
    with patch(SEND_CODE, new=AsyncMock(return_value={"session": "s", "phone_code_hash": "h"})):
        await tg.send_code(db_session, admin_user.company_id, admin_user.id, phone="+79991234567")
    signed = {"status": "connected", "session": "auth-sess", "user": {"id": "111", "username": "ivan"}}
    with patch(SIGN_CODE, new=AsyncMock(return_value=signed)):
        res = await tg.confirm_code(db_session, admin_user.company_id, admin_user.id, code="12345")
    assert res["state"] == "connected"
    row = await _row(db_session, admin_user.company_id)
    assert row.status == "connected"
    assert row.config["state"] == "connected"
    assert decrypt_text(row.config["session"]) == "auth-sess"
    assert row.config["tg_user"]["username"] == "ivan"


async def test_confirm_code_need_password(db_session, admin_user, fernet_key):
    with patch(SEND_CODE, new=AsyncMock(return_value={"session": "s", "phone_code_hash": "h"})):
        await tg.send_code(db_session, admin_user.company_id, admin_user.id, phone="+79991234567")
    with patch(SIGN_CODE, new=AsyncMock(return_value={"status": "need_password", "session": "pwd-sess"})):
        res = await tg.confirm_code(db_session, admin_user.company_id, admin_user.id, code="12345")
    assert res["state"] == "pending_password"
    row = await _row(db_session, admin_user.company_id)
    assert row.config["state"] == "pending_password"
    assert decrypt_text(row.config["session"]) == "pwd-sess"


async def test_confirm_code_wrong_state(db_session, admin_user, fernet_key):
    # без send_code — нет pending_code
    with pytest.raises(ValidationError):
        await tg.confirm_code(db_session, admin_user.company_id, admin_user.id, code="12345")


# --------------------------- confirm_password (2FA) ---------------------------

async def test_confirm_password_connects(db_session, admin_user, fernet_key):
    with patch(SEND_CODE, new=AsyncMock(return_value={"session": "s", "phone_code_hash": "h"})):
        await tg.send_code(db_session, admin_user.company_id, admin_user.id, phone="+79991234567")
    with patch(SIGN_CODE, new=AsyncMock(return_value={"status": "need_password", "session": "pwd-sess"})):
        await tg.confirm_code(db_session, admin_user.company_id, admin_user.id, code="12345")
    with patch(SIGN_PWD, new=AsyncMock(return_value={"status": "connected", "session": "auth2", "user": {"id": "1", "username": "u"}})):
        res = await tg.confirm_password(db_session, admin_user.company_id, admin_user.id, password="hunter2")
    assert res["state"] == "connected"
    row = await _row(db_session, admin_user.company_id)
    assert row.status == "connected"
    assert decrypt_text(row.config["session"]) == "auth2"


# --------------------------- status / test / disconnect ---------------------------

async def test_status_never_returns_session(db_session, admin_user, fernet_key):
    with patch(SEND_CODE, new=AsyncMock(return_value={"session": "s", "phone_code_hash": "h"})):
        await tg.send_code(db_session, admin_user.company_id, admin_user.id, phone="+79991234567")
    status = await tg.get_status(db_session, admin_user.company_id)
    assert "session" not in status
    assert status["configured"] is True
    assert status["connected"] is False
    assert status["state"] == "pending_code"
    assert status["phone"] == "+79991234567"


async def _connect(db_session, admin_user):
    with patch(SEND_CODE, new=AsyncMock(return_value={"session": "s", "phone_code_hash": "h"})):
        await tg.send_code(db_session, admin_user.company_id, admin_user.id, phone="+79991234567")
    with patch(SIGN_CODE, new=AsyncMock(return_value={"status": "connected", "session": "auth", "user": {"id": "1", "username": "u"}})):
        await tg.confirm_code(db_session, admin_user.company_id, admin_user.id, code="12345")


async def test_send_test_success(db_session, admin_user, fernet_key):
    await _connect(db_session, admin_user)
    send = AsyncMock()
    with patch(SEND_SELF, new=send):
        res = await tg.send_test(db_session, admin_user.company_id, admin_user.id)
    assert res["sent"] is True
    send.assert_awaited_once()
    # тест зовётся с расшифрованной сессией
    assert send.await_args.args[0] == "auth"
    status = await tg.get_status(db_session, admin_user.company_id)
    assert status["last_test_ok"] is True


async def test_send_test_failure_records(db_session, admin_user, fernet_key):
    await _connect(db_session, admin_user)
    boom = AsyncMock(side_effect=AppError(code="TG_SEND_ERROR", message="Не удалось отправить", status_code=400))
    with patch(SEND_SELF, new=boom):
        with pytest.raises(AppError):
            await tg.send_test(db_session, admin_user.company_id, admin_user.id)
    status = await tg.get_status(db_session, admin_user.company_id)
    assert status["last_test_ok"] is False
    assert status["last_test_error"] == "Не удалось отправить"


async def test_send_test_not_connected(db_session, admin_user, fernet_key):
    with pytest.raises(ValidationError):
        await tg.send_test(db_session, admin_user.company_id, admin_user.id)


async def test_disconnect_clears_session(db_session, admin_user, fernet_key):
    await _connect(db_session, admin_user)
    await tg.disconnect(db_session, admin_user.company_id, admin_user.id)
    row = await _row(db_session, admin_user.company_id)
    assert row.status == "disconnected"
    assert row.config["session"] is None
    assert row.config["state"] == "disconnected"


# ---------------------------------------------------------------------------
# QR-вход
# ---------------------------------------------------------------------------

_QR_EXPORT_RESULT = {
    "qr_url": "tg://login?token=AAABBBCCC",
    "token": "AAABBBCCC",
    "session": "qr-sess-1",
    "expires": 9999999999,
}


async def test_qr_start_saves_config(db_session, admin_user, fernet_key):
    """qr_start: сохраняет зашифрованный qr_session и возвращает qr_image + expires."""
    with patch(QR_EXPORT, new=AsyncMock(return_value=_QR_EXPORT_RESULT)):
        res = await tg.qr_start(db_session, admin_user.company_id, admin_user.id)

    # qr_image должен быть data-URI SVG
    assert res["qr_image"].startswith("data:image/svg+xml;base64,")
    assert res["expires"] == 9999999999

    row = await _row(db_session, admin_user.company_id)
    assert row.config["state"] == "qr_pending"
    assert row.status == "disconnected"
    # qr_session зашифрован (не равен исходному)
    assert row.config["qr_session"] != "qr-sess-1"
    assert decrypt_text(row.config["qr_session"]) == "qr-sess-1"
    assert row.config["qr_token"] == "AAABBBCCC"
    # реальная сессия не должна быть задана
    assert row.config["session"] is None


async def test_qr_status_connected(db_session, admin_user, fernet_key):
    """qr_status: poll вернул 'connected' → сохранить сессию, вернуть user."""
    with patch(QR_EXPORT, new=AsyncMock(return_value=_QR_EXPORT_RESULT)):
        await tg.qr_start(db_session, admin_user.company_id, admin_user.id)

    poll_result = {
        "status": "connected",
        "session": "auth-sess-qr",
        "user": {"id": "42", "username": "qruser", "first_name": "QR", "phone": "+79001234567"},
    }
    with patch(QR_POLL, new=AsyncMock(return_value=poll_result)):
        res = await tg.qr_status(db_session, admin_user.company_id, admin_user.id)

    assert res["state"] == "connected"
    assert res["user"]["username"] == "qruser"

    row = await _row(db_session, admin_user.company_id)
    assert row.status == "connected"
    assert row.config["state"] == "connected"
    assert decrypt_text(row.config["session"]) == "auth-sess-qr"
    assert row.config["tg_user"]["username"] == "qruser"
    # qr-поля очищены
    assert row.config["qr_session"] is None
    assert row.config["qr_token"] is None


async def test_qr_status_need_password(db_session, admin_user, fernet_key):
    """qr_status: poll вернул 'password_needed' → перейти в pending_password."""
    with patch(QR_EXPORT, new=AsyncMock(return_value=_QR_EXPORT_RESULT)):
        await tg.qr_start(db_session, admin_user.company_id, admin_user.id)

    poll_result = {"status": "password_needed", "session": "partial-sess"}
    with patch(QR_POLL, new=AsyncMock(return_value=poll_result)):
        res = await tg.qr_status(db_session, admin_user.company_id, admin_user.id)

    assert res["state"] == "need_password"

    row = await _row(db_session, admin_user.company_id)
    assert row.config["state"] == "pending_password"
    assert row.status == "disconnected"
    assert decrypt_text(row.config["session"]) == "partial-sess"
    assert row.config["qr_session"] is None


async def test_qr_status_waiting(db_session, admin_user, fernet_key):
    """qr_status: poll вернул 'waiting' → просто вернуть state='waiting'."""
    with patch(QR_EXPORT, new=AsyncMock(return_value=_QR_EXPORT_RESULT)):
        await tg.qr_start(db_session, admin_user.company_id, admin_user.id)

    with patch(QR_POLL, new=AsyncMock(return_value={"status": "waiting"})):
        res = await tg.qr_status(db_session, admin_user.company_id, admin_user.id)

    assert res["state"] == "waiting"
    # конфиг не должен был измениться
    row = await _row(db_session, admin_user.company_id)
    assert row.config["state"] == "qr_pending"


async def test_qr_status_idle_without_start(db_session, admin_user, fernet_key):
    """qr_status без qr_start → state='idle'."""
    res = await tg.qr_status(db_session, admin_user.company_id, admin_user.id)
    assert res["state"] == "idle"


async def test_qr_status_expired_refreshes_qr(db_session, admin_user, fernet_key):
    """qr_status: poll вернул 'expired' → сохранить новый QR, вернуть qr_image."""
    with patch(QR_EXPORT, new=AsyncMock(return_value=_QR_EXPORT_RESULT)):
        await tg.qr_start(db_session, admin_user.company_id, admin_user.id)

    expired_result = {
        "status": "expired",
        "qr_url": "tg://login?token=NEWTOKEN",
        "token": "NEWTOKEN",
        "session": "qr-sess-2",
        "expires": 9999999998,
    }
    with patch(QR_POLL, new=AsyncMock(return_value=expired_result)):
        res = await tg.qr_status(db_session, admin_user.company_id, admin_user.id)

    assert res["state"] == "waiting"
    assert "qr_image" in res
    assert res["qr_image"].startswith("data:image/svg+xml;base64,")
    assert res["expires"] == 9999999998

    row = await _row(db_session, admin_user.company_id)
    assert row.config["qr_token"] == "NEWTOKEN"
    assert decrypt_text(row.config["qr_session"]) == "qr-sess-2"


async def test_qr_then_confirm_password(db_session, admin_user, fernet_key):
    """Полный QR-2FA-сценарий: qr_start → qr_status(need_password) → confirm_password."""
    with patch(QR_EXPORT, new=AsyncMock(return_value=_QR_EXPORT_RESULT)):
        await tg.qr_start(db_session, admin_user.company_id, admin_user.id)

    with patch(QR_POLL, new=AsyncMock(return_value={"status": "password_needed", "session": "partial"})):
        await tg.qr_status(db_session, admin_user.company_id, admin_user.id)

    # Теперь confirm_password должен работать из state=pending_password
    pwd_result = {"status": "connected", "session": "auth-final", "user": {"id": "7", "username": "qr2fa"}}
    with patch(SIGN_PWD, new=AsyncMock(return_value=pwd_result)):
        res = await tg.confirm_password(db_session, admin_user.company_id, admin_user.id, password="secret")

    assert res["state"] == "connected"
    assert res["user"]["username"] == "qr2fa"
    row = await _row(db_session, admin_user.company_id)
    assert row.status == "connected"
    assert decrypt_text(row.config["session"]) == "auth-final"
