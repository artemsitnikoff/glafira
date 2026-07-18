from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VacancyStage


async def test_create_vacancy_default_template(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    default_client: str,
):
    payload = {
        "name": "Senior Python Developer",
        "city": "Москва",
        "salary_from": 250000,
        "salary_to": 400000,
        "currency": "RUB",
        "funnel_template": "default",
        "positions_count": 2,
        "client_id": default_client,
    }

    response = await async_client.post("/api/v1/vacancies", headers=auth_headers, json=payload)
    assert response.status_code == 201, response.text

    data = response.json()
    assert data["name"] == "Senior Python Developer"
    assert data["city"] == "Москва"
    assert data["salary_from"] == 250000
    assert data["salary_to"] == 400000
    assert data["status"] == "active"
    assert data["glafira_mode"] == "A"
    assert data["team"] == []
    assert data["responsible_user"] is None
    assert "message" not in data

    vacancy_id = data["id"]
    count = (
        await db_session.execute(
            select(func.count(VacancyStage.id)).where(VacancyStage.vacancy_id == vacancy_id)
        )
    ).scalar_one()
    assert count == 9


async def test_create_vacancy_mass_template_has_5_stages(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    default_client: str,
):
    response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Курьер", "funnel_template": "mass", "client_id": default_client},
    )
    assert response.status_code == 201, response.text
    vacancy_id = response.json()["id"]

    keys = (
        await db_session.execute(
            select(VacancyStage.stage_key)
            .where(VacancyStage.vacancy_id == vacancy_id)
            .order_by(VacancyStage.order_index)
        )
    ).scalars().all()
    assert keys == ["response", "selected", "interview", "hired", "rejected"]


async def test_list_vacancies_returns_paginated(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    response = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    for field in ("items", "total", "page", "page_size", "pages"):
        assert field in body, body
    assert body["page"] == 1
    assert body["page_size"] == 24
    assert isinstance(body["items"], list)


async def test_get_vacancy_sidebar(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    response = await async_client.get("/api/v1/vacancies/sidebar", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "archived_count" in body
    assert isinstance(body["items"], list)


async def test_get_vacancy_stages(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    default_client: str,
):
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Бэкенд-разработчик", "client_id": default_client},
    )
    vacancy_id = created.json()["id"]

    response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/stages",
        headers=auth_headers,
    )
    assert response.status_code == 200
    stages = response.json()
    assert len(stages) == 9
    for stage in stages:
        assert {"stage_key", "label", "color", "count", "is_terminal"} <= set(stage.keys())


async def test_restore_vacancy_from_archive(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    default_client: str,
):
    """Test 1: Restore archived vacancy clears archive_result and closed_at"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy", "client_id": default_client},
    )
    vacancy_id = created.json()["id"]

    # Archive vacancy
    await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/archive",
        headers=auth_headers,
        json={"result": "hired"},
    )

    # Restore vacancy
    response = await async_client.patch(
        f"/api/v1/vacancies/{vacancy_id}",
        headers=auth_headers,
        json={"status": "active"},
    )
    assert response.status_code == 200

    # Check vacancy is restored with all archive fields cleared
    data = response.json()
    assert data["status"] == "active"
    assert data["archive_result"] is None
    assert data["closed_at"] is None


async def test_restore_vacancy_audit_log(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    default_client: str,
):
    """Test 2: Restore vacancy creates audit log with vacancy_restore action"""
    from app.models import AuditLog

    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy 2", "client_id": default_client},
    )
    vacancy_id = created.json()["id"]

    # Archive vacancy
    await async_client.post(
        f"/api/v1/vacancies/{vacancy_id}/archive",
        headers=auth_headers,
        json={"result": "cancelled"},
    )

    # Restore vacancy
    await async_client.patch(
        f"/api/v1/vacancies/{vacancy_id}",
        headers=auth_headers,
        json={"status": "active"},
    )

    # Check audit log entry was created
    audit_entry = (
        await db_session.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "vacancy",
                AuditLog.entity_id == vacancy_id,
                AuditLog.action == "vacancy_restore"
            )
            .order_by(AuditLog.created_at.desc())
        )
    ).scalar_one_or_none()

    assert audit_entry is not None
    assert audit_entry.action == "vacancy_restore"
    assert audit_entry.changes["before"]["status"] == "archived"
    assert audit_entry.changes["after"]["status"] == "active"
    assert audit_entry.changes["after"]["archive_result"] is None
    assert audit_entry.changes["after"]["closed_at"] is None


async def test_create_vacancy_with_custom_stages(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    default_client: str,
):
    """Test creating vacancy with custom stages"""
    payload = {
        "name": "Custom Pipeline Vacancy",
        "client_id": default_client,
        "stages": [
            {"stage_key": "apply", "label": "Заявка", "order_index": 1, "is_terminal": False},
            {"stage_key": "review", "label": "Рассмотрение", "order_index": 2, "is_terminal": False},
            {"stage_key": "decision", "label": "Решение", "order_index": 3, "is_terminal": False},
            {"stage_key": "success", "label": "Принят", "order_index": 4, "is_terminal": True},
            {"stage_key": "fail", "label": "Отказ", "order_index": 5, "is_terminal": True},
        ]
    }

    response = await async_client.post("/api/v1/vacancies", headers=auth_headers, json=payload)
    assert response.status_code == 201, response.text

    data = response.json()
    assert data["name"] == "Custom Pipeline Vacancy"

    # Check that exactly 5 stages were created with correct data
    vacancy_id = data["id"]
    stages = (
        await db_session.execute(
            select(VacancyStage)
            .where(VacancyStage.vacancy_id == vacancy_id)
            .order_by(VacancyStage.order_index)
        )
    ).scalars().all()

    assert len(stages) == 5
    assert stages[0].stage_key == "apply"
    assert stages[0].label == "Заявка"
    assert stages[0].order_index == 1
    assert stages[0].is_terminal == False

    assert stages[3].stage_key == "success"
    assert stages[3].is_terminal == True
    assert stages[4].stage_key == "fail"
    assert stages[4].is_terminal == True


async def test_create_vacancy_with_template_still_works(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    default_client: str,
):
    """Test backward compatibility - template-based creation still works"""
    payload = {
        "name": "Template Vacancy",
        "funnel_template": "mass",
        "client_id": default_client,
        # No stages provided - should use template
    }

    response = await async_client.post("/api/v1/vacancies", headers=auth_headers, json=payload)
    assert response.status_code == 201, response.text

    data = response.json()
    vacancy_id = data["id"]

    # Should have 5 stages from mass template
    count = (
        await db_session.execute(
            select(func.count(VacancyStage.id)).where(VacancyStage.vacancy_id == vacancy_id)
        )
    ).scalar_one()
    assert count == 5


async def test_create_vacancy_too_few_custom_stages_fails(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test that less than 3 custom stages fails validation"""
    payload = {
        "name": "Invalid Vacancy",
        "stages": [
            {"stage_key": "start", "label": "Начало", "order_index": 1, "is_terminal": False},
            {"stage_key": "end", "label": "Конец", "order_index": 2, "is_terminal": True},
        ]
    }

    response = await async_client.post("/api/v1/vacancies", headers=auth_headers, json=payload)
    assert response.status_code == 422
    assert "Minimum 3 stages required" in response.text
