"""Тесты персонального hh-токена рекрутёра (Фаза 1: фундамент).

Покрывают:
- персональный OAuth-callback (kind='personal') пишет в user_hh_integrations
  (company-scoped), НЕ в hh_integrations;
- селектор get_hh_token_for_user: свой токен приоритетнее общего;
- ФОЛБЭК на общий компанийный токен, когда своего нет;
- company-изоляция персонального токена (§2.3);
- рефреш персонального токена под FOR UPDATE;
- RBAC: manager/hiring_manager → 403 на authorize/me, recruiter проходит;
- DELETE персонального токена → далее фолбэк на общий;
- company-флоу (kind='company') НЕ сломан — пишет в hh_integrations.
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.security import get_password_hash
from app.services.integrations.hh import service as hh_service
from app.services.settings.crypto import encrypt_text, decrypt_text
from app.core.errors import ValidationError, NotFoundError
from app.models import HhIntegration, HhOauthState, UserHhIntegration, User, AuditLog


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture
def fernet_key(monkeypatch):
    """FERNET_KEY для шифрования токенов в тестах."""
    test_key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.FERNET_KEY", test_key)
    return test_key


@pytest.fixture(autouse=True)
def clear_hh_env(monkeypatch):
    """Пустой ключ приложения в env — детерминизм (на VPS тест-контейнер видит прод-.env)."""
    monkeypatch.setattr("app.config.settings.HH_CLIENT_ID", "")
    monkeypatch.setattr("app.config.settings.HH_CLIENT_SECRET", "")
    monkeypatch.setattr("app.config.settings.HH_REDIRECT_URI", "")


@pytest.fixture
def mock_hh_config(monkeypatch):
    """Ключ приложения Глафиры из env (prod-путь) — чтобы OAuth не требовал company-строки."""
    monkeypatch.setattr("app.config.settings.HH_CLIENT_ID", "test_client_id")
    monkeypatch.setattr("app.config.settings.HH_CLIENT_SECRET", "test_client_secret")
    monkeypatch.setattr("app.config.settings.HH_REDIRECT_URI", "https://test.com/callback")


@pytest_asyncio.fixture
async def hiring_manager_user(db_session, admin_user) -> User:
    user = User(
        company_id=admin_user.company_id,
        email="hm.personal@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Нанимающий Менеджер",
        role="hiring_manager",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def second_company_user(db_session, second_company) -> User:
    """Пользователь второй компании (для теста изоляции)."""
    user = User(
        company_id=second_company.id,
        email="user.companyB@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Юзер Компании Б",
        role="recruiter",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_personal(db_session, company_id, user_id, *,
                         access="personal_access", refresh="personal_refresh",
                         minutes=60, employer="777", manager="42") -> UserHhIntegration:
    integ = UserHhIntegration(
        company_id=company_id,
        user_id=user_id,
        access_token=encrypt_text(access),
        refresh_token=encrypt_text(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        hh_employer_id=employer,
        hh_manager_id=manager,
        connected_at=datetime.now(timezone.utc),
    )
    db_session.add(integ)
    await db_session.commit()
    await db_session.refresh(integ)
    return integ


async def _make_company(db_session, company_id, *,
                        access="company_access", refresh="company_refresh", minutes=60,
                        employer="123456"):
    integ = HhIntegration(
        company_id=company_id,
        client_id="test_client_id",
        client_secret=encrypt_text("test_client_secret"),
        redirect_uri="https://test.com/callback",
        access_token=encrypt_text(access),
        refresh_token=encrypt_text(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        hh_employer_id=employer,
    )
    db_session.add(integ)
    await db_session.commit()
    await db_session.refresh(integ)
    return integ


# ---------------------------------------------------------------------------
# 1. Персональный callback пишет в user_hh_integrations, company-scoped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_oauth_personal_writes_user_integration(
    db_session, admin_user, fernet_key, mock_hh_config
):
    # Общий hh компании ДОЛЖЕН быть подключён и с ТЕМ ЖЕ employer (555) — гард работодателя.
    await _make_company(db_session, admin_user.company_id, employer="555", access="COMPANY_KEEP")

    oauth_state = HhOauthState(
        state="personal_state_1",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        kind="personal",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(oauth_state)
    await db_session.commit()

    token_resp = {
        "access_token": "acc_personal", "refresh_token": "ref_personal",
        "token_type": "bearer", "expires_in": 3600,
    }
    me_resp = {"id": "9001", "employer": {"id": "555"}, "manager": {"id": "42"}}

    with patch("app.services.integrations.hh.service.hh_client") as mock_client:
        mock_client.exchange_code = AsyncMock(return_value=token_resp)
        mock_client.get_me = AsyncMock(return_value=me_resp)

        result = await hh_service.complete_oauth(db_session, "code_1", "personal_state_1")

    assert isinstance(result, UserHhIntegration)
    assert result.user_id == admin_user.id
    assert result.company_id == admin_user.company_id
    assert result.hh_employer_id == "555"
    assert result.hh_manager_id == "42"
    # Токены зашифрованы, но расшифровываются корректно
    assert result.access_token != "acc_personal"
    assert decrypt_text(result.access_token) == "acc_personal"
    assert decrypt_text(result.refresh_token) == "ref_personal"

    # Строка реально в user_hh_integrations, company-scoped
    row = (await db_session.execute(
        select(UserHhIntegration).where(UserHhIntegration.user_id == admin_user.id)
    )).scalar_one_or_none()
    assert row is not None
    assert row.company_id == admin_user.company_id

    # Персональный флоу НЕ трогает общую компанийную строку hh_integrations (она осталась
    # той же — токен не перезаписан персональным).
    company_row = (await db_session.execute(
        select(HhIntegration).where(HhIntegration.company_id == admin_user.company_id)
    )).scalar_one_or_none()
    assert company_row is not None
    assert company_row.hh_employer_id == "555"
    assert decrypt_text(company_row.access_token) == "COMPANY_KEEP"

    # State использован (удалён)
    state_row = (await db_session.execute(
        select(HhOauthState).where(HhOauthState.state == "personal_state_1")
    )).scalar_one_or_none()
    assert state_row is None

    # Аудит connect (§2.2): action + actor + company + entity_type
    audit_row = (await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "hh_personal_connected",
            AuditLog.company_id == admin_user.company_id,
        )
    )).scalar_one_or_none()
    assert audit_row is not None
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.entity_type == "user_hh_integration"
    assert audit_row.entity_id == result.id


# ---------------------------------------------------------------------------
# 2. Селектор: свой токен приоритетнее общего
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_hh_token_for_user_prefers_personal(db_session, admin_user, fernet_key):
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    await _make_personal(db_session, admin_user.company_id, admin_user.id, access="PERSONAL_TOK")

    token = await hh_service.get_hh_token_for_user(
        db_session, company_id=admin_user.company_id, user_id=admin_user.id
    )
    assert token == "PERSONAL_TOK"


# ---------------------------------------------------------------------------
# 3. ФОЛБЭК на общий токен, когда персонального нет
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_hh_token_for_user_falls_back_to_company(db_session, admin_user, fernet_key):
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    # Персонального токена НЕТ

    token = await hh_service.get_hh_token_for_user(
        db_session, company_id=admin_user.company_id, user_id=admin_user.id
    )
    assert token == "COMPANY_TOK"


# ---------------------------------------------------------------------------
# 4. Ни своего, ни общего → None (не исключение)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_hh_token_for_user_none_when_neither(db_session, admin_user, fernet_key):
    token = await hh_service.get_hh_token_for_user(
        db_session, company_id=admin_user.company_id, user_id=admin_user.id
    )
    assert token is None


# ---------------------------------------------------------------------------
# 4b. user_id=None (фон/крон/нет инициатора) → ОБЩИЙ токен, персональный НЕ ищем
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_hh_token_for_user_none_userid_returns_company(db_session, admin_user, fernet_key):
    """Фаза 2: селектор с user_id=None короткозамыкается на общий компанийный токен,
    даже если у пользователя ЕСТЬ персональный (личный ищется только при заданном user_id).
    Это гарантирует, что фон/кроны/вызовы без инициатора остаются на общем токене."""
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    # У пользователя ЕСТЬ личный токен, но инициатора нет (user_id=None)
    await _make_personal(db_session, admin_user.company_id, admin_user.id, access="PERSONAL_TOK")

    token = await hh_service.get_hh_token_for_user(
        db_session, company_id=admin_user.company_id, user_id=None
    )
    assert token == "COMPANY_TOK"

    # И дефолт (без user_id вовсе) ведёт себя так же — общий токен.
    token_default = await hh_service.get_hh_token_for_user(
        db_session, company_id=admin_user.company_id
    )
    assert token_default == "COMPANY_TOK"


# ---------------------------------------------------------------------------
# 5. Company-изоляция персонального токена (§2.3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_personal_token_company_isolation(
    db_session, admin_user, fernet_key, second_company, second_company_user
):
    # Персональный токен пользователя компании A
    await _make_personal(db_session, admin_user.company_id, admin_user.id, access="A_PERSONAL")

    # Запрос ТЕМ ЖЕ user_id, но company_id компании B → не виден (WHERE scoped по обоим)
    leaked = await hh_service.get_user_integration(
        db_session, second_company.id, admin_user.id
    )
    assert leaked is None

    # Селектор для пользователя компании B (своего нет, общего у B нет) → None,
    # а НЕ персональный токен компании A
    token_b = await hh_service.get_hh_token_for_user(
        db_session, company_id=second_company.id, user_id=second_company_user.id
    )
    assert token_b is None


# ---------------------------------------------------------------------------
# 6. Рефреш персонального токена (протух → обновился)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_personal_token_refresh_when_expired(db_session, admin_user, fernet_key):
    # Для creds рефреша нужен ключ приложения: env пуст (clear_hh_env) → берём из
    # legacy DB-колонок компанийной интеграции.
    await _make_company(db_session, admin_user.company_id)
    # Персональный токен истекает через 2 минуты (< 5-минутного запаса) → рефреш
    integ = await _make_personal(
        db_session, admin_user.company_id, admin_user.id,
        access="old_personal_access", refresh="old_personal_refresh", minutes=2,
    )

    refresh_resp = {
        "access_token": "new_personal_access", "refresh_token": "new_personal_refresh",
        "token_type": "bearer", "expires_in": 3600,
    }
    with patch("app.services.integrations.hh.service.hh_client") as mock_client:
        mock_client.refresh_tokens = AsyncMock(return_value=refresh_resp)

        token = await hh_service.get_hh_token_for_user(
            db_session, company_id=admin_user.company_id, user_id=admin_user.id
        )
        assert token == "new_personal_access"
        mock_client.refresh_tokens.assert_called_once_with(
            "old_personal_refresh", "test_client_id", "test_client_secret"
        )

    await db_session.refresh(integ)
    assert decrypt_text(integ.access_token) == "new_personal_access"
    assert decrypt_text(integ.refresh_token) == "new_personal_refresh"


# ---------------------------------------------------------------------------
# 7. DELETE персонального токена → далее фолбэк на общий
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_personal_then_fallback(db_session, admin_user, fernet_key):
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    await _make_personal(db_session, admin_user.company_id, admin_user.id, access="PERSONAL_TOK")

    # До отключения — свой токен
    assert await hh_service.get_hh_token_for_user(
        db_session, company_id=admin_user.company_id, user_id=admin_user.id
    ) == "PERSONAL_TOK"

    await hh_service.disconnect_personal(db_session, admin_user.company_id, admin_user.id)

    # Строка удалена
    assert (await db_session.execute(
        select(UserHhIntegration).where(UserHhIntegration.user_id == admin_user.id)
    )).scalar_one_or_none() is None

    # Теперь — фолбэк на общий
    assert await hh_service.get_hh_token_for_user(
        db_session, company_id=admin_user.company_id, user_id=admin_user.id
    ) == "COMPANY_TOK"


@pytest.mark.asyncio
async def test_disconnect_personal_not_found_raises(db_session, admin_user, fernet_key):
    with pytest.raises(NotFoundError):
        await hh_service.disconnect_personal(db_session, admin_user.company_id, admin_user.id)


# ---------------------------------------------------------------------------
# 8. Company-флоу НЕ сломан: kind='company' пишет в hh_integrations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_flow_not_broken(db_session, admin_user, fernet_key, mock_hh_config):
    oauth_state = HhOauthState(
        state="company_state_1",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        kind="company",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(oauth_state)
    await db_session.commit()

    token_resp = {
        "access_token": "acc_company", "refresh_token": "ref_company",
        "token_type": "bearer", "expires_in": 3600,
    }
    me_resp = {"employer": {"id": "999"}}

    with patch("app.services.integrations.hh.service.hh_client") as mock_client:
        mock_client.exchange_code = AsyncMock(return_value=token_resp)
        mock_client.get_me = AsyncMock(return_value=me_resp)

        result = await hh_service.complete_oauth(db_session, "code_c", "company_state_1")

    # Company-строка создана в hh_integrations
    assert isinstance(result, HhIntegration)
    assert result.company_id == admin_user.company_id
    assert result.hh_employer_id == "999"
    assert decrypt_text(result.access_token) == "acc_company"

    # Персональной строки НЕ появилось
    personal_row = (await db_session.execute(
        select(UserHhIntegration).where(UserHhIntegration.company_id == admin_user.company_id)
    )).scalar_one_or_none()
    assert personal_row is None


# ---------------------------------------------------------------------------
# 9. RBAC на GET /integrations/hh/authorize/me
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authorize_me_manager_forbidden(async_client, manager_headers):
    resp = await async_client.get("/api/v1/integrations/hh/authorize/me", headers=manager_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_authorize_me_hiring_manager_forbidden(async_client, hiring_manager_user):
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": hiring_manager_user.email, "password": "Glafira2026!"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await async_client.get("/api/v1/integrations/hh/authorize/me", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_authorize_me_recruiter_allowed(
    async_client, db_session, regular_user, fernet_key, mock_hh_config
):
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": regular_user.email, "password": "Glafira2026!"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    with patch("app.services.integrations.hh.service.hh_client") as mock_client:
        mock_client.build_authorize_url.return_value = "https://hh.ru/oauth/authorize?state=x"
        resp = await async_client.get("/api/v1/integrations/hh/authorize/me", headers=headers)

    assert resp.status_code == 200, resp.text
    assert "authorize_url" in resp.json()

    # Персональный state создан с kind='personal' и user_id рекрутёра
    state_row = (await db_session.execute(
        select(HhOauthState).where(HhOauthState.company_id == regular_user.company_id)
    )).scalar_one_or_none()
    assert state_row is not None
    assert state_row.kind == "personal"
    assert state_row.user_id == regular_user.id


# ---------------------------------------------------------------------------
# 10. API: DELETE /hh/me и GET /hh/me/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_personal_status_and_disconnect_api(
    async_client, db_session, regular_user, fernet_key
):
    await _make_personal(db_session, regular_user.company_id, regular_user.id, access="RECR_TOK")

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": regular_user.email, "password": "Glafira2026!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    status = await async_client.get("/api/v1/integrations/hh/me/status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["connected"] is True

    disc = await async_client.delete("/api/v1/integrations/hh/me", headers=headers)
    assert disc.status_code == 200, disc.text

    row = (await db_session.execute(
        select(UserHhIntegration).where(UserHhIntegration.user_id == regular_user.id)
    )).scalar_one_or_none()
    assert row is None

    status2 = await async_client.get("/api/v1/integrations/hh/me/status", headers=headers)
    assert status2.status_code == 200
    assert status2.json()["connected"] is False


# ---------------------------------------------------------------------------
# 11. Гард работодателя: личный аккаунт должен быть тем же employer, что и общий
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_oauth_personal_wrong_employer_rejected(
    db_session, admin_user, fernet_key, mock_hh_config
):
    """Личный аккаунт под ЧУЖИМ employer (999 ≠ 555 у общего) → ValidationError,
    строка user_hh_integrations НЕ пишется, state погашен."""
    await _make_company(db_session, admin_user.company_id, employer="555")

    oauth_state = HhOauthState(
        state="wrong_emp_state",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        kind="personal",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(oauth_state)
    await db_session.commit()

    token_resp = {"access_token": "a", "refresh_token": "r",
                  "token_type": "bearer", "expires_in": 3600}
    me_resp = {"id": "9002", "employer": {"id": "999"}, "manager": {"id": "7"}}

    with patch("app.services.integrations.hh.service.hh_client") as mock_client:
        mock_client.exchange_code = AsyncMock(return_value=token_resp)
        mock_client.get_me = AsyncMock(return_value=me_resp)
        with pytest.raises(ValidationError) as ei:
            await hh_service.complete_oauth(db_session, "code_x", "wrong_emp_state")

    assert "другому работодателю" in str(ei.value)

    row = (await db_session.execute(
        select(UserHhIntegration).where(UserHhIntegration.user_id == admin_user.id)
    )).scalar_one_or_none()
    assert row is None  # строка НЕ создана

    st = (await db_session.execute(
        select(HhOauthState).where(HhOauthState.state == "wrong_emp_state")
    )).scalar_one_or_none()
    assert st is None  # state погашен


@pytest.mark.asyncio
async def test_complete_oauth_personal_no_company_hh_rejected(
    db_session, admin_user, fernet_key, mock_hh_config
):
    """Общий hh компании НЕ подключён → личное подключение отклоняется (нет эталона employer)."""
    oauth_state = HhOauthState(
        state="no_company_state",
        company_id=admin_user.company_id,
        user_id=admin_user.id,
        kind="personal",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(oauth_state)
    await db_session.commit()

    token_resp = {"access_token": "a", "refresh_token": "r",
                  "token_type": "bearer", "expires_in": 3600}
    me_resp = {"id": "9003", "employer": {"id": "555"}}

    with patch("app.services.integrations.hh.service.hh_client") as mock_client:
        mock_client.exchange_code = AsyncMock(return_value=token_resp)
        mock_client.get_me = AsyncMock(return_value=me_resp)
        with pytest.raises(ValidationError) as ei:
            await hh_service.complete_oauth(db_session, "code_y", "no_company_state")

    assert "подключите общий аккаунт hh" in str(ei.value).lower()

    row = (await db_session.execute(
        select(UserHhIntegration).where(UserHhIntegration.user_id == admin_user.id)
    )).scalar_one_or_none()
    assert row is None


# ---------------------------------------------------------------------------
# 12. Аудит отключения персонального токена
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_personal_writes_audit(db_session, admin_user, fernet_key):
    integ = await _make_personal(db_session, admin_user.company_id, admin_user.id)
    integ_id = integ.id

    await hh_service.disconnect_personal(db_session, admin_user.company_id, admin_user.id)

    audit_row = (await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "hh_personal_disconnected",
            AuditLog.company_id == admin_user.company_id,
        )
    )).scalar_one_or_none()
    assert audit_row is not None
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.entity_type == "user_hh_integration"
    assert audit_row.entity_id == integ_id


# ---------------------------------------------------------------------------
# 13. Сбой рефреша ЛИЧНОГО токена ПРОБРАСЫВАЕТСЯ (не молчаливый уход на общий)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_personal_refresh_failure_propagates(db_session, admin_user, fernet_key):
    """Личный токен истёк, refresh_tokens падает, а валидный ОБЩИЙ токен ЕСТЬ →
    get_hh_token_for_user поднимает ValidationError (НЕ возвращает общий токен молча —
    иначе вернулась бы та же проблема с личным аккаунтом рекрутёра)."""
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    await _make_personal(
        db_session, admin_user.company_id, admin_user.id, minutes=2,
        access="old_p", refresh="old_p_ref",
    )

    with patch("app.services.integrations.hh.service.hh_client") as mock_client:
        mock_client.refresh_tokens = AsyncMock(side_effect=RuntimeError("hh 400 token invalid"))
        with pytest.raises(ValidationError) as ei:
            await hh_service.get_hh_token_for_user(
                db_session, company_id=admin_user.company_id, user_id=admin_user.id
            )

    assert "персональный токен" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# 14. Гонка: строку удалил конкурентный disconnect во время рефреша → None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_valid_personal_token_none_on_concurrent_disconnect(
    db_session, admin_user, fernet_key
):
    """Строку user_hh_integrations удалил конкурентный disconnect_personal между чтением
    и рефрешем → session.refresh(with_for_update) падает StaleDataError → _get_valid_personal_token
    возвращает None (get_hh_token_for_user чисто уйдёт на общий токен), не роняя исключение."""
    from sqlalchemy.orm.exc import StaleDataError

    await _make_personal(
        db_session, admin_user.company_id, admin_user.id, minutes=2,  # near-expiry → путь рефреша
    )

    with patch.object(db_session, "refresh", new_callable=AsyncMock,
                      side_effect=StaleDataError("row vanished")):
        token = await hh_service._get_valid_personal_token(
            db_session, admin_user.company_id, admin_user.id
        )
    assert token is None


# ---------------------------------------------------------------------------
# 15. Каскад квоты просмотров: личный исчерпан → добор из общего
# ---------------------------------------------------------------------------

_SVC_RESUME = "app.services.integrations.hh.service.hh_client.get_resume_by_id"


@pytest.mark.asyncio
async def test_view_cascade_spills_to_company_on_personal_limit(
    db_session, admin_user, fernet_key
):
    """Лимит просмотров на ЛИЧНОМ токене → повтор на ОБЩЕМ + daily_view_exhausted_at
    выставлен + audit-спилл записан."""
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    integ = await _make_personal(db_session, admin_user.company_id, admin_user.id, access="PERSONAL_TOK")

    m = AsyncMock(side_effect=[
        ValidationError("Превышена квота просмотров резюме hh.ru"),  # личный токен
        {"id": "r1", "owner": {"id": 1}},                            # общий токен
    ])
    with patch(_SVC_RESUME, m):
        result = await hh_service.view_resume_with_cascade(
            db_session, company_id=admin_user.company_id, user_id=admin_user.id, resume_id="r1"
        )

    assert result == {"id": "r1", "owner": {"id": 1}}
    assert m.await_count == 2
    assert m.await_args_list[0].args[0] == "PERSONAL_TOK"  # сначала личным
    assert m.await_args_list[1].args[0] == "COMPANY_TOK"   # добор общим

    await db_session.refresh(integ)
    assert integ.daily_view_exhausted_at is not None

    audit_row = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "hh_personal_view_quota_spill")
    )).scalar_one_or_none()
    assert audit_row is not None
    assert audit_row.actor_user_id == admin_user.id
    assert audit_row.company_id == admin_user.company_id
    assert audit_row.entity_type == "user_hh_integration"


@pytest.mark.asyncio
async def test_view_cascade_both_exhausted_raises(db_session, admin_user, fernet_key):
    """Лимит и на личном, и на общем → чистая ValidationError, без фейкового результата."""
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    await _make_personal(db_session, admin_user.company_id, admin_user.id, access="PERSONAL_TOK")

    m = AsyncMock(side_effect=[
        ValidationError("Превышена квота просмотров резюме hh.ru"),
        ValidationError("Превышена квота просмотров резюме hh.ru"),
    ])
    with patch(_SVC_RESUME, m):
        with pytest.raises(ValidationError) as ei:
            await hh_service.view_resume_with_cascade(
                db_session, company_id=admin_user.company_id, user_id=admin_user.id, resume_id="r1"
            )
    assert "и на личном, и на общем" in str(ei.value)
    assert m.await_count == 2


@pytest.mark.asyncio
async def test_view_cascade_non_limit_error_propagates(db_session, admin_user, fernet_key):
    """НЕ-лимитный сбой (403 нет доступа) на личном токене → пробрасывается, НЕ повторяется
    на общем и НЕ помечает квоту исчерпанной (это не квота, а отсутствие доступа)."""
    await _make_company(db_session, admin_user.company_id, access="COMPANY_TOK")
    integ = await _make_personal(db_session, admin_user.company_id, admin_user.id, access="PERSONAL_TOK")

    m = AsyncMock(side_effect=ValidationError(
        "Ошибка получения резюме hh.ru: Client error '403 Forbidden'"
    ))
    with patch(_SVC_RESUME, m):
        with pytest.raises(ValidationError) as ei:
            await hh_service.view_resume_with_cascade(
                db_session, company_id=admin_user.company_id, user_id=admin_user.id, resume_id="r1"
            )
    assert "403" in str(ei.value)          # исходная ошибка, НЕ «дневной лимит»
    assert m.await_count == 1              # на общем токене НЕ повторяли
    await db_session.refresh(integ)
    assert integ.daily_view_exhausted_at is None  # квота НЕ помечена исчерпанной
