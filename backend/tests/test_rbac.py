"""Tests for RBAC (Role-Based Access Control) system"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Vacancy, VacancyTeam, Candidate, Application
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
async def recruiter_user(db_session: AsyncSession, admin_user: User) -> User:
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


@pytest.fixture
async def test_vacancy(db_session: AsyncSession, admin_user: User) -> Vacancy:
    """Create a test vacancy"""
    vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Тестовая вакансия",
        responsible_user_id=admin_user.id,
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest.fixture
async def manager_vacancy(db_session: AsyncSession, manager_user: User) -> Vacancy:
    """Create a vacancy assigned to manager via responsible_user_id"""
    vacancy = Vacancy(
        company_id=manager_user.company_id,
        name="Вакансия менеджера",
        responsible_user_id=manager_user.id,
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest.fixture
async def manager_team_vacancy(db_session: AsyncSession, manager_user: User) -> Vacancy:
    """Create a vacancy assigned to manager via VacancyTeam"""
    vacancy = Vacancy(
        company_id=manager_user.company_id,
        name="Командная вакансия менеджера",
    )
    db_session.add(vacancy)
    await db_session.flush()

    # Add manager to vacancy team
    team = VacancyTeam(
        company_id=manager_user.company_id,
        vacancy_id=vacancy.id,
        user_id=manager_user.id,
    )
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest.fixture
async def test_candidate_with_application(
    db_session: AsyncSession,
    manager_user: User,
    manager_vacancy: Vacancy
) -> tuple[Candidate, Application]:
    """Create candidate with application in manager's vacancy"""
    candidate = Candidate(
        company_id=manager_user.company_id,
        last_name="Кандидатов",
        first_name="Кандидат",
        source="manual",
        phone="+7 900 123 45 67",
        email="candidate@example.com",
    )
    db_session.add(candidate)
    await db_session.flush()

    application = Application(
        company_id=manager_user.company_id,
        candidate_id=candidate.id,
        vacancy_id=manager_vacancy.id,
        stage="response",
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(candidate)
    await db_session.refresh(application)
    return candidate, application


async def get_auth_headers(async_client: AsyncClient, user: User) -> dict[str, str]:
    """Get auth headers for given user"""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestVacancyAccess:
    """Tests for vacancy access control"""

    async def test_manager_sees_only_assigned_vacancies(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_vacancy: Vacancy,
        test_vacancy: Vacancy,
    ):
        """Manager should only see assigned vacancies in listing"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get("/api/v1/vacancies", headers=headers)
        assert response.status_code == 200

        data = response.json()
        vacancy_ids = [v["id"] for v in data["items"]]

        assert str(manager_vacancy.id) in vacancy_ids
        assert str(test_vacancy.id) not in vacancy_ids

    async def test_manager_sees_assigned_vacancy_in_sidebar(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_vacancy: Vacancy,
        test_vacancy: Vacancy,
    ):
        """Manager should only see assigned vacancies in sidebar"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get("/api/v1/vacancies/sidebar", headers=headers)
        assert response.status_code == 200

        data = response.json()
        vacancy_ids = [v["id"] for v in data["items"]]

        assert str(manager_vacancy.id) in vacancy_ids
        assert str(test_vacancy.id) not in vacancy_ids

    async def test_manager_can_access_assigned_vacancy_details(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_vacancy: Vacancy,
    ):
        """Manager can access details of assigned vacancy"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/vacancies/{manager_vacancy.id}", headers=headers)
        assert response.status_code == 200

    async def test_manager_cannot_access_unassigned_vacancy_details(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
    ):
        """Manager cannot access details of unassigned vacancy"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/vacancies/{test_vacancy.id}", headers=headers)
        assert response.status_code == 403

    async def test_manager_cannot_create_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
    ):
        """Manager cannot create vacancies"""
        headers = await get_auth_headers(async_client, manager_user)

        vacancy_data = {
            "name": "Новая вакансия",
            "sort_order": 100,
            "funnel_template": "default"
        }

        response = await async_client.post("/api/v1/vacancies", json=vacancy_data, headers=headers)
        assert response.status_code == 403

    async def test_manager_can_access_assigned_vacancy_stages(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_vacancy: Vacancy,
    ):
        """Manager can access stages of assigned vacancy"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/vacancies/{manager_vacancy.id}/stages", headers=headers)
        assert response.status_code == 200

    async def test_manager_cannot_access_unassigned_vacancy_stages(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
    ):
        """Manager cannot access stages of unassigned vacancy"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/vacancies/{test_vacancy.id}/stages", headers=headers)
        assert response.status_code == 403

    async def test_admin_can_access_all_vacancies(
        self,
        async_client: AsyncClient,
        admin_user: User,
        manager_vacancy: Vacancy,
        test_vacancy: Vacancy,
    ):
        """Admin can access all vacancies"""
        headers = await get_auth_headers(async_client, admin_user)

        response = await async_client.get("/api/v1/vacancies", headers=headers)
        assert response.status_code == 200

        data = response.json()
        vacancy_ids = [v["id"] for v in data["items"]]

        assert str(manager_vacancy.id) in vacancy_ids
        assert str(test_vacancy.id) in vacancy_ids

    async def test_recruiter_can_access_all_vacancies(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
        manager_vacancy: Vacancy,
        test_vacancy: Vacancy,
    ):
        """Recruiter can access all vacancies"""
        headers = await get_auth_headers(async_client, recruiter_user)

        response = await async_client.get("/api/v1/vacancies", headers=headers)
        assert response.status_code == 200

        data = response.json()
        vacancy_ids = [v["id"] for v in data["items"]]

        assert str(manager_vacancy.id) in vacancy_ids
        assert str(test_vacancy.id) in vacancy_ids


class TestApplicationAccess:
    """Tests for application access control"""

    async def test_manager_can_access_assigned_vacancy_applications(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_vacancy: Vacancy,
    ):
        """Manager can access applications in assigned vacancy"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/vacancies/{manager_vacancy.id}/applications", headers=headers)
        assert response.status_code == 200

    async def test_manager_cannot_access_unassigned_vacancy_applications(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
    ):
        """Manager cannot access applications in unassigned vacancy"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/vacancies/{test_vacancy.id}/applications", headers=headers)
        assert response.status_code == 403


class TestCandidateAccess:
    """Tests for candidate access control"""

    async def test_manager_cannot_access_general_candidate_pool(
        self,
        async_client: AsyncClient,
        manager_user: User,
    ):
        """Manager cannot access general candidate pool"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get("/api/v1/candidates", headers=headers)
        assert response.status_code == 403

    async def test_manager_can_access_candidate_in_assigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate_with_application,
    ):
        """Manager can access candidate who has application in manager's vacancy"""
        candidate, application = test_candidate_with_application
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/candidates/{candidate.id}", headers=headers)
        assert response.status_code == 200

    async def test_manager_cannot_access_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: Candidate,
    ):
        """Manager cannot access candidate with no applications in manager's vacancies"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/candidates/{test_candidate.id}", headers=headers)
        assert response.status_code == 403

    async def test_manager_cannot_create_candidates(
        self,
        async_client: AsyncClient,
        manager_user: User,
    ):
        """Manager cannot create candidates"""
        headers = await get_auth_headers(async_client, manager_user)

        candidate_data = {
            "last_name": "Новый",
            "first_name": "Кандидат",
            "source": "manual",
        }

        response = await async_client.post("/api/v1/candidates", json=candidate_data, headers=headers)
        assert response.status_code == 403

    async def test_manager_cannot_add_tags_to_candidates(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate_with_application,
    ):
        """Manager cannot add tags to candidates"""
        candidate, application = test_candidate_with_application
        headers = await get_auth_headers(async_client, manager_user)

        tag_data = {"tag_id": str(uuid.uuid4())}

        response = await async_client.post(
            f"/api/v1/candidates/{candidate.id}/tags",
            json=tag_data,
            headers=headers
        )
        assert response.status_code == 403

    async def test_recruiter_can_access_general_candidate_pool(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
    ):
        """Recruiter can access general candidate pool"""
        headers = await get_auth_headers(async_client, recruiter_user)

        response = await async_client.get("/api/v1/candidates", headers=headers)
        assert response.status_code == 200

    async def test_admin_can_access_general_candidate_pool(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ):
        """Admin can access general candidate pool"""
        headers = await get_auth_headers(async_client, admin_user)

        response = await async_client.get("/api/v1/candidates", headers=headers)
        assert response.status_code == 200


class TestSettingsAccess:
    """Tests for settings access control"""

    async def test_admin_can_read_settings(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ):
        """Admin can read settings"""
        headers = await get_auth_headers(async_client, admin_user)

        response = await async_client.get("/api/v1/settings/profile", headers=headers)
        assert response.status_code == 200

    async def test_recruiter_can_read_settings(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
    ):
        """Recruiter can read settings"""
        headers = await get_auth_headers(async_client, recruiter_user)

        response = await async_client.get("/api/v1/settings/profile", headers=headers)
        assert response.status_code == 200

    async def test_manager_cannot_read_settings(
        self,
        async_client: AsyncClient,
        manager_user: User,
    ):
        """Manager cannot read settings"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get("/api/v1/settings/profile", headers=headers)
        assert response.status_code == 403

    async def test_recruiter_cannot_write_settings(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
    ):
        """Recruiter cannot write settings"""
        headers = await get_auth_headers(async_client, recruiter_user)

        # Try to create a reject reason (write operation)
        reason_data = {
            "name": "Новая причина",
            "side": "company",
        }

        response = await async_client.post("/api/v1/settings/reject-reasons", json=reason_data, headers=headers)
        assert response.status_code == 403

    async def test_admin_can_write_settings(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ):
        """Admin can write settings"""
        headers = await get_auth_headers(async_client, admin_user)

        # Try to create a reject reason (write operation)
        reason_data = {
            "name": "Новая причина",
            "side": "company",
        }

        response = await async_client.post("/api/v1/settings/reject-reasons", json=reason_data, headers=headers)
        assert response.status_code == 201


class TestIntegrationsAccess:
    """Tests for integrations access control"""

    async def test_admin_can_read_integrations(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ):
        """Admin can read integrations status"""
        headers = await get_auth_headers(async_client, admin_user)

        response = await async_client.get("/api/v1/integrations/hh/status", headers=headers)
        assert response.status_code == 200

    async def test_recruiter_can_read_integrations(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
    ):
        """Recruiter can read integrations status"""
        headers = await get_auth_headers(async_client, recruiter_user)

        response = await async_client.get("/api/v1/integrations/hh/status", headers=headers)
        assert response.status_code == 200

    async def test_manager_cannot_read_integrations(
        self,
        async_client: AsyncClient,
        manager_user: User,
    ):
        """Manager cannot read integrations"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get("/api/v1/integrations/hh/status", headers=headers)
        assert response.status_code == 403

    async def test_recruiter_cannot_configure_integrations(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
    ):
        """Recruiter cannot configure integrations"""
        headers = await get_auth_headers(async_client, recruiter_user)

        config_data = {
            "webhook_url": "https://example.com/webhook"
        }

        response = await async_client.post("/api/v1/integrations/bitrix24/config", json=config_data, headers=headers)
        assert response.status_code == 403

    async def test_admin_can_configure_integrations(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ):
        """Admin can configure integrations"""
        headers = await get_auth_headers(async_client, admin_user)

        config_data = {
            "webhook_url": "https://example.com/webhook"
        }

        response = await async_client.post("/api/v1/integrations/bitrix24/config", json=config_data, headers=headers)
        assert response.status_code == 200


class TestVacancyTeamAssignment:
    """Tests for VacancyTeam assignment access"""

    async def test_manager_can_access_team_assigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_team_vacancy: Vacancy,
    ):
        """Manager can access vacancy assigned via VacancyTeam"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get(f"/api/v1/vacancies/{manager_team_vacancy.id}", headers=headers)
        assert response.status_code == 200

    async def test_manager_sees_team_assigned_vacancy_in_listing(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_team_vacancy: Vacancy,
    ):
        """Manager sees team-assigned vacancy in listing"""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get("/api/v1/vacancies", headers=headers)
        assert response.status_code == 200

        data = response.json()
        vacancy_ids = [v["id"] for v in data["items"]]

        assert str(manager_team_vacancy.id) in vacancy_ids