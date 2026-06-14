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


@pytest.fixture(autouse=True)
def clear_hh_env(monkeypatch):
    """Форсируем пустой ключ приложения в env для детерминизма тестов.

    На VPS тест-контейнер видит прод-.env, где HH_* заданы — без этого env
    перебивал бы legacy DB-колонки и ломал DB-основанные ассерты. С пустым env
    тесты проверяют fallback-путь (legacy DB), эквивалентный прежнему DB-flow.
    """
    monkeypatch.setattr("app.config.settings.HH_CLIENT_ID", "")
    monkeypatch.setattr("app.config.settings.HH_CLIENT_SECRET", "")
    monkeypatch.setattr("app.config.settings.HH_REDIRECT_URI", "")


@pytest.fixture
def mock_hh_config(monkeypatch):
    """Мокаем конфигурацию hh.ru (env-путь) для тестов"""
    monkeypatch.setattr("app.config.settings.HH_CLIENT_ID", "test_client_id")
    monkeypatch.setattr("app.config.settings.HH_CLIENT_SECRET", "test_client_secret")
    monkeypatch.setattr("app.config.settings.HH_REDIRECT_URI", "https://test.com/callback")


@pytest.mark.asyncio
async def test_save_config_stores_encrypted_secret(db_session, admin_user, fernet_key):
    """Тест сохранения конфигурации с шифрованием client_secret"""
    # Сохраняем конфигурацию
    integration = await hh_service.save_config(
        db_session,
        admin_user.company_id,
        admin_user.id,
        "test_client_id",
        "test_client_secret",
        "https://test.com/callback"
    )

    # Проверяем что конфигурация записана
    assert integration.client_id == "test_client_id"
    assert integration.redirect_uri == "https://test.com/callback"
    assert integration.client_secret != "test_client_secret"  # Должен быть зашифрован

    # Проверяем что client_secret правильно расшифровывается
    decrypted_secret = decrypt_text(integration.client_secret)
    assert decrypted_secret == "test_client_secret"

    # Проверяем что токены пока null
    assert integration.access_token is None
    assert integration.refresh_token is None
    assert integration.expires_at is None


@pytest.mark.asyncio
async def test_save_config_updates_existing_and_clears_tokens_on_client_id_change(db_session, admin_user, fernet_key):
    """Тест обновления конфигурации с обнулением токенов при смене client_id"""
    # Создаем интеграцию с токенами
    integration = HhIntegration(
        company_id=admin_user.company_id,
        client_id="old_client_id",
        client_secret=encrypt_text("old_client_secret"),
        redirect_uri="https://old.com/callback",
        access_token=encrypt_text("access_token"),
        refresh_token=encrypt_text("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        hh_employer_id="123456"
    )
    db_session.add(integration)
    await db_session.commit()
    old_id = integration.id

    # Обновляем конфигурацию с новым client_id
    updated_integration = await hh_service.save_config(
        db_session,
        admin_user.company_id,
        admin_user.id,
        "new_client_id",  # Изменился
        "new_client_secret",
        "https://new.com/callback"
    )

    # Проверяем что это та же запись
    assert updated_integration.id == old_id

    # Проверяем что конфигурация обновилась
    assert updated_integration.client_id == "new_client_id"
    assert updated_integration.redirect_uri == "https://new.com/callback"
    decrypted_secret = decrypt_text(updated_integration.client_secret)
    assert decrypted_secret == "new_client_secret"

    # Проверяем что токены обнулены (из-за смены client_id)
    assert updated_integration.access_token is None
    assert updated_integration.refresh_token is None
    assert updated_integration.expires_at is None
    assert updated_integration.hh_employer_id is None


@pytest.mark.asyncio
async def test_save_config_updates_without_clearing_tokens_when_client_id_same(db_session, admin_user, fernet_key):
    """Тест обновления конфигурации без обнуления токенов если client_id не изменился"""
    # Создаем интеграцию с токенами
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    integration = HhIntegration(
        company_id=admin_user.company_id,
        client_id="same_client_id",
        client_secret=encrypt_text("old_client_secret"),
        redirect_uri="https://old.com/callback",
        access_token=encrypt_text("access_token"),
        refresh_token=encrypt_text("refresh_token"),
        expires_at=expires_at,
        hh_employer_id="123456"
    )
    db_session.add(integration)
    await db_session.commit()

    # Обновляем конфигурацию с тем же client_id
    updated_integration = await hh_service.save_config(
        db_session,
        admin_user.company_id,
        admin_user.id,
        "same_client_id",  # Не изменился
        "new_client_secret",
        "https://new.com/callback"
    )

    # Проверяем что конфигурация обновилась
    assert updated_integration.client_id == "same_client_id"
    assert updated_integration.redirect_uri == "https://new.com/callback"
    decrypted_secret = decrypt_text(updated_integration.client_secret)
    assert decrypted_secret == "new_client_secret"

    # Проверяем что токены ОСТАЛИСЬ (client_id не изменился)
    assert updated_integration.access_token is not None
    assert updated_integration.refresh_token is not None
    assert updated_integration.expires_at == expires_at
    assert updated_integration.hh_employer_id == "123456"


@pytest.mark.asyncio
async def test_save_config_validation_errors(db_session, admin_user):
    """Тест валидации при сохранении конфигурации"""
    # Пустой client_id
    with pytest.raises(ValidationError, match="Все поля обязательны"):
        await hh_service.save_config(
            db_session, admin_user.company_id, admin_user.id, "", "secret", "uri"
        )

    # Пустой client_secret
    with pytest.raises(ValidationError, match="Все поля обязательны"):
        await hh_service.save_config(
            db_session, admin_user.company_id, admin_user.id, "id", "", "uri"
        )

    # Пустой redirect_uri
    with pytest.raises(ValidationError, match="Все поля обязательны"):
        await hh_service.save_config(
            db_session, admin_user.company_id, admin_user.id, "id", "secret", ""
        )


@pytest.mark.asyncio
async def test_start_oauth_without_config_raises_error(db_session, admin_user):
    """Тест ошибки при start_oauth без сохранённой конфигурации"""
    with pytest.raises(ValidationError, match="не настроен"):
        await hh_service.start_oauth(db_session, admin_user.company_id, admin_user.id)


@pytest.mark.asyncio
async def test_start_oauth_with_config_creates_state_and_returns_url(db_session, admin_user, fernet_key):
    """Тест создания OAuth state и генерации authorize URL с сохранённой конфигурацией"""
    # Сначала сохраняем конфигурацию
    await hh_service.save_config(
        db_session,
        admin_user.company_id,
        admin_user.id,
        "test_client_id",
        "test_client_secret",
        "https://test.com/callback"
    )

    # Мокаем hh клиент
    with patch('app.services.integrations.hh.service.hh_client') as mock_client:
        mock_client.build_authorize_url.return_value = "https://hh.ru/oauth/authorize?client_id=test_client_id&state=abc123"

        # Вызываем start_oauth
        authorize_url = await hh_service.start_oauth(db_session, admin_user.company_id, admin_user.id)

        # Проверяем что URL сгенерирован
        assert "https://hh.ru/oauth/authorize" in authorize_url
        assert "client_id=test_client_id" in authorize_url
        assert "state=" in authorize_url

        # Проверяем что state создан в БД
        from sqlalchemy import select
        result = await db_session.execute(select(HhOauthState))
        oauth_state = result.scalar_one_or_none()

        assert oauth_state is not None
        assert oauth_state.company_id == admin_user.company_id
        assert oauth_state.user_id == admin_user.id
        assert oauth_state.expires_at > datetime.now(timezone.utc)

        # Проверяем что hh_client.build_authorize_url был вызван с правильными параметрами
        mock_client.build_authorize_url.assert_called_once()
        call_args = mock_client.build_authorize_url.call_args[0]
        assert call_args[0] == oauth_state.state  # state
        assert call_args[1] == "test_client_id"   # client_id
        assert call_args[2] == "https://test.com/callback"  # redirect_uri


@pytest.mark.asyncio
async def test_complete_oauth_creates_integration(db_session, admin_user, fernet_key):
    """Тест успешного завершения OAuth и обновления интеграции"""
    # Сначала сохраняем конфигурацию
    await hh_service.save_config(
        db_session,
        admin_user.company_id,
        admin_user.id,
        "test_client_id",
        "test_client_secret",
        "https://test.com/callback"
    )

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

        # Проверяем что hh API были вызваны с правильными параметрами
        mock_client.exchange_code.assert_called_once_with(
            "test_code", "test_client_id", "test_client_secret", "https://test.com/callback"
        )
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
async def test_get_valid_access_token_refreshes_when_expired(db_session, admin_user, fernet_key):
    """Тест обновления токена, если он истек или истекает скоро"""
    # Создаем интеграцию с истекающим токеном и конфигурацией
    integration = HhIntegration(
        company_id=admin_user.company_id,
        client_id="test_client_id",
        client_secret=encrypt_text("test_client_secret"),
        redirect_uri="https://test.com/callback",
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

        # Проверяем что refresh был вызван с правильными параметрами
        mock_client.refresh_tokens.assert_called_once_with(
            "old_refresh_token", "test_client_id", "test_client_secret"
        )

        # Проверяем что интеграция обновилась
        await db_session.refresh(integration)
        assert decrypt_text(integration.access_token) == "new_access_token"
        assert decrypt_text(integration.refresh_token) == "new_refresh_token"


@pytest.mark.asyncio
async def test_disconnect_nullifies_tokens_but_keeps_config(db_session, admin_user, fernet_key):
    """Тест отключения интеграции (обнуляет токены, но оставляет config)"""
    # Создаем интеграцию с конфигурацией и токенами
    integration = HhIntegration(
        company_id=admin_user.company_id,
        client_id="test_client_id",
        client_secret=encrypt_text("test_client_secret"),
        redirect_uri="https://test.com/callback",
        access_token=encrypt_text("access_token"),
        refresh_token=encrypt_text("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        hh_employer_id="123456"
    )
    db_session.add(integration)
    await db_session.commit()

    # Отключаем
    await hh_service.disconnect(db_session, admin_user.company_id, admin_user.id)

    # Проверяем что интеграция осталась, но токены обнулены
    from sqlalchemy import select
    result = await db_session.execute(
        select(HhIntegration).where(HhIntegration.company_id == admin_user.company_id)
    )
    updated_integration = result.scalar_one_or_none()
    assert updated_integration is not None

    # Конфигурация должна остаться
    assert updated_integration.client_id == "test_client_id"
    assert updated_integration.client_secret is not None  # Зашифровано
    assert updated_integration.redirect_uri == "https://test.com/callback"

    # Токены должны быть обнулены
    assert updated_integration.access_token is None
    assert updated_integration.refresh_token is None
    assert updated_integration.expires_at is None
    assert updated_integration.hh_employer_id is None


@pytest.mark.asyncio
async def test_disconnect_not_found_raises_error(db_session, admin_user):
    """Тест ошибки при отключении несуществующей интеграции"""
    with pytest.raises(NotFoundError, match="Интеграция hh.ru не найдена"):
        await hh_service.disconnect(db_session, admin_user.company_id, admin_user.id)


@pytest.mark.asyncio
async def test_get_status_returns_not_configured_when_no_integration(db_session, admin_user):
    """Тест статуса когда интеграции нет"""
    status = await hh_service.get_status(db_session, admin_user.company_id)

    expected = {
        "configured": False,
        "connected": False,
        "redirect_uri": None,
        "client_id_masked": None,
        "hh_employer_id": None,
        "expires_at": None
    }
    assert status == expected


@pytest.mark.asyncio
async def test_get_status_configured_but_not_connected(db_session, admin_user, fernet_key):
    """Тест статуса когда конфигурация сохранена, но не подключено"""
    # Создаем интеграцию только с конфигурацией
    integration = HhIntegration(
        company_id=admin_user.company_id,
        client_id="test_client_id_long",
        client_secret=encrypt_text("test_client_secret"),
        redirect_uri="https://test.com/callback"
    )
    db_session.add(integration)
    await db_session.commit()

    # Получаем статус
    status = await hh_service.get_status(db_session, admin_user.company_id)

    expected = {
        "configured": True,
        "connected": False,
        "redirect_uri": "https://test.com/callback",
        "client_id_masked": "••••long",
        "hh_employer_id": None,
        "expires_at": None
    }
    assert status == expected


@pytest.mark.asyncio
async def test_get_status_configured_and_connected(db_session, admin_user, fernet_key):
    """Тест статуса когда интеграция полностью настроена и подключена"""
    # Создаем интеграцию с конфигурацией и токенами
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    integration = HhIntegration(
        company_id=admin_user.company_id,
        client_id="test_client_id_short",
        client_secret=encrypt_text("test_client_secret"),
        redirect_uri="https://test.com/callback",
        access_token=encrypt_text("access_token"),
        refresh_token=encrypt_text("refresh_token"),
        expires_at=expires_at,
        hh_employer_id="123456"
    )
    db_session.add(integration)
    await db_session.commit()

    # Получаем статус
    status = await hh_service.get_status(db_session, admin_user.company_id)

    expected = {
        "configured": True,
        "connected": True,
        "redirect_uri": "https://test.com/callback",
        "client_id_masked": "••••hort",
        "hh_employer_id": "123456",
        "expires_at": expires_at
    }
    assert status == expected


@pytest.mark.asyncio
async def test_get_status_short_client_id_masking(db_session, admin_user, fernet_key):
    """Тест маскирования короткого client_id"""
    # Создаем интеграцию с коротким client_id
    integration = HhIntegration(
        company_id=admin_user.company_id,
        client_id="abc",  # Короче 4 символов
        client_secret=encrypt_text("test_client_secret"),
        redirect_uri="https://test.com/callback"
    )
    db_session.add(integration)
    await db_session.commit()

    # Получаем статус
    status = await hh_service.get_status(db_session, admin_user.company_id)

    # Для коротких ID просто ••••
    assert status["client_id_masked"] == "••••"