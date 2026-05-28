from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VacancyStage


async def test_create_vacancy_default_template(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    payload = {
        "name": "Senior Python Developer",
        "city": "Москва",
        "salary_from": 250000,
        "salary_to": 400000,
        "currency": "RUB",
        "funnel_template": "default",
        "positions_count": 2,
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
):
    response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Курьер", "funnel_template": "mass"},
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
):
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Бэкенд-разработчик"},
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
):
    """Test 1: Restore archived vacancy clears archive_result and closed_at"""
    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
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
):
    """Test 2: Restore vacancy creates audit log with vacancy_restore action"""
    from app.models import AuditLog

    # Create vacancy
    created = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy 2"},
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
