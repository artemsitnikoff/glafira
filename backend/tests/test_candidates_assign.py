import pytest
from uuid import uuid4
from httpx import AsyncClient

from app.core.stages import STAGES


@pytest.mark.asyncio
async def test_assign_candidate_to_vacancy_success(
    async_client: AsyncClient, auth_headers: dict, test_candidate, default_client
):
    """Test successful assignment of candidate to vacancy"""
    # Create a vacancy for testing
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy",
            "description": "Test vacancy description",
            "location": "Remote",
            "salary_from": 50000,
            "salary_to": 80000,
            "client_id": default_client
        }
    )
    assert vacancy_response.status_code == 201
    vacancy_id = vacancy_response.json()["id"]

    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id,
            "stage": "response"
        }
    )
    assert response.status_code == 201
    data = response.json()

    # Check response structure
    assert data["id"]
    assert data["candidate_id"] == str(test_candidate.id)
    assert data["stage"] == "response"
    assert data["stage_color"] == STAGES["response"].color
    assert data["selected_at"] is not None


@pytest.mark.asyncio
async def test_assign_candidate_duplicate_application(
    async_client: AsyncClient, auth_headers: dict, test_candidate, default_client
):
    """Test creating duplicate application returns 409"""
    # Create a vacancy for testing
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy 2",
            "description": "Test vacancy description",
            "location": "Remote",
            "salary_from": 50000,
            "salary_to": 80000,
            "client_id": default_client
        }
    )
    assert vacancy_response.status_code == 201
    vacancy_id = vacancy_response.json()["id"]

    # Create first application
    await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id,
            "stage": "response"
        }
    )

    # Try to create duplicate
    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id,
            "stage": "selected"
        }
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "CONFLICT"
    assert "уже назначен" in error["message"]


@pytest.mark.asyncio
async def test_assign_nonexistent_candidate(
    async_client: AsyncClient, auth_headers: dict, default_client
):
    """Test assigning nonexistent candidate returns 404"""
    fake_candidate_id = str(uuid4())

    # Create a vacancy for testing
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy 3",
            "description": "Test vacancy description",
            "location": "Remote",
            "salary_from": 50000,
            "salary_to": 80000,
            "client_id": default_client
        }
    )
    assert vacancy_response.status_code == 201
    vacancy_id = vacancy_response.json()["id"]

    response = await async_client.post(
        f"/api/v1/candidates/{fake_candidate_id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id,
            "stage": "response"
        }
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_assign_to_nonexistent_vacancy(
    async_client: AsyncClient, auth_headers: dict, test_candidate
):
    """Test assigning to nonexistent vacancy returns 404"""
    fake_vacancy_id = str(uuid4())

    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": fake_vacancy_id,
            "stage": "response"
        }
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_assign_unknown_stage_falls_back_to_real_stage(
    async_client: AsyncClient, auth_headers: dict, test_candidate, default_client
):
    """A stage not present in the vacancy's funnel falls back to the first
    non-terminal stage of that vacancy (documented intentional behaviour:
    the request schema defaults stage to 'response', so the service cannot
    distinguish an explicit bad stage from the default, and we avoid putting
    the candidate into a ghost stage / raising 500). The candidate must land
    on a real, non-terminal stage of the vacancy — never on the requested
    unknown stage."""
    # Create a vacancy for testing — this seeds real vacancy_stages rows
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy 4",
            "description": "Test vacancy description",
            "location": "Remote",
            "salary_from": 50000,
            "salary_to": 80000,
            "client_id": default_client
        }
    )
    assert vacancy_response.status_code == 201
    vacancy_id = vacancy_response.json()["id"]

    # Fetch the vacancy's real funnel stages
    stages_response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
    )
    assert stages_response.status_code == 200
    funnel_keys = {s["stage_key"] for s in stages_response.json()}
    assert funnel_keys  # vacancy has seeded stages

    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id,
            "stage": "invalid_stage"
        }
    )
    assert response.status_code == 201
    data = response.json()
    # Candidate must NOT be placed on the requested unknown stage
    assert data["stage"] != "invalid_stage"
    # Candidate lands on a real stage of THIS vacancy's funnel
    assert data["stage"] in funnel_keys
    # ...and it is a non-terminal one (first non-terminal = 'response' here)
    assert data["stage"] not in ("hired", "rejected")
    assert data["stage"] == "response"


@pytest.mark.asyncio
async def test_assign_default_stage(
    async_client: AsyncClient, auth_headers: dict, test_candidate, default_client
):
    """Test assignment with default stage (response)"""
    # Create a vacancy for testing
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy 5",
            "description": "Test vacancy description",
            "location": "Remote",
            "salary_from": 50000,
            "salary_to": 80000,
            "client_id": default_client
        }
    )
    assert vacancy_response.status_code == 201
    vacancy_id = vacancy_response.json()["id"]

    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id
            # stage omitted, should default to "response"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["stage"] == "response"


@pytest.mark.asyncio
async def test_assign_candidate_has_pdn_true(
    async_client: AsyncClient, auth_headers: dict, test_candidate, db_session, admin_user, default_client
):
    """Тест 3: кандидат + signed consent → assign → has_pdn == True"""
    from app.models import Consent, Vacancy

    # Создаём signed consent для кандидата
    consent = Consent(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        number="TEST-CONSENT-001",
        status="signed"
    )
    db_session.add(consent)
    await db_session.flush()

    # Create a vacancy for testing
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy PDN True",
            "description": "Test vacancy description",
            "client_id": default_client
        }
    )
    assert vacancy_response.status_code == 201
    vacancy_id = vacancy_response.json()["id"]

    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id,
            "stage": "response"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["has_pdn"] == True


@pytest.mark.asyncio
async def test_assign_candidate_has_pdn_false(
    async_client: AsyncClient, auth_headers: dict, test_candidate, default_client
):
    """Тест 4: кандидат без consent → assign → has_pdn == False"""
    # Create a vacancy for testing
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy PDN False",
            "description": "Test vacancy description",
            "client_id": default_client
        }
    )
    assert vacancy_response.status_code == 201
    vacancy_id = vacancy_response.json()["id"]

    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={
            "vacancy_id": vacancy_id,
            "stage": "response"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["has_pdn"] == False