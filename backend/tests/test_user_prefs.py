"""Tests for user preferences (language/date_format/timezone)"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


@pytest.mark.asyncio
async def test_get_profile_includes_prefs(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test GET /settings/profile returns language and date_format"""
    response = await async_client.get(
        "/api/v1/settings/profile",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "language" in data
    assert "date_format" in data
    assert "timezone" in data
    assert data["language"] == "ru"  # Default value
    assert data["date_format"] == "DD.MM.YYYY"  # Default value


@pytest.mark.asyncio
async def test_update_profile_language_and_date_format(
    async_client: AsyncClient,
    admin_token: str,
    admin_user: User,
    db_session: AsyncSession,
):
    """Test PATCH /settings/profile updates language and date_format"""
    # Update language and date_format
    response = await async_client.patch(
        "/api/v1/settings/profile",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "language": "en",
            "date_format": "MM/DD/YYYY",
            "timezone": "America/New_York"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "en"
    assert data["date_format"] == "MM/DD/YYYY"
    assert data["timezone"] == "America/New_York"

    # Verify in database
    await db_session.refresh(admin_user)
    assert admin_user.language == "en"
    assert admin_user.date_format == "MM/DD/YYYY"
    assert admin_user.timezone == "America/New_York"


@pytest.mark.asyncio
async def test_update_profile_partial_prefs(
    async_client: AsyncClient,
    admin_token: str,
    admin_user: User,
    db_session: AsyncSession,
):
    """Test PATCH /settings/profile with only some preference fields"""
    # Update only language
    response = await async_client.patch(
        "/api/v1/settings/profile",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "language": "fr"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "fr"
    # Other fields should remain unchanged
    assert data["date_format"] == "DD.MM.YYYY"
    assert data["timezone"] == "Europe/Moscow"


@pytest.mark.asyncio
async def test_update_profile_backward_compatibility(
    async_client: AsyncClient,
    admin_token: str,
):
    """Test that old profile update requests without new fields still work"""
    # Update existing fields without new prefs
    response = await async_client.patch(
        "/api/v1/settings/profile",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": "Updated Name",
            "phone": "+7999123456"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"
    assert data["phone"] == "+7999123456"
    # New fields should have defaults
    assert "language" in data
    assert "date_format" in data