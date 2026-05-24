from httpx import AsyncClient

from app.models import User


async def test_login_success(async_client: AsyncClient, admin_user: User):
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(async_client: AsyncClient, admin_user: User):
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "wrong"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_nonexistent_user(async_client: AsyncClient, admin_user: User):
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "any"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_inactive_user(async_client: AsyncClient, inactive_user: User):
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": inactive_user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_INACTIVE"


async def test_me_without_token(async_client: AsyncClient):
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_AUTHENTICATED"


async def test_me_with_token(async_client: AsyncClient, auth_headers: dict[str, str], admin_user: User):
    response = await async_client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == admin_user.email
    assert data["full_name"] == "Анна Седова"
    assert data["role"] == "admin"
