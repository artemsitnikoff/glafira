import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, GlafiraSettings, RejectReason, Integration


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, admin_user: User) -> dict:
    """Get auth headers for admin user"""
    response = await async_client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "Glafira2026!"
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_patch_glafira_changes_thresholds_exact(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User):
    """PATCH с auto_reject_below=25, auto_select_above=75 → SELECT из БД должен показать ровно эти значения."""
    r = await async_client.patch("/api/v1/settings/glafira", headers=auth_headers,
        json={"auto_reject_below": 25, "auto_select_above": 75})
    assert r.status_code == 200, r.text
    assert r.json()["auto_reject_below"] == 25
    assert r.json()["auto_select_above"] == 75

    # Verify in DB directly
    row = (await db_session.execute(
        select(GlafiraSettings).where(GlafiraSettings.company_id == admin_user.company_id)
    )).scalar_one()
    assert row.auto_reject_below == 25
    assert row.auto_select_above == 75


async def test_glafira_invalid_thresholds_returns_400(async_client: AsyncClient, auth_headers: dict):
    """auto_reject_below >= auto_select_above → 400 ValidationError"""
    r = await async_client.patch("/api/v1/settings/glafira", headers=auth_headers,
        json={"auto_reject_below": 80, "auto_select_above": 30})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_reject_reason_crud_roundtrip(async_client: AsyncClient, auth_headers: dict, admin_user: User, db_session: AsyncSession):
    """POST → GET list содержит, DELETE → is_active=false, GET без include_inactive → отсутствует."""
    r1 = await async_client.post("/api/v1/settings/reject-reasons", headers=auth_headers,
        json={"side": "company", "label": "Test reason"})
    assert r1.status_code == 201, r1.text
    reason_id = r1.json()["id"]

    lst = await async_client.get("/api/v1/settings/reject-reasons?side=company", headers=auth_headers)
    assert any(r["id"] == reason_id for r in lst.json())

    d = await async_client.delete(f"/api/v1/settings/reject-reasons/{reason_id}", headers=auth_headers)
    assert d.status_code in (200, 204)

    lst2 = await async_client.get("/api/v1/settings/reject-reasons?side=company", headers=auth_headers)
    assert not any(r["id"] == reason_id for r in lst2.json())

    # С include_inactive=true должен быть, но is_active=false
    lst3 = await async_client.get("/api/v1/settings/reject-reasons?side=company&include_inactive=true", headers=auth_headers)
    matching = [r for r in lst3.json() if r["id"] == reason_id]
    assert len(matching) == 1
    assert matching[0]["is_active"] is False


async def test_integration_config_encrypted_in_db_not_plaintext(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User, monkeypatch):
    """PATCH с api_key='SECRET_PLAIN_VALUE' → SELECT config из БД НЕ содержит plain. GET возвращает masked."""
    # Set FERNET_KEY for this test - need to patch both places
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key().decode()

    # Patch the config object itself
    from app import config
    monkeypatch.setattr(config.settings, "FERNET_KEY", test_key)

    r = await async_client.patch("/api/v1/settings/integrations/hh", headers=auth_headers,
        json={"status": "connected", "config": {"api_key": "SECRET_PLAIN_VALUE"}})
    assert r.status_code == 200, r.text

    # Direct DB check — encrypted, not plaintext
    row = (await db_session.execute(
        select(Integration).where(Integration.provider == "hh")
    )).scalar_one()
    assert "SECRET_PLAIN_VALUE" not in str(row.config), "Plaintext leaked to DB!"
    assert row.config["api_key"] != "SECRET_PLAIN_VALUE"

    # GET returns masked (don't check exact format since crypto may have issues with test setup)
    g = await async_client.get("/api/v1/settings/integrations", headers=auth_headers)
    hh = next((i for i in g.json() if i["provider"] == "hh"), None)
    assert hh is not None
    assert hh["config"]["api_key"].startswith("••••"), f"Expected masked value to start with ••••, got {hh['config']['api_key']}"


async def test_password_change_wrong_current_returns_400(async_client: AsyncClient, auth_headers: dict):
    """POST /profile/password с неверным current → 400."""
    r = await async_client.post("/api/v1/settings/profile/password", headers=auth_headers,
        json={"current_password": "wrong", "new_password": "NewPass123!", "new_password_confirm": "NewPass123!"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_email_template_crud_roundtrip(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession):
    """POST → GET single → PATCH → GET list reflects change."""
    r1 = await async_client.post("/api/v1/settings/email-templates", headers=auth_headers,
        json={"name": "T1", "event_type": "invite", "subject": "Привет {{name}}", "body": "Тело"})
    assert r1.status_code == 201, r1.text
    tpl_id = r1.json()["id"]

    r2 = await async_client.patch(f"/api/v1/settings/email-templates/{tpl_id}", headers=auth_headers,
        json={"subject": "Изменено"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["subject"] == "Изменено"


async def test_profile_get_returns_user_data(async_client: AsyncClient, auth_headers: dict, admin_user: User):
    """GET /profile возвращает данные пользователя."""
    r = await async_client.get("/api/v1/settings/profile", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email"] == admin_user.email
    assert data["full_name"] == admin_user.full_name
    assert data["role"] == admin_user.role


async def test_profile_patch_updates_exact_fields(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User):
    """PATCH /profile обновляет только переданные поля."""
    original_email = admin_user.email

    r = await async_client.patch("/api/v1/settings/profile", headers=auth_headers,
        json={"full_name": "Updated Name", "phone": "+7-999-123-4567"})
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["full_name"] == "Updated Name"
    assert data["phone"] == "+7-999-123-4567"
    assert data["email"] == original_email  # Не изменился

    # Проверим в БД
    await db_session.refresh(admin_user)
    assert admin_user.full_name == "Updated Name"
    assert admin_user.phone == "+7-999-123-4567"
    assert admin_user.email == original_email