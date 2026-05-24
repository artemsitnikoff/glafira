import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient):
    """Test successful login"""
    response = await async_client.post("/api/v1/auth/login", json={
        "email": "anna.sedova@example.com",
        "password": "Glafira2026!"
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(async_client: AsyncClient):
    """Test login with wrong password"""
    response = await async_client.post("/api/v1/auth/login", json={
        "email": "anna.sedova@example.com",
        "password": "wrong_password"
    })

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_nonexistent_user(async_client: AsyncClient):
    """Test login with nonexistent user"""
    response = await async_client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "any_password"
    })

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_inactive_user(async_client: AsyncClient, db_session: AsyncSession):
    """Test login with inactive user"""
    # Deactivate user
    result = await db_session.execute(
        select(User).where(User.email == "anna.sedova@example.com")
    )
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    response = await async_client.post("/api/v1/auth/login", json={
        "email": "anna.sedova@example.com",
        "password": "Glafira2026!"
    })

    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "USER_INACTIVE"


@pytest.mark.asyncio
async def test_me_without_token(async_client: AsyncClient):
    """Test /me endpoint without token"""
    response = await async_client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(async_client: AsyncClient, auth_headers: dict[str, str]):
    """Test /me endpoint with valid token"""
    response = await async_client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "anna.sedova@example.com"
    assert data["full_name"] == "Анна Седова"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_logout(async_client: AsyncClient):
    """Test logout endpoint"""
    response = await async_client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    data = response.json()
    assert "message" in data