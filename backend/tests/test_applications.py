import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Candidate, Application, StageHistory


@pytest.mark.asyncio
async def test_application_move_and_history(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession
):
    """Test moving application through stages and checking history"""
    # Create a vacancy first
    vacancy_data = {"name": "Test Vacancy for Applications"}
    vacancy_response = await async_client.post(
        "/api/v1/vacancies/",
        headers=auth_headers,
        json=vacancy_data
    )
    vacancy_id = vacancy_response.json()["id"]

    # Create a candidate manually in the database
    candidate = Candidate(
        company_id="00000000-0000-0000-0000-000000000001",
        last_name="Иванов",
        first_name="Иван",
        middle_name="Иванович",
        full_name="Иванов Иван Иванович",
        source="manual",
        phone="+7 905 123 45 67",
        email="ivan.ivanov@example.com",
        city="Москва"
    )
    db_session.add(candidate)
    await db_session.flush()

    # Create an application
    application = Application(
        company_id="00000000-0000-0000-0000-000000000001",
        candidate_id=candidate.id,
        vacancy_id=vacancy_id,
        stage="response"
    )
    db_session.add(application)
    await db_session.commit()

    # Test moving through stages
    stages_to_test = ["added", "selected", "recruiter", "interview"]

    for stage in stages_to_test:
        # Move to next stage
        move_response = await async_client.post(
            f"/api/v1/applications/{application.id}/move",
            headers=auth_headers,
            json={"to_stage": stage}
        )

        assert move_response.status_code == 200
        move_data = move_response.json()
        assert move_data["new_stage"] == stage

    # Test reject
    reject_response = await async_client.post(
        f"/api/v1/applications/{application.id}/reject",
        headers=auth_headers,
        json={"reason": "Не подходит по опыту", "side": "company"}
    )

    assert reject_response.status_code == 200

    # Test restore
    restore_response = await async_client.post(
        f"/api/v1/applications/{application.id}/restore",
        headers=auth_headers
    )

    assert restore_response.status_code == 200

    # Check stage history
    history_response = await async_client.get(
        f"/api/v1/applications/{application.id}/history",
        headers=auth_headers
    )

    assert history_response.status_code == 200
    history_data = history_response.json()
    assert isinstance(history_data, list)
    assert len(history_data) >= 6  # At least 4 moves + reject + restore

    # Check history structure
    for entry in history_data:
        assert "from_stage" in entry
        assert "to_stage" in entry
        assert "actor_type" in entry
        assert "created_at" in entry


@pytest.mark.asyncio
async def test_get_applications_for_vacancy(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession
):
    """Test getting applications for a vacancy"""
    # Create a vacancy
    vacancy_data = {"name": "Test Vacancy for Application List"}
    vacancy_response = await async_client.post(
        "/api/v1/vacancies/",
        headers=auth_headers,
        json=vacancy_data
    )
    vacancy_id = vacancy_response.json()["id"]

    # Create a candidate and application
    candidate = Candidate(
        company_id="00000000-0000-0000-0000-000000000001",
        last_name="Петров",
        first_name="Петр",
        full_name="Петров Петр",
        source="hh",
        phone="+7 905 111 22 33"
    )
    db_session.add(candidate)
    await db_session.flush()

    application = Application(
        company_id="00000000-0000-0000-0000-000000000001",
        candidate_id=candidate.id,
        vacancy_id=vacancy_id,
        stage="response",
        ai_score=75
    )
    db_session.add(application)
    await db_session.commit()

    # Get applications for vacancy
    response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Check application structure
    app_data = data[0]
    assert "id" in app_data
    assert "candidate_id" in app_data
    assert "full_name" in app_data
    assert "stage" in app_data
    assert "ai_score" in app_data
    assert app_data["full_name"] == "Петров Петр"
    assert app_data["ai_score"] == 75


@pytest.mark.asyncio
async def test_bulk_move_applications(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession
):
    """Test bulk moving applications"""
    # Create a vacancy
    vacancy_data = {"name": "Test Vacancy for Bulk Operations"}
    vacancy_response = await async_client.post(
        "/api/v1/vacancies/",
        headers=auth_headers,
        json=vacancy_data
    )
    vacancy_id = vacancy_response.json()["id"]

    # Create multiple candidates and applications
    application_ids = []
    for i in range(3):
        candidate = Candidate(
            company_id="00000000-0000-0000-0000-000000000001",
            last_name=f"Candidate{i}",
            first_name="Test",
            full_name=f"Test Candidate{i}",
            source="manual"
        )
        db_session.add(candidate)
        await db_session.flush()

        application = Application(
            company_id="00000000-0000-0000-0000-000000000001",
            candidate_id=candidate.id,
            vacancy_id=vacancy_id,
            stage="response"
        )
        db_session.add(application)
        await db_session.flush()
        application_ids.append(str(application.id))

    await db_session.commit()

    # Test bulk move
    bulk_response = await async_client.post(
        "/api/v1/applications/bulk/move",
        headers=auth_headers,
        json={
            "application_ids": application_ids,
            "to_stage": "selected"
        }
    )

    assert bulk_response.status_code == 200
    bulk_data = bulk_response.json()
    assert bulk_data["moved_count"] >= 1