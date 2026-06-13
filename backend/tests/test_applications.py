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


async def test_applications_filter_added_period(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test added_period filter - 1 application 40 days ago + 1 fresh; added_period=30d → only fresh"""
    from datetime import datetime, timedelta, timezone

    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = vacancy_response.json()["id"]

    # Create old candidate and application (40 days ago)
    old_candidate = await _make_candidate(db_session, last_name="OldCandidate")
    old_time = datetime.now(timezone.utc) - timedelta(days=40)
    old_application = await _make_application(
        db_session,
        candidate_id=old_candidate.id,
        vacancy_id=vacancy_id,
        created_at=old_time
    )

    # Create fresh candidate and application (5 days ago)
    fresh_candidate = await _make_candidate(db_session, last_name="FreshCandidate")
    fresh_time = datetime.now(timezone.utc) - timedelta(days=5)
    fresh_application = await _make_application(
        db_session,
        candidate_id=fresh_candidate.id,
        vacancy_id=vacancy_id,
        created_at=fresh_time
    )

    await db_session.commit()

    # Filter by 30d period - should return only fresh application
    response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications?added_period=30d",
        headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert "FreshCandidate" in body["items"][0]["full_name"]


async def test_applications_filter_repeat(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test repeat filter - Candidate A with 2 applications + candidate B with 1 application;
    repeat=true → A, repeat=false → B"""

    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = vacancy_response.json()["id"]

    # Create candidate A with 2 applications (repeat candidate)
    candidate_a = await _make_candidate(db_session, last_name="RepeatCandidate")
    app_a1 = await _make_application(
        db_session,
        candidate_id=candidate_a.id,
        vacancy_id=vacancy_id,
        is_repeat=True
    )
    app_a2 = await _make_application(
        db_session,
        candidate_id=candidate_a.id,
        vacancy_id=vacancy_id,
        stage="selected",
        is_repeat=True
    )

    # Create candidate B with 1 application (first time candidate)
    candidate_b = await _make_candidate(db_session, last_name="FirstTimeCandidate")
    app_b1 = await _make_application(
        db_session,
        candidate_id=candidate_b.id,
        vacancy_id=vacancy_id,
        is_repeat=False
    )

    await db_session.commit()

    # Filter for repeat candidates (true) - should return candidate A applications
    repeat_response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications?repeat=true",
        headers=auth_headers
    )
    assert repeat_response.status_code == 200
    repeat_body = repeat_response.json()
    assert repeat_body["total"] == 2
    # All returned applications should be from RepeatCandidate
    assert all("RepeatCandidate" in item["full_name"] for item in repeat_body["items"])

    # Filter for first-time candidates (false) - should return candidate B application
    first_time_response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications?repeat=false",
        headers=auth_headers
    )
    assert first_time_response.status_code == 200
    first_time_body = first_time_response.json()
    assert first_time_body["total"] == 1
    assert "FirstTimeCandidate" in first_time_body["items"][0]["full_name"]


async def test_applications_filter_messenger(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test messenger filter - Candidate with preferred_channel=telegram + another with hh;
    messenger=['telegram'] → only first"""

    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Test Vacancy"},
    )
    vacancy_id = vacancy_response.json()["id"]

    # Create candidate with telegram preferred_channel
    telegram_candidate = await _make_candidate(
        db_session,
        last_name="TelegramCandidate",
        preferred_channel="telegram"
    )
    telegram_app = await _make_application(
        db_session,
        candidate_id=telegram_candidate.id,
        vacancy_id=vacancy_id
    )

    # Create candidate with email preferred_channel
    email_candidate = await _make_candidate(
        db_session,
        last_name="EmailCandidate",
        preferred_channel="email"
    )
    email_app = await _make_application(
        db_session,
        candidate_id=email_candidate.id,
        vacancy_id=vacancy_id
    )

    await db_session.commit()

    # Filter by telegram messenger - should return only telegram candidate
    response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications?messenger=telegram",
        headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert "TelegramCandidate" in body["items"][0]["full_name"]


async def test_applications_filter_ready_relocate(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test ready_relocate JSONB filter - 3 candidates with relocation: true/false/empty;
    ready_relocate=true → 1, ready_relocate=false → 1, no filter → 3"""

    vacancy_response = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Remote Job"},
    )
    vacancy_id = vacancy_response.json()["id"]

    # relocation в extra — СВОБОДНЫЙ ТЕКСТ (как из hh), не bool: фильтр ищет по ilike '%готов%'.
    # Candidate with relocation: ready
    relocate_yes = await _make_candidate(
        db_session,
        last_name="WillRelocate",
        extra={"relocation": "готов к переезду"}
    )
    await _make_application(
        db_session,
        candidate_id=relocate_yes.id,
        vacancy_id=vacancy_id
    )

    # Candidate with relocation: not ready
    relocate_no = await _make_candidate(
        db_session,
        last_name="WontRelocate",
        extra={"relocation": "не готов к переезду"}
    )
    await _make_application(
        db_session,
        candidate_id=relocate_no.id,
        vacancy_id=vacancy_id
    )

    # Candidate without relocation field (empty extra → relocation IS NULL)
    relocate_unknown = await _make_candidate(
        db_session,
        last_name="NoRelocateInfo",
        extra={}
    )
    await _make_application(
        db_session,
        candidate_id=relocate_unknown.id,
        vacancy_id=vacancy_id
    )

    await db_session.commit()

    # Test ready_relocate=true → только явно «готов» (WillRelocate)
    true_response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications?ready_relocate=true",
        headers=auth_headers
    )
    assert true_response.status_code == 200
    true_body = true_response.json()
    assert true_body["total"] == 1
    assert "WillRelocate" in true_body["items"][0]["full_name"]

    # Test ready_relocate=false → «не готов» + неизвестно (NULL) = fail-closed по дизайну фильтра
    false_response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications?ready_relocate=false",
        headers=auth_headers
    )
    assert false_response.status_code == 200
    false_body = false_response.json()
    assert false_body["total"] == 2
    false_names = {item["full_name"] for item in false_body["items"]}
    assert any("WontRelocate" in n for n in false_names)
    assert any("NoRelocateInfo" in n for n in false_names)

    # Test without ready_relocate filter - should return all 3
    all_response = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/applications",
        headers=auth_headers
    )
    assert all_response.status_code == 200
    all_body = all_response.json()
    assert all_body["total"] == 3
