"""Tests for Message Templates functionality"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, AuditLog
from app.core.security import get_password_hash


@pytest.fixture
async def manager_user(db_session: AsyncSession, admin_user: User) -> User:
    """Create a manager user for testing"""
    user = User(
        company_id=admin_user.company_id,
        email="manager@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Менеджер Тестов",
        role="manager",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def regular_user(db_session: AsyncSession, admin_user: User) -> User:
    """Create a recruiter user for testing"""
    user = User(
        company_id=admin_user.company_id,
        email="recruiter@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Рекрутер Тестов",
        role="recruiter",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def get_auth_headers(async_client: AsyncClient, user: User) -> dict[str, str]:
    """Get auth headers for given user"""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestMessageTemplatesAccess:
    """Test RBAC for message templates endpoints"""

    async def test_list_templates_all_roles_can_read(
        self,
        async_client: AsyncClient,
        admin_user: User,
        regular_user: User,
        manager_user: User,
    ):
        """All authenticated users can read templates list"""
        # Admin
        admin_headers = await get_auth_headers(async_client, admin_user)
        response = await async_client.get("/api/v1/message-templates", headers=admin_headers)
        assert response.status_code == 200

        # Recruiter
        recruiter_headers = await get_auth_headers(async_client, regular_user)
        response = await async_client.get("/api/v1/message-templates", headers=recruiter_headers)
        assert response.status_code == 200

        # Manager
        manager_headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get("/api/v1/message-templates", headers=manager_headers)
        assert response.status_code == 200

    async def test_create_template_admin_and_recruiter_ok(
        self,
        async_client: AsyncClient,
        admin_user: User,
        regular_user: User,
    ):
        """Admin and recruiter can create templates"""
        template_data = {
            "name": "Тестовый шаблон",
            "body": "Привет! Как дела?",
            "order_index": 0
        }

        # Admin
        admin_headers = await get_auth_headers(async_client, admin_user)
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        assert response.json()["name"] == "Тестовый шаблон"

        # Recruiter
        recruiter_headers = await get_auth_headers(async_client, regular_user)
        template_data["name"] = "Шаблон рекрутера"
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=recruiter_headers)
        assert response.status_code == 201
        assert response.json()["name"] == "Шаблон рекрутера"

    async def test_create_template_manager_forbidden(
        self,
        async_client: AsyncClient,
        manager_user: User,
    ):
        """Manager cannot create templates"""
        template_data = {
            "name": "Тестовый шаблон",
            "body": "Привет! Как дела?",
            "order_index": 0
        }

        manager_headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=manager_headers)
        assert response.status_code == 403

    async def test_update_template_admin_and_recruiter_ok(
        self,
        async_client: AsyncClient,
        admin_user: User,
        regular_user: User,
    ):
        """Admin and recruiter can update templates"""
        # Create template first
        admin_headers = await get_auth_headers(async_client, admin_user)
        template_data = {"name": "Исходный шаблон", "body": "Исходный текст"}
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        template_id = response.json()["id"]

        # Update by admin
        update_data = {"name": "Обновленный шаблон", "body": "Новый текст"}
        response = await async_client.patch(f"/api/v1/message-templates/{template_id}",
                                          json=update_data, headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Обновленный шаблон"

        # Update by recruiter
        recruiter_headers = await get_auth_headers(async_client, regular_user)
        update_data = {"body": "Текст от рекрутера"}
        response = await async_client.patch(f"/api/v1/message-templates/{template_id}",
                                          json=update_data, headers=recruiter_headers)
        assert response.status_code == 200
        assert response.json()["body"] == "Текст от рекрутера"

    async def test_update_template_manager_forbidden(
        self,
        async_client: AsyncClient,
        admin_user: User,
        manager_user: User,
    ):
        """Manager cannot update templates"""
        # Create template first
        admin_headers = await get_auth_headers(async_client, admin_user)
        template_data = {"name": "Тестовый шаблон", "body": "Исходный текст"}
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        template_id = response.json()["id"]

        # Try to update by manager
        manager_headers = await get_auth_headers(async_client, manager_user)
        update_data = {"body": "Новый текст"}
        response = await async_client.patch(f"/api/v1/message-templates/{template_id}",
                                          json=update_data, headers=manager_headers)
        assert response.status_code == 403

    async def test_delete_template_admin_and_recruiter_ok(
        self,
        async_client: AsyncClient,
        admin_user: User,
        regular_user: User,
    ):
        """Admin and recruiter can delete templates"""
        admin_headers = await get_auth_headers(async_client, admin_user)

        # Create template by admin
        template_data = {"name": "Для удаления админом", "body": "Текст"}
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        template_id = response.json()["id"]

        # Delete by admin
        response = await async_client.delete(f"/api/v1/message-templates/{template_id}",
                                           headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["message"] == "Шаблон сообщения удалён"

        # Create template for recruiter deletion
        template_data = {"name": "Для удаления рекрутером", "body": "Текст"}
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        template_id = response.json()["id"]

        # Delete by recruiter
        recruiter_headers = await get_auth_headers(async_client, regular_user)
        response = await async_client.delete(f"/api/v1/message-templates/{template_id}",
                                           headers=recruiter_headers)
        assert response.status_code == 200

    async def test_delete_template_manager_forbidden(
        self,
        async_client: AsyncClient,
        admin_user: User,
        manager_user: User,
    ):
        """Manager cannot delete templates"""
        # Create template first
        admin_headers = await get_auth_headers(async_client, admin_user)
        template_data = {"name": "Тестовый шаблон", "body": "Текст"}
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        template_id = response.json()["id"]

        # Try to delete by manager
        manager_headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.delete(f"/api/v1/message-templates/{template_id}",
                                           headers=manager_headers)
        assert response.status_code == 403


class TestMessageTemplatesValidation:
    """Test validation and business logic"""

    async def test_validation_empty_name_and_body(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ):
        """Empty name and body should raise validation error"""
        admin_headers = await get_auth_headers(async_client, admin_user)

        # Empty name
        response = await async_client.post("/api/v1/message-templates",
                                         json={"name": "", "body": "Valid body"},
                                         headers=admin_headers)
        assert response.status_code == 400
        assert "Название шаблона обязательно" in response.text

        # Empty body
        response = await async_client.post("/api/v1/message-templates",
                                         json={"name": "Valid name", "body": ""},
                                         headers=admin_headers)
        assert response.status_code == 400
        assert "Текст шаблона обязателен" in response.text

    async def test_company_isolation(
        self,
        async_client: AsyncClient,
        admin_user: User,
        test_company: uuid.UUID,
        db_session: AsyncSession,
    ):
        """Templates should be isolated by company_id"""
        # Create another company and user
        other_company_id = uuid.uuid4()
        other_user = User(
            company_id=other_company_id,
            email="other@company.com",
            password_hash=get_password_hash("Glafira2026!"),
            full_name="Другой Админ",
            role="admin",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()

        # Create template in first company
        admin_headers = await get_auth_headers(async_client, admin_user)
        template_data = {"name": "Наш шаблон", "body": "Наш текст"}
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        template_id = response.json()["id"]

        # Try to access from other company user
        other_headers = await get_auth_headers(async_client, other_user)
        response = await async_client.patch(f"/api/v1/message-templates/{template_id}",
                                          json={"name": "Hack attempt"}, headers=other_headers)
        assert response.status_code == 404

    async def test_audit_log_written(
        self,
        async_client: AsyncClient,
        admin_user: User,
        db_session: AsyncSession,
    ):
        """All write operations should create audit log entries"""
        admin_headers = await get_auth_headers(async_client, admin_user)

        # Create
        template_data = {"name": "Аудит тест", "body": "Тест аудита"}
        response = await async_client.post("/api/v1/message-templates",
                                         json=template_data, headers=admin_headers)
        assert response.status_code == 201
        template_id = response.json()["id"]

        # Check create audit log
        audit_entries = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "message_template",
                AuditLog.action == "create_message_template",
                AuditLog.entity_id == uuid.UUID(template_id),
            )
        )
        assert audit_entries.scalars().first() is not None

        # Update
        response = await async_client.patch(f"/api/v1/message-templates/{template_id}",
                                          json={"name": "Обновленное название"}, headers=admin_headers)
        assert response.status_code == 200

        # Check update audit log
        audit_entries = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "message_template",
                AuditLog.action == "update_message_template",
                AuditLog.entity_id == uuid.UUID(template_id),
            )
        )
        assert audit_entries.scalars().first() is not None

        # Delete
        response = await async_client.delete(f"/api/v1/message-templates/{template_id}",
                                           headers=admin_headers)
        assert response.status_code == 200

        # Check delete audit log
        audit_entries = await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "message_template",
                AuditLog.action == "delete_message_template",
                AuditLog.entity_id == uuid.UUID(template_id),
            )
        )
        assert audit_entries.scalars().first() is not None