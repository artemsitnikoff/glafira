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

    async def test_manager_cannot_update_candidates(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate_with_application,
    ):
        """Manager cannot edit candidate data — даже того, к кому имеет доступ (GET 200)."""
        candidate, application = test_candidate_with_application
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.patch(
            f"/api/v1/candidates/{candidate.id}",
            json={"city": "Тула"},
            headers=headers,
        )
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
        """Manager cannot read settings (профиль исключён — это личный аккаунт; берём
        реальные настройки системы /settings/glafira: GET = admin+recruiter)."""
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.get("/api/v1/settings/glafira", headers=headers)
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

        # RejectReasonCreate ожидает label+side (не name)
        reason_data = {
            "label": "Новая причина",
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

        # Валидный b24-webhook: https://<портал>/rest/<user_id>/<код>/
        config_data = {
            "webhook_url": "https://demo.bitrix24.ru/rest/1/abc123secretcode/"
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


class TestSmartSearchAccess:
    """Tests for Smart Search RBAC"""

    async def test_manager_cannot_access_smart_search(
        self,
        async_client: AsyncClient,
        manager_user: User,
    ):
        """Manager cannot access smart search endpoints"""
        headers = await get_auth_headers(async_client, manager_user)

        # Test hh-ветка (платный поиск)
        response = await async_client.get("/api/v1/smart/access", headers=headers)
        assert response.status_code == 403

        response = await async_client.get("/api/v1/smart/vacancies", headers=headers)
        assert response.status_code == 403

        search_data = {
            "vacancy_id": str(uuid.uuid4()),
            "scan_n": 10,
            "threshold": 50
        }
        response = await async_client.post("/api/v1/smart/search", json=search_data, headers=headers)
        assert response.status_code == 403

        # Test base-ветка (поиск по своей базе)
        base_search_data = {
            "search_type": "prompt",
            "query": "Python разработчик"
        }
        response = await async_client.post("/api/v1/smart/base/search", json=base_search_data, headers=headers)
        assert response.status_code == 403

        response = await async_client.get("/api/v1/smart/base/count", headers=headers)
        assert response.status_code == 403

    async def test_recruiter_can_access_smart_search(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
    ):
        """Recruiter can access smart search endpoints"""
        headers = await get_auth_headers(async_client, recruiter_user)

        # Test basic access endpoint (должен возвращать 200, даже если доступа нет)
        response = await async_client.get("/api/v1/smart/access", headers=headers)
        assert response.status_code == 200

        response = await async_client.get("/api/v1/smart/vacancies", headers=headers)
        assert response.status_code == 200

        response = await async_client.get("/api/v1/smart/base/count", headers=headers)
        assert response.status_code == 200

    async def test_admin_can_access_smart_search(
        self,
        async_client: AsyncClient,
        admin_user: User,
    ):
        """Admin can access smart search endpoints"""
        headers = await get_auth_headers(async_client, admin_user)

        # Test basic access endpoint
        response = await async_client.get("/api/v1/smart/access", headers=headers)
        assert response.status_code == 200

        response = await async_client.get("/api/v1/smart/vacancies", headers=headers)
        assert response.status_code == 200

        response = await async_client.get("/api/v1/smart/base/count", headers=headers)
        assert response.status_code == 200

        # Admin также может переиндексировать
        response = await async_client.post("/api/v1/smart/base/reindex", headers=headers)
        assert response.status_code == 202


class TestApplicationWriteAccess:
    """RBAC write-paths: менеджер только назначенные вакансии (FIX #1)"""

    async def test_manager_can_move_in_assigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate_with_application,
    ):
        """Менеджер может переводить заявку своей вакансии"""
        candidate, application = test_candidate_with_application
        headers = await get_auth_headers(async_client, manager_user)

        response = await async_client.post(
            f"/api/v1/applications/{application.id}/move",
            json={"stage": "selected"},
            headers=headers,
        )
        assert response.status_code == 200

    async def test_manager_cannot_move_in_unassigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
        test_candidate: "Candidate",
        db_session: AsyncSession,
        admin_user: User,
    ):
        """Менеджер не может переводить заявку чужой вакансии"""
        # Создаём кандидата с заявкой в чужой вакансии
        from app.models import Candidate as CandModel, Application as AppModel
        other_candidate = CandModel(
            company_id=admin_user.company_id,
            last_name="Чужой",
            first_name="Кандидат",
            source="manual",
        )
        db_session.add(other_candidate)
        await db_session.flush()
        other_app = AppModel(
            company_id=admin_user.company_id,
            candidate_id=other_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="response",
        )
        db_session.add(other_app)
        await db_session.commit()

        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post(
            f"/api/v1/applications/{other_app.id}/move",
            json={"stage": "selected"},
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_cannot_reject_in_unassigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
        db_session: AsyncSession,
        admin_user: User,
    ):
        """Менеджер не может отклонять заявки чужой вакансии"""
        from app.models import Candidate as CandModel, Application as AppModel
        other_candidate = CandModel(
            company_id=admin_user.company_id,
            last_name="Чужой2",
            first_name="Кандидат",
            source="manual",
        )
        db_session.add(other_candidate)
        await db_session.flush()
        other_app = AppModel(
            company_id=admin_user.company_id,
            candidate_id=other_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="response",
        )
        db_session.add(other_app)
        await db_session.commit()

        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post(
            f"/api/v1/applications/{other_app.id}/reject",
            json={"reason_id": None, "comment": ""},
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_bulk_move_with_foreign_app_returns_403(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate_with_application,
        test_vacancy: Vacancy,
        db_session: AsyncSession,
        admin_user: User,
    ):
        """bulk/move с чужой заявкой → 403 (fail-closed)"""
        candidate, own_app = test_candidate_with_application

        from app.models import Candidate as CandModel, Application as AppModel
        other_candidate = CandModel(
            company_id=admin_user.company_id,
            last_name="БалкЧужой",
            first_name="Кандидат",
            source="manual",
        )
        db_session.add(other_candidate)
        await db_session.flush()
        foreign_app = AppModel(
            company_id=admin_user.company_id,
            candidate_id=other_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="response",
        )
        db_session.add(foreign_app)
        await db_session.commit()

        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post(
            "/api/v1/applications/bulk/move",
            json={
                "application_ids": [str(own_app.id), str(foreign_app.id)],
                "stage": "selected",
            },
            headers=headers,
        )
        assert response.status_code == 403

    async def test_admin_bulk_move_not_affected(
        self,
        async_client: AsyncClient,
        admin_user: User,
        test_candidate_with_application,
    ):
        """admin не затронут — bulk/move работает"""
        candidate, application = test_candidate_with_application
        headers = await get_auth_headers(async_client, admin_user)
        response = await async_client.post(
            "/api/v1/applications/bulk/move",
            json={
                "application_ids": [str(application.id)],
                "stage": "selected",
            },
            headers=headers,
        )
        assert response.status_code == 200


class TestCandidateSubresourceWriteAccess:
    """RBAC: messages/comments/documents/calls/evaluation — менеджер только свои (FIX #1)"""

    async def test_manager_can_get_messages_in_assigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate_with_application,
    ):
        """Менеджер может читать сообщения кандидата своей вакансии"""
        candidate, _ = test_candidate_with_application
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get(
            f"/api/v1/candidates/{candidate.id}/messages",
            headers=headers,
        )
        assert response.status_code == 200

    async def test_manager_cannot_get_messages_for_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер не может читать сообщения чужого кандидата"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/messages",
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_cannot_post_message_for_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер не может отправить сообщение чужому кандидату"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post(
            f"/api/v1/candidates/{test_candidate.id}/messages",
            json={"text": "Привет", "channel": "hh"},
            headers=headers,
        )
        assert response.status_code == 403

    async def test_recruiter_can_post_message(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
        test_candidate: "Candidate",
    ):
        """Рекрутёр не ограничен — может отправлять сообщения"""
        headers = await get_auth_headers(async_client, recruiter_user)
        # Ответ 201 или бизнес-ошибка (нет интеграции) — главное не 403
        response = await async_client.post(
            f"/api/v1/candidates/{test_candidate.id}/messages",
            json={"text": "Привет", "channel": "hh"},
            headers=headers,
        )
        assert response.status_code != 403

    async def test_manager_cannot_get_comments_for_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер не может читать комментарии чужого кандидата"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/comments",
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_cannot_post_comment_for_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер не может добавить комментарий чужому кандидату"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post(
            f"/api/v1/candidates/{test_candidate.id}/comments",
            json={"text": "Заметка"},
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_cannot_get_documents_for_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер не может читать документы чужого кандидата (PII!)"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/documents",
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_cannot_get_calls_for_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер не может смотреть звонки чужого кандидата"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/calls",
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_cannot_get_evaluation_for_unrelated_candidate(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер не может читать AI-оценку чужого кандидата"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/evaluation",
            headers=headers,
        )
        # 403 от RBAC или 404 если оценки нет — главное не 200 для чужого кандидата
        assert response.status_code in (403, 404)

    async def test_manager_cannot_get_evaluation_for_unrelated_candidate_returns_403_not_200(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: "Candidate",
    ):
        """Менеджер чужой кандидат → строго 403, не 200"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/evaluation",
            headers=headers,
        )
        assert response.status_code == 403


class TestVacancyWriteAccess:
    """RBAC: write-пути вакансий — менеджер только назначенные (FIX #1)"""

    async def test_manager_cannot_patch_unassigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
    ):
        """Менеджер не может редактировать чужую вакансию"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.patch(
            f"/api/v1/vacancies/{test_vacancy.id}",
            json={"name": "Взлом"},
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_can_patch_assigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        manager_vacancy: Vacancy,
    ):
        """Менеджер может редактировать свою вакансию"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.patch(
            f"/api/v1/vacancies/{manager_vacancy.id}",
            json={"name": "Обновлённая вакансия"},
            headers=headers,
        )
        assert response.status_code == 200

    async def test_manager_cannot_publish_to_hh_unassigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
    ):
        """Менеджер не может публиковать на hh чужую вакансию (платное действие!)"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post(
            f"/api/v1/vacancies/{test_vacancy.id}/hh/publish",
            headers=headers,
        )
        assert response.status_code == 403

    async def test_admin_can_patch_any_vacancy(
        self,
        async_client: AsyncClient,
        admin_user: User,
        manager_vacancy: Vacancy,
    ):
        """Admin не ограничен — может редактировать любую вакансию"""
        headers = await get_auth_headers(async_client, admin_user)
        response = await async_client.patch(
            f"/api/v1/vacancies/{manager_vacancy.id}",
            json={"name": "Любая вакансия"},
            headers=headers,
        )
        assert response.status_code == 200

    async def test_recruiter_can_patch_any_vacancy(
        self,
        async_client: AsyncClient,
        recruiter_user: User,
        manager_vacancy: Vacancy,
    ):
        """Recruiter не ограничен — может редактировать любую вакансию"""
        headers = await get_auth_headers(async_client, recruiter_user)
        response = await async_client.patch(
            f"/api/v1/vacancies/{manager_vacancy.id}",
            json={"name": "Любая вакансия 2"},
            headers=headers,
        )
        assert response.status_code == 200

    async def test_manager_cannot_assign_candidate_to_unassigned_vacancy(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_vacancy: Vacancy,
        test_candidate: "Candidate",
    ):
        """Менеджер не может назначить кандидата в чужую вакансию"""
        headers = await get_auth_headers(async_client, manager_user)
        response = await async_client.post(
            f"/api/v1/candidates/{test_candidate.id}/applications",
            json={"vacancy_id": str(test_vacancy.id), "stage": "response"},
            headers=headers,
        )
        assert response.status_code == 403