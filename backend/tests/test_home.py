"""Тесты для Home API"""

import pytest
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4

from app.models import Vacancy, Application, Candidate, Event, Employee, PulseSurvey


@pytest.mark.asyncio
async def test_home_kpi_structure_and_keys(async_client, auth_headers):
    """Тест структуры KPI и ключей базовых/расширенных метрик"""
    # Тест базовых метрик
    response = await async_client.get("/api/v1/home/kpi?period=month", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["period"] == "month"
    assert len(data["cards"]) == 6

    expected_keys = {
        "open_vacancies", "closed_vacancies", "avg_time_to_hire",
        "turnover_90d", "active_candidates", "conversion"
    }
    actual_keys = {card["key"] for card in data["cards"]}
    assert actual_keys == expected_keys

    # Проверяем структуру карточки
    for card in data["cards"]:
        assert "key" in card
        assert "value" in card
        assert "delta_dir" in card
        assert card["delta_dir"] in ["up", "down", "up-bad", "down-good", "flat"]

    # Тест расширенных метрик
    response = await async_client.get("/api/v1/home/kpi?period=month&extended=true", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data["cards"]) == 8
    extended_keys = expected_keys.union({"cost_per_hire", "recruiter_response_speed"})
    actual_keys = {card["key"] for card in data["cards"]}
    assert actual_keys == extended_keys


@pytest.mark.asyncio
async def test_home_kpi_period_all_returns_null_deltas(async_client, auth_headers):
    """Тест что period=all возвращает delta=null для всех метрик"""
    response = await async_client.get("/api/v1/home/kpi?period=all", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["period"] == "all"
    for card in data["cards"]:
        assert card["delta"] is None
        assert card["delta_dir"] == "flat"


@pytest.mark.asyncio
async def test_home_kpi_invalid_period_returns_400(async_client, auth_headers):
    """Тест неверного периода"""
    response = await async_client.get("/api/v1/home/kpi?period=bogus", headers=auth_headers)
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_home_attention_detects_urgent_vacancy(async_client, auth_headers, db_session, admin_user):
    """Тест обнаружения urgent вакансии без движения"""
    # Создаём активную вакансию без applications
    vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Тестовая вакансия",
        status="active"
    )
    db_session.add(vacancy)
    await db_session.flush()

    response = await async_client.get("/api/v1/home/attention", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Проверяем что вакансия попала в urgent
    urgent_items = [item for item in data if item["kind"] == "urgent"]
    assert len(urgent_items) >= 1

    urgent_vacancy_ids = [item["vacancy_id"] for item in urgent_items]
    assert str(vacancy.id) in urgent_vacancy_ids

    # Проверяем текст
    urgent_item = next(item for item in urgent_items if item["vacancy_id"] == str(vacancy.id))
    assert "7+ дней" in urgent_item["text"]


@pytest.mark.asyncio
async def test_home_events_returns_recent_sorted_desc(async_client, auth_headers, db_session, admin_user, test_candidate):
    """Тест что события возвращаются в порядке убывания времени"""
    now = datetime.now(timezone.utc)

    # Создаём 3 события с разным временем
    events = []
    for i in range(3):
        event = Event(
            company_id=admin_user.company_id,
            type="new",
            actor_type="human",
            actor_user_id=admin_user.id,
            text=f"Тестовое событие {i}",
            entities=[],
            candidate_id=test_candidate.id,
            created_at=now - timedelta(minutes=i * 10)
        )
        events.append(event)
        db_session.add(event)

    await db_session.flush()

    response = await async_client.get("/api/v1/home/events?limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Проверяем что есть наши события
    assert len(data) >= 3

    # Проверяем порядок (новые первыми)
    our_events = [e for e in data if e["text"].startswith("Тестовое событие")]
    assert len(our_events) == 3

    # События должны идти в порядке убывания времени (свежие первыми)
    timestamps = [datetime.fromisoformat(e["created_at"].replace('Z', '+00:00')) for e in our_events]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_home_pulse_summary_risk_split(async_client, auth_headers, db_session, admin_user):
    """Тест risk_split в pulse summary"""
    # Создаём сотрудников с разным уровнем риска
    employees = []
    for risk_level in ["high", "mid", "low"]:
        # Сначала создаём кандидата
        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name=f"Тест{risk_level}",
            first_name="Сотрудник",
            source="manual"
        )
        db_session.add(candidate)
        await db_session.flush()

        employee = Employee(
            company_id=admin_user.company_id,
            candidate_id=candidate.id,
            full_name=f"Тест {risk_level}",
            start_date=date.today(),
            status="onboarding",
            risk_level=risk_level
        )
        employees.append(employee)
        db_session.add(employee)

    await db_session.flush()

    response = await async_client.get("/api/v1/home/pulse-summary?period=month", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Проверяем risk_split
    risk_split = data["risk_split"]
    assert risk_split["high"] >= 1
    assert risk_split["mid"] >= 1
    assert risk_split["low"] >= 1


@pytest.mark.asyncio
async def test_home_sources_groups_by_source(async_client, auth_headers, db_session, admin_user):
    """Бонусный тест группировки источников"""
    now = datetime.now(timezone.utc)

    # Создаём кандидатов с разными источниками
    sources_data = [
        ("hh", 3),
        ("telegram", 2),
        ("direct", 1)
    ]

    for source, count in sources_data:
        for i in range(count):
            candidate = Candidate(
                company_id=admin_user.company_id,
                last_name=f"Фамилия{source}{i}",
                first_name=f"Имя{source}{i}",
                source=source,
                created_at=now - timedelta(days=5)  # В пределах месячного периода
            )
            db_session.add(candidate)

    await db_session.flush()

    response = await async_client.get("/api/v1/home/sources?period=month", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Проверяем что источники сгруппированы правильно
    sources_dict = {item["source"]: item["count"] for item in data}

    assert sources_dict.get("hh", 0) >= 3
    assert sources_dict.get("telegram", 0) >= 2
    assert sources_dict.get("direct", 0) >= 1

    # Проверяем сортировку по убыванию count
    counts = [item["count"] for item in data]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
async def test_home_kpi_extended_recruiter_response_speed(
    async_client, auth_headers, admin_user, test_candidate, db_session
):
    """Засеить application с известным временем первого ответа → recruiter_response_speed соответствует."""
    from datetime import datetime, timezone, timedelta
    from app.models import Vacancy, Application, Message

    # Создать vacancy через API
    vr = await async_client.post("/api/v1/vacancies", headers=auth_headers, json={"name": "V"})
    vacancy_id = vr.json()["id"]

    # Application создан 10h назад
    now = datetime.now(timezone.utc)
    app_obj = Application(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        vacancy_id=vacancy_id,
        stage="response",
        created_at=now - timedelta(hours=10),
    )
    db_session.add(app_obj)
    await db_session.flush()

    # Первое OUT-сообщение 3h назад (т.е. ответ дан через 7h после отклика)
    msg = Message(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        application_id=app_obj.id,
        direction="out",
        sender_type="recruiter",
        channel="telegram",
        body="Здравствуйте!",
        sent_at=now - timedelta(hours=3),
        created_at=now - timedelta(hours=3),
    )
    db_session.add(msg)
    await db_session.commit()

    # GET /home/kpi?period=month&extended=true
    r = await async_client.get("/api/v1/home/kpi?period=month&extended=true", headers=auth_headers)
    assert r.status_code == 200
    cards = {c["key"]: c for c in r.json()["cards"]}
    assert "recruiter_response_speed" in cards
    speed = cards["recruiter_response_speed"]
    # Ожидаем ~7 часов (с допуском)
    assert speed["value"] is not None, f"value is None; card={speed}"
    assert 6.5 <= speed["value"] <= 7.5, f"expected ~7 hours, got {speed['value']}"
    assert speed["unit"] == "часа"


@pytest.mark.asyncio
async def test_open_vacancies_previous_real(async_client, auth_headers, db_session, admin_user):
    """Тест 1: исторический snapshot для open_vacancies"""
    now = datetime.now(timezone.utc)

    # seed: 2 vacancy created 10 дней назад со status='active' (current = 2)
    ten_days_ago = now - timedelta(days=10)
    for i in range(2):
        vacancy = Vacancy(
            company_id=admin_user.company_id,
            name=f"Old Active Vacancy {i}",
            status='active',
            created_at=ten_days_ago
        )
        db_session.add(vacancy)

    # 1 vacancy created 10 дней назад со status='archived', но closed_at=5 дней назад (была active на начало недели)
    five_days_ago = now - timedelta(days=5)
    archived_vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Recently Archived Vacancy",
        status='archived',
        created_at=ten_days_ago,
        closed_at=five_days_ago.date()
    )
    db_session.add(archived_vacancy)

    await db_session.commit()

    # для period_days=7: current=2 (2 active), previous=3 (2 active + 1 archived что было active неделю назад)
    # delta = current - previous = 2 - 3 = -1
    response = await async_client.get("/api/v1/home/kpi?period=week", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Найти карточку open_vacancies
    open_vacancies_card = None
    for card in data["cards"]:
        if card["key"] == "open_vacancies":
            open_vacancies_card = card
            break

    assert open_vacancies_card is not None, "open_vacancies card not found"
    assert open_vacancies_card["value"] == 2.0  # current=2 (только active)

    # delta = current - previous = 2 - 3 = -1
    assert open_vacancies_card["delta"] == -1.0
    assert open_vacancies_card["delta_dir"] == "down"