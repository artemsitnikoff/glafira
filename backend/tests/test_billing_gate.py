from datetime import date, timedelta
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Company
from app.core.security import get_password_hash

# Тесты проверяют РЕАЛЬНЫЙ billing-гейт → отключаем авто-обход из conftest
pytestmark = pytest.mark.billing_gate


@pytest.mark.asyncio
async def test_expired_company_blocked(async_client: AsyncClient, db_session: AsyncSession):
    """Expired company (paid_until = yesterday) → authenticated endpoint returns 402"""
    # Create company with expired subscription
    yesterday = date.today() - timedelta(days=1)
    company = Company(id=uuid.uuid4(), name="Expired Company", paid_until=yesterday)
    db_session.add(company)
    await db_session.flush()

    # Create user in expired company
    user = User(
        company_id=company.id,
        email="expired@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Expired User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Login to get token
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Try to access authenticated endpoint
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 402
    data = response.json()
    assert data["error"]["code"] == "SUBSCRIPTION_EXPIRED"
    assert "тариф" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_active_company_allowed(async_client: AsyncClient, db_session: AsyncSession):
    """Active company (paid_until = tomorrow) → authenticated endpoint returns 200"""
    # Create company with active subscription
    tomorrow = date.today() + timedelta(days=1)
    company = Company(id=uuid.uuid4(), name="Active Company", paid_until=tomorrow)
    db_session.add(company)
    await db_session.flush()

    # Create user in active company
    user = User(
        company_id=company.id,
        email="active@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Active User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Login to get token
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Access authenticated endpoint should work
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user.email


@pytest.mark.asyncio
async def test_paid_until_today_active(async_client: AsyncClient, db_session: AsyncSession):
    """paid_until == today → 200 (boundary, active)"""
    # Create company with subscription ending today
    today = date.today()
    company = Company(id=uuid.uuid4(), name="Today Company", paid_until=today)
    db_session.add(company)
    await db_session.flush()

    # Create user in company
    user = User(
        company_id=company.id,
        email="today@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Today User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Login to get token
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Access authenticated endpoint should work (today is still active)
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user.email


@pytest.mark.asyncio
async def test_paid_until_null_blocked(async_client: AsyncClient, db_session: AsyncSession):
    """paid_until == NULL → 402 (blocked)"""
    # Create company without paid_until (NULL)
    company = Company(id=uuid.uuid4(), name="No Subscription Company", paid_until=None)
    db_session.add(company)
    await db_session.flush()

    # Create user in company
    user = User(
        company_id=company.id,
        email="nosubscription@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="No Sub User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Login to get token
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Try to access authenticated endpoint
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 402
    data = response.json()
    assert data["error"]["code"] == "SUBSCRIPTION_EXPIRED"


@pytest.mark.asyncio
async def test_isolation_company_a_expired_company_b_active(async_client: AsyncClient, db_session: AsyncSession):
    """ISOLATION: company A expired + company B active → B's user gets 200, A's user gets 402"""
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

    # Create expired company A
    company_a = Company(id=uuid.uuid4(), name="Expired Company A", paid_until=yesterday)
    db_session.add(company_a)
    await db_session.flush()

    # Create active company B
    company_b = Company(id=uuid.uuid4(), name="Active Company B", paid_until=tomorrow)
    db_session.add(company_b)
    await db_session.flush()

    # Create user A in expired company
    user_a = User(
        company_id=company_a.id,
        email="usera@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="User A",
        role="admin",
        is_active=True,
    )
    db_session.add(user_a)

    # Create user B in active company
    user_b = User(
        company_id=company_b.id,
        email="userb@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="User B",
        role="admin",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.commit()

    # Login user A (expired company)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_a.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200
    token_a = response.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Login user B (active company)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_b.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200
    token_b = response.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A should get 402
    response = await async_client.get("/api/v1/auth/me", headers=headers_a)
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "SUBSCRIPTION_EXPIRED"

    # User B should get 200
    response = await async_client.get("/api/v1/auth/me", headers=headers_b)
    assert response.status_code == 200
    assert response.json()["email"] == user_b.email


@pytest.mark.asyncio
async def test_login_works_for_expired_company(async_client: AsyncClient, db_session: AsyncSession):
    """Login still works for a user whose company is expired (login endpoint returns token/200, NOT 402)"""
    # Create expired company
    yesterday = date.today() - timedelta(days=1)
    company = Company(id=uuid.uuid4(), name="Expired Company", paid_until=yesterday)
    db_session.add(company)
    await db_session.flush()

    # Create user in expired company
    user = User(
        company_id=company.id,
        email="expired_login@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Expired Login User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Login should still work despite expired subscription
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"