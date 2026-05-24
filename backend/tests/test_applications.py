import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Application, Candidate


async def _make_candidate(db: AsyncSession, **overrides) -> Candidate:
    defaults = dict(
        company_id=uuid.UUID(settings.DEFAULT_COMPANY_ID),
        last_name="Иванов",
        first_name="Иван",
        source="manual",
    )
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    db.add(candidate)
    await db.flush()
    return candidate


async def _make_application(db: AsyncSession, *, candidate_id, vacancy_id, **overrides) -> Application:
    defaults = dict(
        company_id=uuid.UUID(settings.DEFAULT_COMPANY_ID),
        candidate_id=candidate_id,
        vacancy_id=vacancy_id,
        stage="response",
    )
    defaults.update(overrides)
    application = Application(**defaults)
    db.add(application)
    await db.flush()
    return application


async def test_application_move_and_reject_lifecycle(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Backend Developer"},
    )
    vacancy_id = vacancy_response.json()["id"]

    candidate = await _make_candidate(db_session)
    application = await _make_application(
        db_session, candidate_id=candidate.id, vacancy_id=vacancy_id
    )
    await db_session.commit()

    for stage in ("added", "selected", "recruiter", "interview"):
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/move",
            headers=auth_headers,
            json={"to_stage": stage},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["new_stage"] == stage

    reject = await async_client.post(
        f"/api/v1/applications/{application.id}/reject",
        headers=auth_headers,
        json={"reason": "Не подходит по опыту", "side": "company"},
    )
    assert reject.status_code == 200, reject.text

    history = await async_client.get(
        f"/api/v1/applications/{application.id}/history",
        headers=auth_headers,
    )
    assert history.status_code == 200
    items = history.json()
    assert len(items) == 5  # 4 moves + 1 reject
    assert items[0]["to_stage"] == "rejected"
    assert items[0]["reason"] == "Не подходит по опыту"
    assert items[0]["actor_type"] == "human"

    restore = await async_client.post(
        f"/api/v1/applications/{application.id}/restore",
        headers=auth_headers,
    )
    assert restore.status_code == 200, restore.text
    assert restore.json()["new_stage"] == "interview"

    history_after = (
        await async_client.get(
            f"/api/v1/applications/{application.id}/history",
            headers=auth_headers,
        )
    ).json()
    assert len(history_after) == 6


async def test_get_applications_for_vacancy_paginated(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Курьер", "funnel_template": "mass"},
    )
    vacancy_id = vacancy_response.json()["id"]

    candidate = await _make_candidate(db_session, last_name="Петров", first_name="Пётр", source="hh")
    await _make_application(
        db_session, candidate_id=candidate.id, vacancy_id=vacancy_id, ai_score=75
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 24
    assert len(body["items"]) == 1

    row = body["items"][0]
    assert row["full_name"] == "Петров Пётр"
    assert row["ai_score"] == 75
    assert row["stage"] == "response"
    assert row["has_pdn"] is False
    assert row["messengers"] == []
    assert row["stage_color"]


async def test_bulk_move_applications(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Менеджер по продажам"},
    )
    vacancy_id = vacancy_response.json()["id"]

    ids = []
    for i in range(3):
        candidate = await _make_candidate(
            db_session,
            last_name=f"Candidate{i}",
        )
        application = await _make_application(
            db_session, candidate_id=candidate.id, vacancy_id=vacancy_id
        )
        ids.append(str(application.id))
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/applications/bulk/move",
        headers=auth_headers,
        json={"application_ids": ids, "to_stage": "selected"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["moved_count"] == 3
