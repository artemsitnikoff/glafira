"""Тесты для hh.ru OAuth интеграции"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet

from app.services.integrations.hh import service as hh_service
from app.services.settings.crypto import encrypt_text, decrypt_text
from app.core.errors import ValidationError, NotFoundError
from app.models import HhIntegration, HhOauthState


@pytest.fixture
def fernet_key(monkeypatch):
    """Фикстура для FERNET_KEY в тестах"""
    test_key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.FERNET_KEY", test_key)
    return test_key


@pytest.fixture
def mock_hh_config(monkeypatch):
    """Мокаем конфигурацию hh.ru для тестов"""
    monkeypatch.setattr("app.config.settings.HH_CLIENT_ID", "test_client_id")
    monkeypatch.setattr("app.config.settings.HH_CLIENT_SECRET", "test_client_secret")
    monkeypatch.setattr("app.config.settings.HH_REDIRECT_URI", "https://test.com/callback")


@pytest.mark.asyncio
async def test_start_oauth_creates_state_and_returns_url(db_session, admin_user, mock_hh_config):
    """Тест создания OAuth state и генерации authorize URL"""
    # Мокаем hh клиент
    with patch('app.services.integrations.hh.service.hh_client') as mock_client:
        mock_client.build_authorize_url.return_value = "https://hh.ru/oauth/authorize?client_id=test&state=abc123"

        # Вызываем start_oauth
        authorize_url = await hh_service.start_oauth(db_session, admin_user.company_id, admin_user.id)

        # Проверяем что URL сгенерирован
        assert "https://hh.ru/oauth/authorize" in authorize_url
        assert "client_id=test" in authorize_url
        assert "state=" in authorize_url

        # Проверяем что state создан в БД
        from sqlalchemy import select
        result = await db_session.execute(select(HhOauthState))
        oauth_state = result.scalar_one_or_none()

        assert oauth_state is not None
        assert oauth_state.company_id == admin_user.company_id
        assert oauth_state.user_id == admin_user.id
        assert oauth_state.expires_at > datetime.now(timezone.utc)

        # Проверяем что hh_client.build_authorize_url был вызван с правильным state
        mock_client.build_authorize_url.assert_called_once()
        called_state = mock_client.build_authorize_url.call_args[0][0]
        assert called_state == oauth_state.state


@pytest.mark.asyncio
async def test_complete_oauth_creates_integration(db_session, admin_user, fernet_key, mock_hh_config):
    """Тест успешного завершения OAuth и создания интеграции"""
    # Создаем state запись
    from sqlalchemy import select
    oauth_state = HhOauthState(
        state="test_state",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db_session.add(oauth_state)
    await db_session.commit()

    # Мокаем hh клиент
    mock_token_response = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "token_type": "bearer",
        "expires_in": 3600
    }

    mock_me_response = {
        "employer": {"id": "123456"}
    }

    with patch('app.services.integrations.hh.service.hh_client') as mock_client:
        mock_client.exchange_code = AsyncMock(return_value=mock_token_response)
        mock_client.get_me = AsyncMock(return_value=mock_me_response)

        # Вызываем complete_oauth
        integration = await hh_service.complete_oauth(db_session, "test_code", "test_state")

        # Проверяем что интеграция создана
        assert integration is not None
        assert integration.company_id == admin_user.company_id
        assert integration.hh_employer_id == "123456"
        assert integration.connected_by_user_id == admin_user.id

        # Проверяем что токены зашифрованы в БД
        stored_access = integration.access_token
        stored_refresh = integration.refresh_token

        # Токены должны быть зашифрованы (не равны исходным)
        assert stored_access != "test_access_token"
        assert stored_refresh != "test_refresh_token"

        # Но должны расшифровываться корректно
        assert decrypt_text(stored_access) == "test_access_token"
        assert decrypt_text(stored_refresh) == "test_refresh_token"

        # Проверяем что state удален
        result = await db_session.execute(select(HhOauthState).where(HhOauthState.state == "test_state"))
        deleted_state = result.scalar_one_or_none()
        assert deleted_state is None

        # Проверяем что hh API были вызваны
        mock_client.exchange_code.assert_called_once_with("test_code")
        mock_client.get_me.assert_called_once_with("test_access_token")


@pytest.mark.asyncio
async def test_complete_oauth_invalid_state_raises_error(db_session):
    """Тест ошибки при невалидном state"""
    with pytest.raises(ValidationError, match="Невалидный или истекший state"):
        await hh_service.complete_oauth(db_session, "test_code", "invalid_state")


@pytest.mark.asyncio
async def test_complete_oauth_expired_state_raises_error(db_session, admin_user):
    """Тест ошибки при истекшем state"""
    # Создаем истекший state
    oauth_state = HhOauthState(
        state="expired_state",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)  # Истек минуту назад
    )
    db_session.add(oauth_state)
    await db_session.commit()

    with pytest.raises(ValidationError, match="Истекший state"):
        await hh_service.complete_oauth(db_session, "test_code", "expired_state")


@pytest.mark.asyncio
async def test_get_valid_access_token_returns_current_when_valid(db_session, admin_user, fernet_key):
    """Тест получения текущего токена, если он еще валидный"""
    # Создаем интеграцию с валидным токеном
    integration = HhIntegration(
        company_id=admin_user.company_id,
        access_token=encrypt_text("current_access_token"),
        refresh_token=encrypt_text("current_refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),  # Истечет через час
        hh_employer_id="123456"
    )
    db_session.add(integration)
    await db_session.commit()

    # Получаем токен
    token = await hh_service.get_valid_access_token(db_session, admin_user.company_id)

    # Должен вернуть текущий токен без refresh
    assert token == "current_access_token"


@pytest.mark.asyncio
async def test_get_valid_access_token_refreshes_when_expired(db_session, admin_user, fernet_key, mock_hh_config):
    """Тест обновления токена, если он истек или истекает скоро"""
    # Создаем интеграцию с истекающим токеном
    integration = HhIntegration(
        company_id=admin_user.company_id,
        access_token=encrypt_text("old_access_token"),
        refresh_token=encrypt_text("old_refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),  # Истечет через 2 минуты (< 5 минут)
        hh_employer_id="123456"
    )
    db_session.add(integration)
    await db_session.commit()

    # Мокаем refresh_tokens
    mock_refresh_response = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "token_type": "bearer",
        "expires_in": 3600
    }

    with patch('app.services.integrations.hh.service.hh_client') as mock_client:
        mock_client.refresh_tokens = AsyncMock(return_value=mock_refresh_response)

        # Получаем токен
        token = await hh_service.get_valid_access_token(db_session, admin_user.company_id)

        # Должен вернуть новый токен
        assert token == "new_access_token"

        # Проверяем что refresh был вызван с правильным refresh_token
        mock_client.refresh_tokens.assert_called_once_with("old_refresh_token")

        # Проверяем что интеграция обновилась
        await db_session.refresh(integration)
        assert decrypt_text(integration.access_token) == "new_access_token"
        assert decrypt_text(integration.refresh_token) == "new_refresh_token"


@pytest.mark.asyncio
async def test_disconnect_removes_integration(db_session, admin_user, fernet_key):
    """Тест отключения интеграции"""
    # Создаем интеграцию
    integration = HhIntegration(
        company_id=admin_user.company_id,
        access_token=encrypt_text("access_token"),
        refresh_token=encrypt_text("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        hh_employer_id="123456"
    )
    db_session.add(integration)
    await db_session.commit()

    # Отключаем
    await hh_service.disconnect(db_session, admin_user.company_id, admin_user.id)

    # Проверяем что интеграция удалена
    from sqlalchemy import select
    result = await db_session.execute(
        select(HhIntegration).where(HhIntegration.company_id == admin_user.company_id)
    )
    deleted_integration = result.scalar_one_or_none()
    assert deleted_integration is None


@pytest.mark.asyncio
async def test_disconnect_not_found_raises_error(db_session, admin_user):
    """Тест ошибки при отключении несуществующей интеграции"""
    with pytest.raises(NotFoundError, match="Интеграция hh.ru не найдена"):
        await hh_service.disconnect(db_session, admin_user.company_id, admin_user.id)


@pytest.mark.asyncio
async def test_get_status_returns_connected_false_when_no_integration(db_session, admin_user):
    """Тест статуса когда интеграции нет"""
    status = await hh_service.get_status(db_session, admin_user.company_id)

    assert status == {"connected": False}


@pytest.mark.asyncio
async def test_get_status_returns_full_info_when_connected(db_session, admin_user, fernet_key):
    """Тест статуса когда интеграция подключена"""
    # Создаем интеграцию
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=1)

    integration = HhIntegration(
        company_id=admin_user.company_id,
        access_token=encrypt_text("access_token"),
        refresh_token=encrypt_text("refresh_token"),
        expires_at=expires_at,
        hh_employer_id="123456",
        created_at=created_at
    )
    db_session.add(integration)
    await db_session.commit()

    # Получаем статус
    status = await hh_service.get_status(db_session, admin_user.company_id)

    assert status == {
        "connected": True,
        "hh_employer_id": "123456",
        "connected_at": created_at,
        "expires_at": expires_at
    }