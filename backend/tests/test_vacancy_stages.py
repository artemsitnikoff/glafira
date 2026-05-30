from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VacancyStage, Application


async def test_add_vacancy_stage(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test adding a new stage to vacancy"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Add custom stage
    stage_data = {
        "stage_key": "custom_stage",
        "label": "Кастомный этап",
        "order_index": 10,
        "is_terminal": False
    }

    response = await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
        json=stage_data,
    )
    assert response.status_code == 201
    assert "Этап создан" in response.json()["message"]

    # Verify stage was created
    stage = (
        await db_session.execute(
            select(VacancyStage)
            .where(
                VacancyStage.vacancy_id == vacancy_id,
                VacancyStage.stage_key == "custom_stage"
            )
        )
    ).scalar_one()

    assert stage.label == "Кастомный этап"
    assert stage.order_index == 10
    assert stage.is_terminal == False


async def test_add_stage_duplicate_key_fails(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that adding stage with duplicate key fails"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Try to add stage with existing key "response" (exists in default template)
    stage_data = {
        "stage_key": "response",
        "label": "Дублированный отклик",
        "order_index": 10,
    }

    response = await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
        json=stage_data,
    )
    assert response.status_code == 409
    assert "уже существует" in response.text


async def test_add_stage_invalid_key_fails(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that adding stage with invalid key fails"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Try to add stage with invalid key
    stage_data = {
        "stage_key": "invalid-key-with-dash!",  # Contains dash and exclamation
        "label": "Плохой ключ",
        "order_index": 10,
    }

    response = await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
        json=stage_data,
    )
    assert response.status_code == 422  # Validation error


async def test_rename_vacancy_stage(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test renaming stage (only label changes, stage_key immutable)"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Add custom stage first
    await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
        json={
            "stage_key": "test_stage",
            "label": "Старое название",
            "order_index": 10,
        },
    )

    # Rename stage
    rename_data = {"label": "Новое название"}
    response = await async_client.patch(
        f"/api/v1/vacancies/{vacancy_id}/stages/test_stage",
        headers=auth_headers,
        json=rename_data,
    )
    assert response.status_code == 200
    assert "переименован" in response.json()["message"]

    # Verify stage was renamed but stage_key unchanged
    stage = (
        await db_session.execute(
            select(VacancyStage)
            .where(
                VacancyStage.vacancy_id == vacancy_id,
                VacancyStage.stage_key == "test_stage"
            )
        )
    ).scalar_one()

    assert stage.label == "Новое название"
    assert stage.stage_key == "test_stage"  # stage_key unchanged


async def test_rename_nonexistent_stage_fails(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that renaming nonexistent stage fails"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Try to rename nonexistent stage
    rename_data = {"label": "Новое название"}
    response = await async_client.patch(
        f"/api/v1/vacancies/{vacancy_id}/stages/nonexistent",
        headers=auth_headers,
        json=rename_data,
    )
    assert response.status_code == 404


async def test_delete_empty_custom_stage_succeeds(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test deleting empty custom stage succeeds"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Add custom stage
    await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
        json={
            "stage_key": "deletable_stage",
            "label": "Удаляемый этап",
            "order_index": 10,
        },
    )

    # Delete stage
    response = await async_client.delete(
        f"/api/v1/vacancies/{vacancy_id}/stages/deletable_stage",
        headers=auth_headers,
    )
    assert response.status_code == 204

    # Verify stage was deleted
    stage = (
        await db_session.execute(
            select(VacancyStage)
            .where(
                VacancyStage.vacancy_id == vacancy_id,
                VacancyStage.stage_key == "deletable_stage"
            )
        )
    ).scalar_one_or_none()

    assert stage is None


async def test_delete_protected_stage_fails(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test deleting protected stage fails"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Try to delete protected stage
    for protected_key in ["hired", "rejected", "added", "response"]:
        response = await async_client.delete(
            f"/api/v1/vacancies/{vacancy_id}/stages/{protected_key}",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Системный этап нельзя удалить" in response.text


async def test_delete_nonempty_stage_fails(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_candidate,
):
    """Test deleting stage with applications fails"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Add custom stage
    await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
        json={
            "stage_key": "nonempty_stage",
            "label": "Непустой этап",
            "order_index": 10,
        },
    )

    # Place a candidate on this stage directly (no create-application API endpoint exists)
    application = Application(
        company_id=test_candidate.company_id,
        candidate_id=test_candidate.id,
        vacancy_id=vacancy_id,
        stage="nonempty_stage",
    )
    db_session.add(application)
    await db_session.commit()

    # Try to delete non-empty stage
    response = await async_client.delete(
        f"/api/v1/vacancies/{vacancy_id}/stages/nonempty_stage",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Переместите кандидатов с этапа перед удалением" in response.text


async def test_reorder_stages(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test reordering stages"""
    # Create vacancy with custom stages
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={
            "name": "Test Vacancy",
            "stages": [
                {"stage_key": "first", "label": "Первый", "order_index": 1},
                {"stage_key": "second", "label": "Второй", "order_index": 2},
                {"stage_key": "third", "label": "Третий", "order_index": 3},
            ]
        },
    )
    vacancy_id = created.json()["id"]

    # Reorder stages
    reorder_data = {"order": ["third", "first", "second"]}
    response = await async_client.put(
        f"/api/v1/vacancies/{vacancy_id}/stages/reorder",
        headers=auth_headers,
        json=reorder_data,
    )
    assert response.status_code == 200
    assert "переупорядочены" in response.json()["message"]

    # Verify new order
    stages = (
        await db_session.execute(
            select(VacancyStage.stage_key, VacancyStage.order_index)
            .where(VacancyStage.vacancy_id == vacancy_id)
            .order_by(VacancyStage.order_index)
        )
    ).fetchall()

    expected_order = [("third", 1), ("first", 2), ("second", 3)]
    actual_order = [(row.stage_key, row.order_index) for row in stages]
    assert actual_order == expected_order


async def test_reorder_with_mismatched_stages_fails(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test reordering with wrong stage keys fails"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},  # Uses default template
    )
    vacancy_id = created.json()["id"]

    # Try to reorder with wrong stage keys
    reorder_data = {"order": ["nonexistent1", "nonexistent2"]}
    response = await async_client.put(
        f"/api/v1/vacancies/{vacancy_id}/stages/reorder",
        headers=auth_headers,
        json=reorder_data,
    )
    assert response.status_code == 400
    assert "не соответствуют этапам вакансии" in response.text


async def test_move_application_to_custom_stage_works(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_candidate,
):
    """Test that moving application to custom stage works (proves CHECK removal)"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = created.json()["id"]

    # Add custom stage
    await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
        json={
            "stage_key": "custom_move_target",
            "label": "Кастомный этап для перемещения",
            "order_index": 10,
        },
    )

    # Place a candidate at a standard stage directly (no create-application API endpoint exists)
    application = Application(
        company_id=test_candidate.company_id,
        candidate_id=test_candidate.id,
        vacancy_id=vacancy_id,
        stage="response",
    )
    db_session.add(application)
    await db_session.commit()

    # Move to custom stage - this should work without CHECK violation
    move_response = await async_client.post(
        f"/api/v1/applications/{application.id}/move",
        headers=auth_headers,
        json={"to_stage": "custom_move_target"},
    )
    assert move_response.status_code == 200, move_response.text
    assert move_response.json()["new_stage"] == "custom_move_target"