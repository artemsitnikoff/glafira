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
