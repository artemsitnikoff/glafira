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
