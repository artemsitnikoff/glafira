from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_refresh_token
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


# === last_login_at (реальный трекинг последнего входа) ======================

async def test_login_sets_last_login_at(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Свежий пользователь не входил → last_login_at NULL; успешный login его выставляет."""
    assert admin_user.last_login_at is None

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200, response.text

    await db_session.refresh(admin_user)
    assert admin_user.last_login_at is not None


async def test_login_updates_last_login_at_on_repeat(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Повторный вход ОБНОВЛЯЕТ last_login_at (не только первый раз).

    Дискриминирующий: ставим заведомо СТАРОЕ значение. Если бы код писал время
    лишь при первом входе (`if last_login_at is None`), повторный вход не тронул бы
    его и assert `> old` упал бы.
    """
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    admin_user.last_login_at = old
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200, response.text

    await db_session.refresh(admin_user)
    assert admin_user.last_login_at is not None
    assert admin_user.last_login_at > old


async def test_failed_login_does_not_touch_last_login_at(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Неудачный вход (неверный пароль) НЕ трогает last_login_at.

    Дискриминирующий: заранее ставим маркер; после 401 значение обязано остаться
    прежним (если бы время писалось до проверки пароля — маркер бы изменился).
    """
    marker = datetime(2021, 6, 1, tzinfo=timezone.utc)
    admin_user.last_login_at = marker
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "wrong"},
    )
    assert response.status_code == 401

    await db_session.refresh(admin_user)
    assert admin_user.last_login_at == marker


async def test_refresh_updates_last_login_at(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Успешный refresh токена обновляет last_login_at (свежесть сессии по ходу работы)."""
    old = datetime(2019, 3, 3, tzinfo=timezone.utc)
    admin_user.last_login_at = old
    await db_session.commit()

    token = create_refresh_token(data={"sub": str(admin_user.id)})
    response = await async_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": token},
    )
    assert response.status_code == 200, response.text

    await db_session.refresh(admin_user)
    assert admin_user.last_login_at is not None
    assert admin_user.last_login_at > old
