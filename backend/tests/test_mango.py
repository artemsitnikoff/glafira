"""Тесты Mango Office интеграции (VPBX API).

Клиент (MangoClient.check_auth) ВСЕГДА замокан — тесты не ходят в сеть.
Проверяем реальную логику: шифрование api_key/api_salt, валидный запрос stats/request
для избежания блокировки, отсутствие утечки секретов в статусе, фиксацию результата проверки.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from cryptography.fernet import Fernet

from app.services.integrations.mango import service as mango_service
from app.services.settings.crypto import decrypt_text
from app.core.errors import AppError, ValidationError

CALL_TARGET = "app.services.integrations.mango.service.MangoClient"
API_KEY = "test123"
API_SALT = "secretsalt"
BASE_URL = "https://app.mango-office.ru/vpbx/"


@pytest.fixture
def fernet_key(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.FERNET_KEY", test_key)
    return test_key


async def _save(db_session, user, api_key=API_KEY, api_salt=API_SALT, vpbx_api_url=None):
    return await mango_service.save_config(
        db_session,
        user.company_id,
        api_key=api_key,
        api_salt=api_salt,
        vpbx_api_url=vpbx_api_url,
        actor_user_id=user.id,
    )


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_config_encrypts_secrets(db_session, admin_user, fernet_key):
    row = await _save(db_session, admin_user)
    assert row.provider == "mango"
    assert row.status == "disconnected"

    # Секреты зашифрованы
    assert row.config["api_key"] != API_KEY
    assert row.config["api_salt"] != API_SALT
    assert decrypt_text(row.config["api_key"]) == API_KEY
    assert decrypt_text(row.config["api_salt"]) == API_SALT

    # vpbx_api_url открыто, дефолтное значение
    assert row.config["vpbx_api_url"] == "https://app.mango-office.ru/vpbx/"
    assert row.config["last_test_ok"] is False


@pytest.mark.asyncio
async def test_save_config_write_only_secrets(db_session, admin_user, fernet_key):
    # Первое сохранение
    await _save(db_session, admin_user)

    # Второе сохранение без api_key (должно сохранить старое значение)
    # URL — легитимный хост из whitelist Mango (custom.mango.ru правильно режется SSRF-гардом);
    # *.mango-office.ru проходит как host == "app.mango-office.ru".
    row = await mango_service.save_config(
        db_session,
        admin_user.company_id,
        api_key=None,  # пустой
        api_salt="newsalt",
        vpbx_api_url="https://app.mango-office.ru/vpbx2/",
        actor_user_id=admin_user.id,
    )

    # Старый api_key сохранен, новый api_salt
    assert decrypt_text(row.config["api_key"]) == API_KEY
    assert decrypt_text(row.config["api_salt"]) == "newsalt"
    assert row.config["vpbx_api_url"] == "https://app.mango-office.ru/vpbx2/"


@pytest.mark.asyncio
async def test_save_config_requires_secrets(db_session, admin_user, fernet_key):
    # Нет api_key
    with pytest.raises(ValidationError, match="код продукта"):
        await mango_service.save_config(
            db_session,
            admin_user.company_id,
            api_key=None,
            api_salt=API_SALT,
            actor_user_id=admin_user.id,
        )

    # Нет api_salt
    with pytest.raises(ValidationError, match="ключ подписи"):
        await mango_service.save_config(
            db_session,
            admin_user.company_id,
            api_key=API_KEY,
            api_salt=None,
            actor_user_id=admin_user.id,
        )


# ---------------------------------------------------------------------------
# get_status — не отдаёт секреты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_never_returns_secrets(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)
    status = await mango_service.get_status(db_session, admin_user.company_id)
    assert "api_key" not in status
    assert "api_salt" not in status
    assert status["configured"] is True
    assert status["verified"] is False
    assert status["vpbx_api_url"] == BASE_URL


@pytest.mark.asyncio
async def test_get_status_unconfigured(db_session, admin_user, fernet_key):
    status = await mango_service.get_status(db_session, admin_user.company_id)
    assert status["configured"] is False
    assert status["verified"] is False
    assert "api_key" not in status
    assert "api_salt" not in status


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connection_success(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)

    # Мокаем успешный check_auth
    mock_client_class = MagicMock()
    mock_client_instance = AsyncMock()
    mock_client_instance.check_auth.return_value = {"ok": True}
    mock_client_class.return_value = mock_client_instance

    with patch(CALL_TARGET, new=mock_client_class):
        result = await mango_service.test_connection(
            db_session, admin_user.company_id, actor_user_id=admin_user.id
        )

    # Проверяем, что клиент создан с правильными параметрами
    mock_client_class.assert_called_once_with(API_KEY, API_SALT, BASE_URL)
    mock_client_instance.check_auth.assert_awaited_once()
    mock_client_instance.close.assert_awaited_once()

    assert result["vpbx_api_url"] == BASE_URL
    assert "last_test_at" in result

    # Статус обновился
    status = await mango_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is True
    assert status["last_test_error"] is None


@pytest.mark.asyncio
async def test_connection_failure_records_error(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)

    # Мокаем ошибку check_auth
    mock_client_class = MagicMock()
    mock_client_instance = AsyncMock()
    mock_client_instance.check_auth.side_effect = AppError(
        code="MANGO_AUTH_ERROR",
        message="Ошибка авторизации Mango Office",
        status_code=400
    )
    mock_client_class.return_value = mock_client_instance

    with patch(CALL_TARGET, new=mock_client_class):
        with pytest.raises(AppError):
            await mango_service.test_connection(
                db_session, admin_user.company_id, actor_user_id=admin_user.id
            )

    # close вызвался даже при ошибке
    mock_client_instance.close.assert_awaited_once()

    status = await mango_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is False
    assert status["last_test_error"] == "Ошибка авторизации Mango Office"


@pytest.mark.asyncio
async def test_connection_not_configured(db_session, admin_user, fernet_key):
    with patch(CALL_TARGET, new=AsyncMock()) as mock:
        with pytest.raises(ValidationError, match="Mango Office не настроен"):
            await mango_service.test_connection(
                db_session, admin_user.company_id, actor_user_id=admin_user.id
            )
    mock.assert_not_called()


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_resets_verified(db_session, admin_user, fernet_key):
    await _save(db_session, admin_user)

    # Имитируем успешное подключение
    mock_client_class = MagicMock()
    mock_client_instance = AsyncMock()
    mock_client_instance.check_auth.return_value = {"ok": True}
    mock_client_class.return_value = mock_client_instance

    with patch(CALL_TARGET, new=mock_client_class):
        await mango_service.test_connection(
            db_session, admin_user.company_id, actor_user_id=admin_user.id
        )

    assert (await mango_service.get_status(db_session, admin_user.company_id))["verified"] is True

    # Отключаем
    await mango_service.disconnect(
        db_session, admin_user.company_id, actor_user_id=admin_user.id
    )

    status = await mango_service.get_status(db_session, admin_user.company_id)
    assert status["verified"] is False
    assert status["configured"] is True  # конфиг остается


@pytest.mark.asyncio
async def test_disconnect_not_configured(db_session, admin_user, fernet_key):
    with pytest.raises(ValidationError, match="Mango Office не настроен"):
        await mango_service.disconnect(
            db_session, admin_user.company_id, actor_user_id=admin_user.id
        )


# ---------------------------------------------------------------------------
# Изоляция компаний
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_isolation(db_session, admin_user, other_company, fernet_key):
    await _save(db_session, admin_user)

    # Другая компания не видит конфиг
    status = await mango_service.get_status(db_session, other_company.id)
    assert status["configured"] is False

    # Другая компания не может тестировать чужой конфиг
    with pytest.raises(ValidationError):
        await mango_service.test_connection(
            db_session, other_company.id, actor_user_id=admin_user.id
        )