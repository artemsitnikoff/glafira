from httpx import AsyncClient

from app.models import User
from app.core.security import create_access_token, create_refresh_token, decode_token


async def test_access_token_has_type_claim(admin_user: User):
    """Test that access tokens have correct type claim"""
    token = create_access_token(data={"sub": str(admin_user.id)})
    payload = decode_token(token)
    assert payload["type"] == "access"


async def test_refresh_token_has_type_claim(admin_user: User):
    """Test that refresh tokens have correct type claim"""
    token = create_refresh_token(data={"sub": str(admin_user.id)})
    payload = decode_token(token)
    assert payload["type"] == "refresh"


async def test_get_current_user_rejects_refresh_token_as_bearer(async_client: AsyncClient, admin_user: User):
    """Test that get_current_user rejects refresh token when used as Bearer"""
    refresh_token = create_refresh_token(data={"sub": str(admin_user.id)})

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_get_current_user_accepts_valid_access_token(async_client: AsyncClient, auth_headers: dict[str, str], admin_user: User):
    """Test that get_current_user accepts valid access token"""
    response = await async_client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == admin_user.email


async def test_refresh_endpoint_rejects_access_token_in_cookie(async_client: AsyncClient, admin_user: User):
    """Test that /refresh rejects access token when provided as refresh cookie"""
    access_token = create_access_token(data={"sub": str(admin_user.id)})

    response = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": access_token}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_refresh_endpoint_accepts_valid_refresh_token(async_client: AsyncClient, admin_user: User):
    """Test that /refresh accepts valid refresh token and returns new access token"""
    refresh_token = create_refresh_token(data={"sub": str(admin_user.id)})

    response = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_refresh_endpoint_rejects_inactive_user(async_client: AsyncClient, inactive_user: User):
    """Test that /refresh rejects refresh token from inactive user"""
    refresh_token = create_refresh_token(data={"sub": str(inactive_user.id)})

    response = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh_token}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_get_current_user_handles_invalid_uuid(async_client: AsyncClient):
    """Test that get_current_user handles invalid UUID in sub claim gracefully"""
    # Create token with invalid UUID
    invalid_token = create_access_token(data={"sub": "not-a-uuid"})

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {invalid_token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_refresh_endpoint_handles_invalid_uuid(async_client: AsyncClient):
    """Test that /refresh handles invalid UUID in sub claim gracefully"""
    # Create refresh token with invalid UUID
    invalid_token = create_refresh_token(data={"sub": "not-a-uuid"})

    response = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": invalid_token}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"