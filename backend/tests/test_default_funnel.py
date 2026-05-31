"""Tests for company default funnel stages"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import CompanyDefaultStage, Vacancy, VacancyStage


@pytest.mark.asyncio
async def test_get_default_funnel_autoprovisions(
    async_client: AsyncClient,
    admin_token: str,
):
    """GET /settings/default-funnel: «пустого дефолта» не существует.

    Если у компании нет этапов (0 строк), эндпоинт провижинит базовую воронку из core STAGES
    (включая защищённые hired/rejected/added/response). Инвариант непустоты + идемпотентность.
    """
    response = await async_client.get(
        "/api/v1/settings/default-funnel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    # Авто-провижининг базовой воронки (9 этапов в порядке order_index)
    keys = [s["stage_key"] for s in data]
    assert keys == [
        "response", "added", "selected", "recruiter",
        "interview", "manager", "offer", "hired", "rejected"
    ]
    # Защищённые этапы присутствуют — воронку нельзя опустошить
    assert {"hired", "rejected", "added", "response"}.issubset(set(keys))

    # Идемпотентность: повторный вызов не плодит дубли
    response2 = await async_client.get(
        "/api/v1/settings/default-funnel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response2.status_code == 200
    assert len(response2.json()) == 9


@pytest.mark.asyncio
async def test_create_default_stage(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test POST /settings/default-funnel creates new stage"""
    response = await async_client.post(
        "/api/v1/settings/default-funnel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "stage_key": "custom_stage",
            "label": "Custom Stage",
            "order_index": 1,
            "is_terminal": False
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["stage_key"] == "custom_stage"
    assert data["label"] == "Custom Stage"
    assert data["order_index"] == 1
    assert data["is_terminal"] is False
    assert "color" in data

    # Verify in database
    result = await db_session.execute(
        select(CompanyDefaultStage).where(CompanyDefaultStage.stage_key == "custom_stage")
    )
    stage = result.scalar_one_or_none()
    assert stage is not None
    assert stage.label == "Custom Stage"


@pytest.mark.asyncio
async def test_create_duplicate_stage_key(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test creating stage with duplicate stage_key fails"""
    # Create first stage
    stage = CompanyDefaultStage(
        company_id=default_company_id,
        stage_key="existing",
        label="Existing Stage",
        order_index=1,
        is_terminal=False
    )
    db_session.add(stage)
    await db_session.commit()

    # Try to create duplicate
    response = await async_client.post(
        "/api/v1/settings/default-funnel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "stage_key": "existing",
            "label": "Another Stage",
            "order_index": 2
        }
    )

    assert response.status_code == 409  # ConflictError


@pytest.mark.asyncio
async def test_create_invalid_stage_key(
    async_client: AsyncClient,
    admin_token: str,
):
    """Test creating stage with invalid stage_key fails"""
    response = await async_client.post(
        "/api/v1/settings/default-funnel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "stage_key": "Invalid-Key!",  # Contains invalid characters
            "label": "Invalid Stage",
            "order_index": 1
        }
    )

    assert response.status_code == 422  # ValidationError


@pytest.mark.asyncio
async def test_update_default_stage(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test PATCH /settings/default-funnel/{stage_key} updates stage label"""
    # Create stage
    stage = CompanyDefaultStage(
        company_id=default_company_id,
        stage_key="test_stage",
        label="Original Label",
        order_index=1,
        is_terminal=False
    )
    db_session.add(stage)
    await db_session.commit()

    # Update label
    response = await async_client.patch(
        "/api/v1/settings/default-funnel/test_stage",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "label": "Updated Label"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Updated Label"
    assert data["stage_key"] == "test_stage"  # Unchanged

    # Verify in database
    await db_session.refresh(stage)
    assert stage.label == "Updated Label"


@pytest.mark.asyncio
async def test_delete_custom_stage(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test DELETE /settings/default-funnel/{stage_key} deletes custom stage"""
    # Create custom stage
    stage = CompanyDefaultStage(
        company_id=default_company_id,
        stage_key="custom_to_delete",
        label="Custom Stage",
        order_index=1,
        is_terminal=False
    )
    db_session.add(stage)
    await db_session.commit()

    # Delete stage
    response = await async_client.delete(
        "/api/v1/settings/default-funnel/custom_to_delete",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Этап удален"

    # Verify deleted from database
    result = await db_session.execute(
        select(CompanyDefaultStage).where(CompanyDefaultStage.stage_key == "custom_to_delete")
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_protected_stage(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test DELETE protected stage fails"""
    # Create protected stage
    stage = CompanyDefaultStage(
        company_id=default_company_id,
        stage_key="hired",  # Protected key
        label="Hired Stage",
        order_index=1,
        is_terminal=True
    )
    db_session.add(stage)
    await db_session.commit()

    # Try to delete protected stage
    response = await async_client.delete(
        "/api/v1/settings/default-funnel/hired",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 422  # ValidationError


@pytest.mark.asyncio
async def test_reorder_default_stages(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test PUT /settings/default-funnel/reorder changes stage order"""
    # Create stages
    stages = [
        CompanyDefaultStage(company_id=default_company_id, stage_key="stage_a", label="Stage A", order_index=1, is_terminal=False),
        CompanyDefaultStage(company_id=default_company_id, stage_key="stage_b", label="Stage B", order_index=2, is_terminal=False),
        CompanyDefaultStage(company_id=default_company_id, stage_key="stage_c", label="Stage C", order_index=3, is_terminal=False),
    ]
    for stage in stages:
        db_session.add(stage)
    await db_session.commit()

    # Reorder: c, a, b
    response = await async_client.put(
        "/api/v1/settings/default-funnel/reorder",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "order": ["stage_c", "stage_a", "stage_b"]
        }
    )

    assert response.status_code == 200

    # Verify new order
    result = await db_session.execute(
        select(CompanyDefaultStage).order_by(CompanyDefaultStage.order_index)
    )
    ordered_stages = list(result.scalars().all())
    assert len(ordered_stages) == 3
    assert ordered_stages[0].stage_key == "stage_c"
    assert ordered_stages[1].stage_key == "stage_a"
    assert ordered_stages[2].stage_key == "stage_b"


@pytest.mark.asyncio
async def test_create_vacancy_uses_default_stages(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
    admin_user,
):
    """Test creating vacancy uses company default stages when available"""
    # Create company default stages
    default_stages = [
        CompanyDefaultStage(company_id=default_company_id, stage_key="stage_1", label="Custom Stage 1", order_index=1, is_terminal=False),
        CompanyDefaultStage(company_id=default_company_id, stage_key="stage_2", label="Custom Stage 2", order_index=2, is_terminal=False),
        CompanyDefaultStage(company_id=default_company_id, stage_key="hired", label="Hired", order_index=3, is_terminal=True),
    ]
    for stage in default_stages:
        db_session.add(stage)
    await db_session.commit()

    # Create vacancy without custom stages
    response = await async_client.post(
        "/api/v1/vacancies",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test Vacancy",
            "team": [str(admin_user.id)],
            "funnel_template": "default"
        }
    )

    assert response.status_code == 201
    vacancy_id = response.json()["id"]

    # Verify vacancy stages match company default stages
    result = await db_session.execute(
        select(VacancyStage)
        .where(VacancyStage.vacancy_id == vacancy_id)
        .order_by(VacancyStage.order_index)
    )
    vacancy_stages = list(result.scalars().all())

    assert len(vacancy_stages) == 3
    assert vacancy_stages[0].stage_key == "stage_1"
    assert vacancy_stages[0].label == "Custom Stage 1"
    assert vacancy_stages[1].stage_key == "stage_2"
    assert vacancy_stages[1].label == "Custom Stage 2"
    assert vacancy_stages[2].stage_key == "hired"
    assert vacancy_stages[2].is_terminal is True


@pytest.mark.asyncio
async def test_create_vacancy_fallback_to_template(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    admin_user,
):
    """Test creating vacancy falls back to template when no default stages"""
    # Ensure no default stages exist (clean test)

    # Create vacancy without custom stages and no company defaults
    response = await async_client.post(
        "/api/v1/vacancies",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test Vacancy",
            "team": [str(admin_user.id)],
            "funnel_template": "default"
        }
    )

    assert response.status_code == 201
    vacancy_id = response.json()["id"]

    # Verify vacancy stages match template (from STAGES)
    result = await db_session.execute(
        select(VacancyStage)
        .where(VacancyStage.vacancy_id == vacancy_id)
        .order_by(VacancyStage.order_index)
    )
    vacancy_stages = list(result.scalars().all())

    # Should have stages from template (response, added, selected, etc.)
    assert len(vacancy_stages) == 9  # Default template has 9 stages
    assert vacancy_stages[0].stage_key == "response"
    assert vacancy_stages[1].stage_key == "added"