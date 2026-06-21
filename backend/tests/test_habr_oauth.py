"""Тесты OAuth-интеграции Хабр Карьера.

ТОЛЬКО OAuth-подключение (получить + сохранить токен per-company).
Приём откликов / поиск / синхронизация — НЕ тестируются (не реализованы).

Тесты:
(а) callback с валидным code+state + мок успешного token-POST → HabrIntegration с токеном, redirect habr=connected
(б) callback с битым/отсутствующим state → redirect habr=error, НЕ 500, токен НЕ сохранён
(в) callback error=access_denied → redirect habr=denied
(г) token-обмен вернул 400/без access_token → redirect habr=error, токен НЕ сохранён
(д) company-изоляция: state компании A сохраняет токен только A
(е) start_oauth без HABR_CLIENT_ID → ValidationError
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from cryptography.fernet import Fernet

from app.services.integrations.habr import service as habr_service
from app.services.settings.crypto import decrypt_text
from app.core.errors import ValidationError
from app.models.habr_integration import HabrIntegration, HabrOauthState
from app.models import Company


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture
def fernet_key(monkeypatch):
    """Временный FERNET_KEY для тестов шифрования."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.FERNET_KEY", key)
    monkeypatch.setattr("app.services.settings.crypto.settings.FERNET_KEY", key)
    return key


@pytest.fixture(autouse=True)
def clear_habr_env(monkeypatch):
    """Сбрасываем Хабр-env, чтобы тесты не видели реальные ключи с VPS."""
    monkeypatch.setattr("app.config.settings.HABR_CLIENT_ID", "")
    monkeypatch.setattr("app.config.settings.HABR_CLIENT_SECRET", "")
    monkeypatch.setattr("app.config.settings.HABR_REDIRECT_URI", "")
    monkeypatch.setattr("app.config.settings.HABR_AUTHORIZE_URL",
                        "https://career.habr.com/integrations/oauth/authorize")
    monkeypatch.setattr("app.config.settings.HABR_TOKEN_URL",
                        "https://career.habr.com/integrations/oauth/token")
    monkeypatch.setattr("app.config.settings.HABR_SCOPE", "")


@pytest.fixture
def habr_env(monkeypatch):
    """Активная Хабр-конфигурация (нужна для тестов start_oauth/handle_callback)."""
    monkeypatch.setattr("app.config.settings.HABR_CLIENT_ID", "test_habr_client_id")
    monkeypatch.setattr("app.config.settings.HABR_CLIENT_SECRET", "test_habr_secret")
    monkeypatch.setattr("app.config.settings.HABR_REDIRECT_URI",
                        "https://glafira.dclouds.ru/api/v1/integrations/habr/callback")


# ---------------------------------------------------------------------------
# (е) start_oauth без HABR_CLIENT_ID → ValidationError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_oauth_without_client_id_raises_validation_error(db_session, admin_user):
    """start_oauth без HABR_CLIENT_ID должен кидать ValidationError с понятным сообщением."""
    with pytest.raises(ValidationError, match="HABR_CLIENT_ID"):
        await habr_service.start_oauth(db_session, admin_user.company_id, admin_user.id)


@pytest.mark.asyncio
async def test_start_oauth_without_redirect_uri_raises_validation_error(db_session, admin_user, monkeypatch):
    """start_oauth без HABR_REDIRECT_URI тоже ValidationError."""
    monkeypatch.setattr("app.config.settings.HABR_CLIENT_ID", "some_id")
    monkeypatch.setattr("app.config.settings.HABR_REDIRECT_URI", "")
    with pytest.raises(ValidationError, match="HABR_REDIRECT_URI"):
        await habr_service.start_oauth(db_session, admin_user.company_id, admin_user.id)


# ---------------------------------------------------------------------------
# start_oauth успешный путь
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_oauth_creates_state_and_returns_url(db_session, admin_user, habr_env):
    """start_oauth создаёт запись state и возвращает authorize URL."""
    from sqlalchemy import select

    url = await habr_service.start_oauth(db_session, admin_user.company_id, admin_user.id)
    await db_session.commit()

    assert "career.habr.com" in url
    assert "response_type=code" in url
    assert "client_id=test_habr_client_id" in url
    assert "state=" in url

    result = await db_session.execute(
        select(HabrOauthState).where(HabrOauthState.company_id == admin_user.company_id)
    )
    state_obj = result.scalar_one_or_none()
    assert state_obj is not None
    assert state_obj.expires_at > datetime.now(timezone.utc)
    assert state_obj.user_id == admin_user.id


@pytest.mark.asyncio
async def test_start_oauth_scope_not_in_url_when_empty(db_session, admin_user, habr_env):
    """Если HABR_SCOPE пустой — scope в URL нет."""
    url = await habr_service.start_oauth(db_session, admin_user.company_id, admin_user.id)
    assert "scope=" not in url


@pytest.mark.asyncio
async def test_start_oauth_scope_in_url_when_set(db_session, admin_user, habr_env, monkeypatch):
    """Если HABR_SCOPE задан — scope попадает в URL."""
    monkeypatch.setattr("app.config.settings.HABR_SCOPE", "resume:read")
    url = await habr_service.start_oauth(db_session, admin_user.company_id, admin_user.id)
    assert "scope=resume%3Aread" in url or "scope=resume:read" in url


# ---------------------------------------------------------------------------
# (а) callback с валидным code+state + мок успешного token-POST
# ---------------------------------------------------------------------------

@pytest.fixture
async def valid_habr_state(db_session, admin_user, habr_env):
    """Валидный state для admin_user.company."""
    state_obj = HabrOauthState(
        state="valid_test_state_abc123",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=9),
    )
    db_session.add(state_obj)
    await db_session.commit()
    return state_obj


@pytest.mark.asyncio
async def test_handle_callback_success_saves_token(
    db_session, admin_user, valid_habr_state, fernet_key, habr_env
):
    """(а) Успешный callback → HabrIntegration с Fernet-токеном у нужной компании."""
    from sqlalchemy import select

    token_response = {
        "access_token": "real_habr_access_token",
        "refresh_token": "real_habr_refresh_token",
        "expires_in": 3600,
    }

    with patch(
        "app.services.integrations.habr.service.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        # httpx Response.json() — синхронный: возвращает dict, НЕ корутину
        mock_resp.json = MagicMock(return_value=token_response)
        mock_client_cls.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_resp
        )

        company_id = await habr_service.handle_callback(
            db_session, "auth_code_xyz", "valid_test_state_abc123"
        )
        await db_session.commit()

    assert company_id == admin_user.company_id

    # Проверяем что токен сохранён зашифрованным
    result = await db_session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == admin_user.company_id)
    )
    integration = result.scalar_one_or_none()
    assert integration is not None
    assert integration.access_token is not None
    assert integration.access_token != "real_habr_access_token"  # Fernet, не plain
    assert decrypt_text(integration.access_token) == "real_habr_access_token"
    assert decrypt_text(integration.refresh_token) == "real_habr_refresh_token"
    assert integration.expires_at is not None
    assert integration.connected_by_user_id == admin_user.id


@pytest.mark.asyncio
async def test_handle_callback_success_deletes_state(
    db_session, admin_user, valid_habr_state, fernet_key, habr_env
):
    """После успешного callback state должен быть удалён (одноразовый)."""
    from sqlalchemy import select

    token_response = {"access_token": "tok", "refresh_token": "ref"}

    with patch(
        "app.services.integrations.habr.service.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        # httpx Response.json() — синхронный: возвращает dict, НЕ корутину
        mock_resp.json = MagicMock(return_value=token_response)
        mock_client_cls.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_resp
        )
        await habr_service.handle_callback(db_session, "code", "valid_test_state_abc123")
        await db_session.commit()

    result = await db_session.execute(
        select(HabrOauthState).where(HabrOauthState.state == "valid_test_state_abc123")
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# (б) callback с битым/отсутствующим state → ValidationError (→ redirect habr=error)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_callback_invalid_state_raises_validation_error(db_session, habr_env):
    """(б) Несуществующий state → ValidationError."""
    with pytest.raises(ValidationError, match="Недействительный или истёкший state"):
        await habr_service.handle_callback(db_session, "some_code", "nonexistent_state")


@pytest.mark.asyncio
async def test_handle_callback_expired_state_raises_validation_error(
    db_session, admin_user, habr_env
):
    """(б) Истёкший state → ValidationError, запись удаляется."""
    from sqlalchemy import select

    expired_state = HabrOauthState(
        state="expired_state_xyz",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(expired_state)
    await db_session.commit()

    with pytest.raises(ValidationError, match="Недействительный или истёкший state"):
        await habr_service.handle_callback(db_session, "code", "expired_state_xyz")

    # Истёкший state должен быть удалён
    result = await db_session.execute(
        select(HabrOauthState).where(HabrOauthState.state == "expired_state_xyz")
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# (в) callback error=access_denied через HTTP API endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_endpoint_error_redirects_to_denied(
    async_client, auth_headers, db_session, admin_user, habr_env
):
    """(в) GET /habr/callback?error=access_denied → 302 habr=denied."""
    resp = await async_client.get(
        "/api/v1/integrations/habr/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "habr=denied" in location


@pytest.mark.asyncio
async def test_callback_endpoint_no_code_redirects_to_error(
    async_client, db_session, admin_user
):
    """(б) GET /habr/callback без code и state → 302 habr=error."""
    resp = await async_client.get(
        "/api/v1/integrations/habr/callback",
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert "habr=error" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_endpoint_invalid_state_redirects_to_error(
    async_client, db_session, admin_user
):
    """(б) GET /habr/callback с несуществующим state → 302 habr=error, НЕ 500."""
    resp = await async_client.get(
        "/api/v1/integrations/habr/callback",
        params={"code": "some_code", "state": "totally_invalid_state"},
        follow_redirects=False,
    )
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "habr=error" in location
    assert "habr=connected" not in location


# ---------------------------------------------------------------------------
# (г) token-обмен вернул 400 / без access_token → redirect habr=error, токен НЕ сохранён
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_endpoint_token_exchange_400_redirects_to_error(
    async_client, db_session, admin_user, fernet_key, habr_env
):
    """(г) Хабр вернул 400 при обмене кода → 302 habr=error, токен НЕ сохранён."""
    from sqlalchemy import select

    # Создаём валидный state
    state_obj = HabrOauthState(
        state="state_for_400_test",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=9),
    )
    db_session.add(state_obj)
    await db_session.commit()

    with patch(
        "app.services.integrations.habr.service.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"
        mock_resp.json.return_value = {"error": "invalid_grant"}
        mock_client_cls.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_resp
        )

        resp = await async_client.get(
            "/api/v1/integrations/habr/callback",
            params={"code": "bad_code", "state": "state_for_400_test"},
            follow_redirects=False,
        )

    assert resp.status_code == 307
    assert "habr=error" in resp.headers["location"]
    assert "habr=connected" not in resp.headers["location"]

    # Токен НЕ должен быть сохранён
    result = await db_session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == admin_user.company_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_callback_endpoint_no_access_token_in_response_redirects_to_error(
    async_client, db_session, admin_user, fernet_key, habr_env
):
    """(г) Хабр вернул 200 но без access_token → 302 habr=error, НЕ фейк-успех."""
    from sqlalchemy import select

    state_obj = HabrOauthState(
        state="state_no_token",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=9),
    )
    db_session.add(state_obj)
    await db_session.commit()

    with patch(
        "app.services.integrations.habr.service.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "ok"}  # нет access_token
        mock_client_cls.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_resp
        )

        resp = await async_client.get(
            "/api/v1/integrations/habr/callback",
            params={"code": "code", "state": "state_no_token"},
            follow_redirects=False,
        )

    assert resp.status_code == 307
    assert "habr=error" in resp.headers["location"]

    result = await db_session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == admin_user.company_id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# (д) company-изоляция: state компании A сохраняет токен только A
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_isolation_state_belongs_to_correct_company(
    db_session, admin_user, other_company, fernet_key, habr_env
):
    """(д) State компании A не может быть использован компанией B."""
    from sqlalchemy import select

    # State принадлежит admin_user.company_id (компания A)
    state_obj = HabrOauthState(
        state="state_company_a",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=9),
    )
    db_session.add(state_obj)
    await db_session.commit()

    token_response = {
        "access_token": "token_for_company_a",
        "refresh_token": "refresh_a",
    }

    with patch(
        "app.services.integrations.habr.service.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        # httpx Response.json() — синхронный: возвращает dict, НЕ корутину
        mock_resp.json = MagicMock(return_value=token_response)
        mock_client_cls.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_resp
        )

        company_id = await habr_service.handle_callback(db_session, "code", "state_company_a")
        await db_session.commit()

    # Токен сохранён ДЛЯ КОМПАНИИ A
    assert company_id == admin_user.company_id

    result_a = await db_session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == admin_user.company_id)
    )
    assert result_a.scalar_one_or_none() is not None

    # Компания B НЕ получила токен
    result_b = await db_session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == other_company.id)
    )
    assert result_b.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_not_connected_when_no_integration(db_session, admin_user):
    """Статус без интеграции → connected=False."""
    status = await habr_service.get_status(db_session, admin_user.company_id)
    assert status["connected"] is False
    assert status["habr_login"] is None


@pytest.mark.asyncio
async def test_get_status_connected_when_token_present(db_session, admin_user, fernet_key, habr_env):
    """Статус с токеном → connected=True."""
    from app.services.settings.crypto import encrypt_text as enc

    integration = HabrIntegration(
        company_id=admin_user.company_id,
        access_token=enc("some_access_token"),
        refresh_token=enc("some_refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(integration)
    await db_session.commit()

    status = await habr_service.get_status(db_session, admin_user.company_id)
    assert status["connected"] is True


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_nullifies_tokens(db_session, admin_user, fernet_key, habr_env):
    """disconnect обнуляет токены, запись остаётся."""
    from sqlalchemy import select
    from app.services.settings.crypto import encrypt_text as enc

    integration = HabrIntegration(
        company_id=admin_user.company_id,
        access_token=enc("tok"),
        refresh_token=enc("ref"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(integration)
    await db_session.commit()

    await habr_service.disconnect(db_session, admin_user.company_id)
    await db_session.commit()

    result = await db_session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == admin_user.company_id)
    )
    integration = result.scalar_one_or_none()
    assert integration is not None  # запись не удалена
    assert integration.access_token is None
    assert integration.refresh_token is None
    assert integration.expires_at is None


@pytest.mark.asyncio
async def test_disconnect_no_integration_no_error(db_session, admin_user):
    """disconnect без интеграции не падает."""
    await habr_service.disconnect(db_session, admin_user.company_id)


# ---------------------------------------------------------------------------
# RBAC: status → settings_read_access, authorize/disconnect → admin only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_habr_status_requires_auth(async_client):
    """GET /habr/status без авторизации → 401/403."""
    resp = await async_client.get("/api/v1/integrations/habr/status")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_habr_authorize_requires_admin(async_client, manager_headers, habr_env):
    """GET /habr/authorize для менеджера → 403."""
    resp = await async_client.get(
        "/api/v1/integrations/habr/authorize", headers=manager_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_habr_disconnect_requires_admin(async_client, manager_headers):
    """POST /habr/disconnect для менеджера → 403."""
    resp = await async_client.post(
        "/api/v1/integrations/habr/disconnect", headers=manager_headers
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Проверка что callback всегда возвращает redirect (не 500)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_endpoint_never_returns_500(async_client):
    """callback ВСЕГДА redirect даже при полном мусоре в параметрах."""
    resp = await async_client.get(
        "/api/v1/integrations/habr/callback",
        params={"code": "abc", "state": "invalid_state_xyz_!!@#"},
        follow_redirects=False,
    )
    # Никогда не 500
    assert resp.status_code != 500
    assert resp.status_code == 307


@pytest.mark.asyncio
async def test_callback_endpoint_is_public_no_auth_required(async_client):
    """callback НЕ требует авторизации — это публичный Redirect URI для Хабра."""
    # Без заголовков Authorization
    resp = await async_client.get(
        "/api/v1/integrations/habr/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    # 302 (не 401) — публичный
    assert resp.status_code == 307
