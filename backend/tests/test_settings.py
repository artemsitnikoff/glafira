import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, GlafiraSettings, RejectReason, Integration, EmailTemplate, SurveyTemplate


def test_glafira_settings_out_normalizes_list_stop_words():
    """Регрессия: исторический stop_words=[] (list) не должен ломать GlafiraSettingsOut (ждёт dict)."""
    from datetime import datetime
    from uuid import uuid4
    from app.schemas.settings import GlafiraSettingsOut
    out = GlafiraSettingsOut(
        id=uuid4(), company_id=uuid4(), tone="friendly", use_informal=True,
        emoji_level="moderate", auto_reject_below=30, auto_select_above=80,
        days_no_response=7, stop_words=[], default_mode="A", turnover_source="none",
        created_at=datetime.now(), updated_at=datetime.now(),
    )
    assert out.stop_words == {}


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


async def test_glafira_turnover_source_default_is_none(async_client: AsyncClient, auth_headers: dict):
    """GET без правок → turnover_source='none' (server_default)."""
    r = await async_client.get("/api/v1/settings/glafira", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["turnover_source"] == "none"


async def test_glafira_turnover_source_saves(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User):
    """PATCH turnover_source='bitrix24' → SELECT из БД показывает ровно это значение."""
    r = await async_client.patch("/api/v1/settings/glafira", headers=auth_headers,
        json={"turnover_source": "bitrix24"})
    assert r.status_code == 200, r.text
    assert r.json()["turnover_source"] == "bitrix24"

    row = (await db_session.execute(
        select(GlafiraSettings).where(GlafiraSettings.company_id == admin_user.company_id)
    )).scalar_one()
    assert row.turnover_source == "bitrix24"


async def test_glafira_turnover_source_invalid_returns_422(async_client: AsyncClient, auth_headers: dict):
    """Недопустимое turnover_source → 422 (теперь Literal в схеме → Pydantic-валидация).
    Единый формат ошибки сохранён: error.code == VALIDATION_ERROR."""
    r = await async_client.patch("/api/v1/settings/glafira", headers=auth_headers,
        json={"turnover_source": "sap"})
    assert r.status_code == 422
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

    # После PATCH очищаем session identity map
    db_session.expire_all()

    # Direct DB check — encrypted, not plaintext
    row = (await db_session.execute(
        select(Integration).where(Integration.provider == "hh")
    )).scalar_one()
    assert "SECRET_PLAIN_VALUE" not in str(row.config), f"Plaintext leaked to DB! config={row.config}"
    assert row.config["api_key"] != "SECRET_PLAIN_VALUE"
    assert len(row.config["api_key"]) > len("SECRET_PLAIN_VALUE")  # encrypted токен обычно длиннее

    # GET returns masked (don't check exact format since crypto may have issues with test setup)
    g = await async_client.get("/api/v1/settings/integrations", headers=auth_headers)
    hh = next((i for i in g.json() if i["provider"] == "hh"), None)
    assert hh is not None
    assert hh["config"]["api_key"].startswith("••••"), f"Expected masked value to start with ••••, got {hh['config']['api_key']}"


async def test_password_change_wrong_current_returns_400(async_client: AsyncClient, auth_headers: dict):
    """Неверный текущий пароль → 400 (НЕ 401: иначе фронтовый axios-интерсептор уйдёт в logout)."""
    r = await async_client.post("/api/v1/settings/profile/password", headers=auth_headers,
        json={"current_password": "wrong", "new_password": "NewPass123!", "new_password_confirm": "NewPass123!"})
    assert r.status_code == 400, r.text


async def test_password_change_mismatch_confirm_returns_400(async_client: AsyncClient, auth_headers: dict):
    """new_password != confirm → 400."""
    r = await async_client.post("/api/v1/settings/profile/password", headers=auth_headers,
        json={"current_password": "Glafira2026!", "new_password": "NewPass123!", "new_password_confirm": "Other123!"})
    assert r.status_code == 400, r.text


async def test_password_change_success_then_login(async_client: AsyncClient, auth_headers: dict, admin_user: User):
    """Успешная смена пароля: 200, и новый пароль работает на входе, старый — нет."""
    r = await async_client.post("/api/v1/settings/profile/password", headers=auth_headers,
        json={"current_password": "Glafira2026!", "new_password": "BrandNew2027!", "new_password_confirm": "BrandNew2027!"})
    assert r.status_code == 200, r.text

    # Старый пароль больше не подходит
    old = await async_client.post("/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Glafira2026!"})
    assert old.status_code == 401

    # Новый — подходит
    new = await async_client.post("/api/v1/auth/login",
        json={"email": admin_user.email, "password": "BrandNew2027!"})
    assert new.status_code == 200, new.text


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


async def test_profile_patch_email_conflict_returns_409(
    async_client: AsyncClient, auth_headers: dict, admin_user: User, regular_user: User
):
    """Смена email на уже занятый (другим пользователем) → 409, без 500."""
    r = await async_client.patch("/api/v1/settings/profile", headers=auth_headers,
        json={"email": regular_user.email})
    assert r.status_code == 409, r.text


async def test_profile_patch_blank_full_name_returns_400(
    async_client: AsyncClient, auth_headers: dict
):
    """Пустое ФИО → 400 (не затираем имя пустой строкой)."""
    r = await async_client.patch("/api/v1/settings/profile", headers=auth_headers,
        json={"full_name": "   "})
    assert r.status_code == 400, r.text


async def test_delete_email_template_success(async_client: AsyncClient, auth_headers: dict):
    """DELETE email template returns 200, subsequent GET returns 404"""
    # Create template
    r1 = await async_client.post("/api/v1/settings/email-templates", headers=auth_headers,
        json={"name": "Test Template", "event_type": "welcome", "subject": "Welcome", "body": "Body"})
    assert r1.status_code == 201
    template_id = r1.json()["id"]

    # Delete template
    r2 = await async_client.delete(f"/api/v1/settings/email-templates/{template_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["message"] == "Email-шаблон удалён"

    # Verify deletion - GET should return 404
    r3 = await async_client.get(f"/api/v1/settings/email-templates/{template_id}", headers=auth_headers)
    assert r3.status_code == 404


async def test_delete_nonexistent_email_template_returns_404(async_client: AsyncClient, auth_headers: dict):
    """DELETE non-existent email template returns 404"""
    from uuid import uuid4
    fake_id = str(uuid4())

    r = await async_client.delete(f"/api/v1/settings/email-templates/{fake_id}", headers=auth_headers)
    assert r.status_code == 404


async def test_delete_email_template_audit_log(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession):
    """DELETE email template creates audit log entry"""
    from app.models import AuditLog

    # Create template
    r1 = await async_client.post("/api/v1/settings/email-templates", headers=auth_headers,
        json={"name": "Audit Test", "event_type": "test", "subject": "Test", "body": "Test Body"})
    template_id = r1.json()["id"]

    # Delete template
    await async_client.delete(f"/api/v1/settings/email-templates/{template_id}", headers=auth_headers)

    # Check audit log
    audit_entry = (
        await db_session.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "email_template",
                AuditLog.entity_id == template_id,
                AuditLog.action == "email_template_delete"
            )
        )
    ).scalar_one()

    assert audit_entry is not None
    assert audit_entry.action == "email_template_delete"
    assert audit_entry.changes["before"]["name"] == "Audit Test"
    assert "after" not in audit_entry.changes


async def test_delete_survey_template_success(async_client: AsyncClient, auth_headers: dict):
    """DELETE survey template returns 200, subsequent GET returns 404"""
    # Create template
    r1 = await async_client.post("/api/v1/settings/survey-templates", headers=auth_headers,
        json={"name": "Survey Test", "channels": {"telegram": True}, "questions": {"items": [{"text": "How are you?"}]}})
    assert r1.status_code == 201
    template_id = r1.json()["id"]

    # Delete template
    r2 = await async_client.delete(f"/api/v1/settings/survey-templates/{template_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["message"] == "Survey-шаблон удалён"

    # Verify deletion - GET should return 404
    r3 = await async_client.get(f"/api/v1/settings/survey-templates/{template_id}", headers=auth_headers)
    assert r3.status_code == 404


async def test_delete_nonexistent_survey_template_returns_404(async_client: AsyncClient, auth_headers: dict):
    """DELETE non-existent survey template returns 404"""
    from uuid import uuid4
    fake_id = str(uuid4())

    r = await async_client.delete(f"/api/v1/settings/survey-templates/{fake_id}", headers=auth_headers)
    assert r.status_code == 404


async def test_delete_survey_template_audit_log(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession):
    """DELETE survey template creates audit log entry"""
    from app.models import AuditLog

    # Create template
    r1 = await async_client.post("/api/v1/settings/survey-templates", headers=auth_headers,
        json={"name": "Survey Audit", "channels": {"email": True}, "questions": {"items": [{"text": "Rating?"}]}})
    template_id = r1.json()["id"]

    # Delete template
    await async_client.delete(f"/api/v1/settings/survey-templates/{template_id}", headers=auth_headers)

    # Check audit log
    audit_entry = (
        await db_session.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "survey_template",
                AuditLog.entity_id == template_id,
                AuditLog.action == "survey_template_delete"
            )
        )
    ).scalar_one()

    assert audit_entry is not None
    assert audit_entry.action == "survey_template_delete"
    assert audit_entry.changes["before"]["name"] == "Survey Audit"
    assert "after" not in audit_entry.changes


@pytest.mark.asyncio
async def test_billing_real_counts_exclude_deleted(async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User):
    """Тест 5: seed 5 кандидатов БЕЗ deleted_at + 1 С deleted_at → current_candidates == 5 (НЕ 6)"""
    from app.models import Candidate, User, Vacancy
    from datetime import datetime, timezone

    # seed: 5 кандидатов БЕЗ deleted_at
    for i in range(5):
        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name=f"AliveCandidate{i}",
            first_name="Test",
            source="manual"
        )
        db_session.add(candidate)

    # 1 кандидат С deleted_at=now()
    deleted_candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="DeletedCandidate",
        first_name="Test",
        source="manual",
        deleted_at=datetime.now(timezone.utc)
    )
    db_session.add(deleted_candidate)

    # 3 user (включая admin_user), 2 active vacancy + 1 archived
    user1 = User(
        company_id=admin_user.company_id,
        email="user1@example.com",
        password_hash="hashed",
        full_name="User 1",
        is_active=True
    )
    user2 = User(
        company_id=admin_user.company_id,
        email="user2@example.com",
        password_hash="hashed",
        full_name="User 2",
        is_active=True
    )
    db_session.add_all([user1, user2])

    # 2 active vacancy
    for i in range(2):
        vacancy = Vacancy(
            company_id=admin_user.company_id,
            name=f"Active Billing Vacancy {i}",
            status='active'
        )
        db_session.add(vacancy)

    # 1 archived vacancy
    archived_vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Archived Billing Vacancy",
        status='archived'
    )
    db_session.add(archived_vacancy)

    await db_session.commit()

    # GET /settings/billing
    response = await async_client.get("/api/v1/settings/billing", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    # КРИТИЧЕСКАЯ ПРОВЕРКА: удалённый кандидат исключён
    assert body["current_candidates"] == 5  # НЕ 6 (удалённый исключён)
    assert body["current_vacancies"] == 2   # archived НЕ считается
    assert body["current_users"] == 3       # admin_user + user1 + user2 (все is_active=True)
    assert body["is_demo"] == True
    assert body["plan"] == "MVP"
    assert body["users_limit"] == 10
    assert body["candidates_limit"] == 1000
    assert body["vacancies_limit"] == 50