"""Tests for audit log API"""

from datetime import date, datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import AuditLog, User


async def test_get_audit_log_pagination(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
):
    """Test audit log pagination - 5 entries, page=1 size=2 should return total=5, len(items)=2"""

    # Create 5 audit log entries
    for i in range(5):
        audit_entry = AuditLog(
            company_id=admin_user.company_id,
            action=f"test_action_{i}",
            entity_type="test_entity",
            entity_id=None,
            actor_user_id=admin_user.id,
            actor_type="human",
            changes={"test": f"data_{i}"},
            created_at=datetime.now(timezone.utc) - timedelta(minutes=i),
        )
        db_session.add(audit_entry)

    await db_session.commit()

    # Test pagination
    response = await async_client.get(
        "/api/v1/audit-log?page=1&page_size=2",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


async def test_get_audit_log_entity_type_filter(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
):
    """Test entity_type filter - create mixed entries, filter by vacancy should return only vacancy entries"""

    # Create vacancy audit entries
    for i in range(3):
        audit_entry = AuditLog(
            company_id=admin_user.company_id,
            action=f"vacancy_action_{i}",
            entity_type="vacancy",
            entity_id=None,
            actor_user_id=admin_user.id,
            actor_type="human",
            changes={"vacancy": f"data_{i}"},
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(audit_entry)

    # Create employee audit entries
    for i in range(2):
        audit_entry = AuditLog(
            company_id=admin_user.company_id,
            action=f"employee_action_{i}",
            entity_type="employee",
            entity_id=None,
            actor_user_id=admin_user.id,
            actor_type="human",
            changes={"employee": f"data_{i}"},
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(audit_entry)

    await db_session.commit()

    # Filter by vacancy entity_type
    response = await async_client.get(
        "/api/v1/audit-log?entity_type=vacancy",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 3
    assert all(item["entity_type"] == "vacancy" for item in data["items"])


async def test_get_audit_log_admin_required(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    regular_user: User,
):
    """Test that admin role is required - non-admin user should get 403"""

    # Create auth headers for regular user (non-admin)
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": regular_user.email,
        "password": "Glafira2026!"
    })
    regular_token = login_response.json()["access_token"]
    regular_headers = {"Authorization": f"Bearer {regular_token}"}

    # Try to access audit log with regular user
    response = await async_client.get(
        "/api/v1/audit-log",
        headers=regular_headers
    )
    assert response.status_code == 403


async def test_get_audit_log_admin_access(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
):
    """Test that admin user can access audit logs"""

    # Create test audit entry
    audit_entry = AuditLog(
        company_id=admin_user.company_id,
        action="test_action",
        entity_type="test_entity",
        entity_id=None,
        actor_user_id=admin_user.id,
        actor_type="human",
        changes={"test": "data"},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(audit_entry)
    await db_session.commit()

    # Admin should have access
    response = await async_client.get(
        "/api/v1/audit-log",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 1  # At least our test entry