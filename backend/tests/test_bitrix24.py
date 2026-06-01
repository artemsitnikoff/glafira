"""Тесты Битрикс24-интеграции (входящий вебхук).

REST-клиент (get_users_page) ВСЕГДА замокан — тесты не ходят в сеть.
Проверяем реальную логику: шифрование URL вебхука, валидацию формата,
отсутствие утечки секрета в статусе, фиксацию результата проверки.
"""

import pytest
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet

from app.services.integrations.bitrix24 import service as b24_service
from app.services.settings.crypto import decrypt_text
from app.core.errors import AppError, ValidationError

CALL_TARGET = "app.services.integrations.bitrix24.service.b24_client.get_users_page"
WEBHOOK = "https://demo.bitrix24.ru/rest/1/abc123secretcode/"


@pytest.fixture
def fernet_key(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.FERNET_KEY", test_key)
    return test_key


async def _save(db_session, user, url=WEBHOOK):
    return await b24_service.save_config(
        db_session, user.company_id, user.id, webhook_url=url
    )


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_config_encrypts_webhook(db_session, admin_user, fernet_key):
    row = await _save(db_session, admin_user)
    assert row.provider == "bitrix24"
    assert row.status == "disconnected"
    assert row.config["webhook_url"] != WEBHOOK  # зашифрован
    assert decrypt_text(row.config["webhook_url"]) == WEBHOOK
    assert row.config["portal"] == "demo.bitrix24.ru"
    assert row.config["last_test_ok"] is False


@pytest.mark.asyncio
async def test_save_config_rejects_bad_url(db_session, admin_user, fernet_key):
    for bad in [
        "",
        "not a url",
        "https://demo.bitrix24.ru/",  # нет /rest/<id>/<code>
        "https://demo.bitrix24.ru/rest/1/",  # нет кода
        "ftp://demo.bitrix24.ru/rest/1/code/",
    ]:
        with pytest.raises(ValidationError):
            await _save(db_session, admin_user, url=bad)


# ---------------------------------------------------------------------------
# get_status — не отдаёт секрет
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_never_returns_webhook(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)
    status = await b24_service.get_status(db_session, admin_user.company_id)
    assert "webhook_url" not in status
    assert status["configured"] is True
    assert status["verified"] is False
    assert status["portal"] == "demo.bitrix24.ru"


@pytest.mark.asyncio
async def test_get_status_unconfigured(db_session, admin_user, fernet_key):
    status = await b24_service.get_status(db_session, admin_user.company_id)
    assert status["configured"] is False
    assert "webhook_url" not in status


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connection_success(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)
    mock = AsyncMock(return_value={"result": [{"ID": "1"}], "total": 42})
    with patch(CALL_TARGET, new=mock):
        result = await b24_service.test_connection(
            db_session, admin_user.company_id, admin_user.id
        )

    mock.assert_awaited_once()
    # вызван с расшифрованным URL вебхука
    assert mock.await_args.args[0] == WEBHOOK
    assert result["user_count"] == 42
    assert result["portal"] == "demo.bitrix24.ru"

    status = await b24_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is True
    assert status["user_count"] == 42
    assert status["last_test_error"] is None


@pytest.mark.asyncio
async def test_connection_failure_records_error(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)
    boom = AsyncMock(side_effect=AppError(
        code="B24_API_ERROR", message="Битрикс24: invalid_token", status_code=400
    ))
    with patch(CALL_TARGET, new=boom):
        with pytest.raises(AppError):
            await b24_service.test_connection(
                db_session, admin_user.company_id, admin_user.id
            )

    status = await b24_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is False
    assert status["last_test_error"] == "Битрикс24: invalid_token"


@pytest.mark.asyncio
async def test_connection_not_configured(db_session, admin_user, fernet_key):
    with patch(CALL_TARGET, new=AsyncMock()) as mock:
        with pytest.raises(ValidationError):
            await b24_service.test_connection(
                db_session, admin_user.company_id, admin_user.id
            )
    mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# preview_users + disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_users_simplifies(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)
    raw = {
        "result": [
            {"ID": 1, "NAME": "Анна", "LAST_NAME": "Седова", "WORK_POSITION": "HR", "EMAIL": "a@x.ru", "ACTIVE": True},
            {"ID": 2, "NAME": "Пётр", "LAST_NAME": "Иванов", "ACTIVE": "N"},
        ],
        "total": 2,
    }
    with patch(CALL_TARGET, new=AsyncMock(return_value=raw)):
        out = await b24_service.preview_users(db_session, admin_user.company_id)

    assert out["total"] == 2
    assert out["users"][0] == {
        "id": "1", "name": "Анна", "last_name": "Седова",
        "position": "HR", "email": "a@x.ru", "active": True,
    }
    # ACTIVE='N' → уволенный
    assert out["users"][1]["active"] is False
    assert out["users"][1]["position"] is None


@pytest.mark.asyncio
async def test_disconnect_resets_verified(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)
    with patch(CALL_TARGET, new=AsyncMock(return_value={"result": [], "total": 0})):
        await b24_service.test_connection(db_session, admin_user.company_id, admin_user.id)
    assert (await b24_service.get_status(db_session, admin_user.company_id))["verified"] is True

    await b24_service.disconnect(db_session, admin_user.company_id, admin_user.id)
    status = await b24_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is False
    assert status["configured"] is True
