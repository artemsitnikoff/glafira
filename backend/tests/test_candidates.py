import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class TestCandidates:
    async def test_create_candidate_validation(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str]
    ):
        """Test 422 validation error without required fields"""
        # Missing source
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Иванов",
                "first_name": "Иван"
            }
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

        # Missing last_name
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "first_name": "Иван",
                "source": "manual"
            }
        )

        assert response.status_code == 422

        # Missing first_name
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Иванов",
                "source": "manual"
            }
        )

        assert response.status_code == 422

    async def test_create_candidate_with_vacancy_id(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test creating candidate with vacancy_id creates application in 'added' stage"""
        from app.models import Vacancy
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate

        # Create vacancy directly via service to avoid router issues
        vacancy_data = VacancyCreate(
            name="Test Vacancy",
            funnel_template="default",
            team=[admin_user.id]
        )
        vacancy = await create_vacancy(
            db_session, vacancy_data, admin_user.company_id, admin_user.id
        )
        await db_session.commit()

        # Create candidate with vacancy_id
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Петров",
                "first_name": "Пётр",
                "source": "manual",
                "vacancy_id": str(vacancy.id)
            }
        )

        assert response.status_code == 201
        candidate = response.json()
        assert candidate["last_name"] == "Петров"
        assert candidate["first_name"] == "Пётр"
        assert candidate["source"] == "manual"

        candidate_id = candidate["id"]

        # Check that application was created
        apps_response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}/applications",
            headers=auth_headers
        )
        assert apps_response.status_code == 200
        applications = apps_response.json()
        assert len(applications) == 1
        assert applications[0]["stage"] == "added"
        assert applications[0]["vacancy_id"] == str(vacancy.id)