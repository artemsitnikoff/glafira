"""Тесты API дедупликации кандидатов.

HTTP — через async_client (httpx ASGITransport, конфтест). Авторизация админа —
через auth_headers; менеджер логинится вручную (пароль Glafira2026!). async_client
делит db_session с тестом (dependency override), поэтому кандидат, созданный
сервисом в тесте, виден API-запросу.
"""

import pytest


@pytest.mark.asyncio
async def test_check_duplicate_api_found(async_client, db_session, admin_user, auth_headers):
    """GET /candidates/check-duplicate находит существующего кандидата"""
    from app.schemas.candidate import CandidateCreate
    from app.services.candidate import create_candidate

    candidate_data = CandidateCreate(
        last_name="Тестов",
        first_name="Тест",
        source="manual",
        phone="+79123456789",
        email="dedup-api@example.com"
    )
    await create_candidate(db_session, candidate_data, admin_user.company_id, admin_user.id)
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/candidates/check-duplicate",
        params={"phone": "+79123456789", "first_name": "Тест", "last_name": "Тестов"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["found"] is True
    assert data["match_count"] == 1
    assert len(data["matches"]) == 1
    assert data["matches"][0]["full_name"] == "Тестов Тест"
    assert data["matches"][0]["match_level"] == "exact"
    assert data["matches"][0]["matched_by"] == "phone"
    # Артефакта 'stage' в ответе быть НЕ должно
    assert "stage" not in data


@pytest.mark.asyncio
async def test_check_duplicate_api_not_found(async_client, auth_headers):
    """GET /candidates/check-duplicate НЕ находит несуществующего кандидата"""
    response = await async_client.get(
        "/api/v1/candidates/check-duplicate",
        params={"phone": "+79999999999"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["found"] is False
    assert data["match_count"] == 0
    assert len(data["matches"]) == 0


@pytest.mark.asyncio
async def test_check_duplicate_api_no_contacts_returns_empty(async_client, auth_headers):
    """GET /candidates/check-duplicate без телефона и email — пустой результат (без запроса БД)"""
    response = await async_client.get(
        "/api/v1/candidates/check-duplicate",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["found"] is False
    assert data["match_count"] == 0
    assert len(data["matches"]) == 0


@pytest.mark.asyncio
async def test_check_duplicate_api_manager_forbidden(async_client, manager_user):
    """GET /candidates/check-duplicate запрещён для роли manager (RBAC)"""
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": manager_user.email, "password": "Glafira2026!"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await async_client.get(
        "/api/v1/candidates/check-duplicate",
        params={"phone": "+79111111111"},
        headers=headers,
    )

    assert response.status_code == 403
    assert "Менеджеры не могут создавать кандидатов" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_create_candidate_api_409_then_force(async_client, auth_headers):
    """POST /candidates: дубль без force → 409; с force_duplicate=true → создаётся"""
    first_candidate = {
        "last_name": "Дублинский",
        "first_name": "Первый",
        "source": "manual",
        "phone": "+79888888888",
    }
    response1 = await async_client.post("/api/v1/candidates", json=first_candidate, headers=auth_headers)
    assert response1.status_code == 201, response1.text

    # Дубль без force → 409
    duplicate_candidate = {
        "last_name": "Дублинский",
        "first_name": "Второй",
        "source": "manual",
        "phone": "+79888888888",
    }
    response2 = await async_client.post("/api/v1/candidates", json=duplicate_candidate, headers=auth_headers)
    assert response2.status_code == 409, response2.text
    body = response2.json()
    assert body["error"]["code"] == "DUPLICATE_CANDIDATE"
    assert body["error"]["details"]["match_count"] >= 1
    assert len(body["error"]["details"]["matches"]) >= 1

    # Дубль с force → 201
    duplicate_candidate["force_duplicate"] = True
    response3 = await async_client.post("/api/v1/candidates", json=duplicate_candidate, headers=auth_headers)
    assert response3.status_code == 201, response3.text
    assert response3.json()["full_name"] == "Дублинский Второй"
