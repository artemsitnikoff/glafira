import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Vacancy, VacancyStage


@pytest.mark.asyncio
async def test_create_vacancy_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession
):
    """Test creating a vacancy with stages"""
    vacancy_data = {
        "name": "Senior Python Developer",
        "city": "Москва",
        "salary_from": 250000,
        "salary_to": 400000,
        "currency": "RUB",
        "description": "Ищем опытного Python разработчика",
        "funnel_template": "default",
        "positions_count": 2
    }

    response = await async_client.post(
        "/api/v1/vacancies/",
        headers=auth_headers,
        json=vacancy_data
    )

    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Senior Python Developer"
    assert data["city"] == "Москва"
    assert data["salary_from"] == 250000
    assert data["salary_to"] == 400000
    assert data["status"] == "active"

    # Check that stages were created
    vacancy_id = data["id"]
    stage_count = await db_session.execute(
        select(func.count(VacancyStage.id)).where(VacancyStage.vacancy_id == vacancy_id)
    )
    count = stage_count.scalar_one()
    assert count == 9  # Default template has 9 stages


@pytest.mark.asyncio
async def test_get_vacancy_sidebar(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """Test getting sidebar data"""
    response = await async_client.get("/api/v1/vacancies/sidebar", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "archived_count" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_vacancies_list(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """Test getting vacancies list"""
    response = await async_client.get("/api/v1/vacancies/", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_vacancy_by_id(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession
):
    """Test getting vacancy by ID"""
    # First create a vacancy
    vacancy_data = {
        "name": "Test Vacancy",
        "city": "Москва"
    }

    create_response = await async_client.post(
        "/api/v1/vacancies/",
        headers=auth_headers,
        json=vacancy_data
    )
    vacancy_id = create_response.json()["id"]

    # Now get it
    response = await async_client.get(f"/api/v1/vacancies/{vacancy_id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == vacancy_id
    assert data["name"] == "Test Vacancy"


@pytest.mark.asyncio
async def test_get_vacancy_stages(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """Test getting vacancy stages with counts"""
    # First create a vacancy
    vacancy_data = {"name": "Test Vacancy for Stages"}

    create_response = await async_client.post(
        "/api/v1/vacancies/",
        headers=auth_headers,
        json=vacancy_data
    )
    vacancy_id = create_response.json()["id"]

    # Get stages
    response = await async_client.get(f"/api/v1/vacancies/{vacancy_id}/stages", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 9  # Default template

    # Check stage structure
    for stage in data:
        assert "stage_key" in stage
        assert "label" in stage
        assert "color" in stage
        assert "count" in stage
        assert "is_terminal" in stage