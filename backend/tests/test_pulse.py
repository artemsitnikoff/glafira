import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Application, Candidate, Employee, PulsePlanItem, PulseSurvey, PulseAlert


async def test_hired_creates_employee_and_plan_idempotent(
    async_client: AsyncClient, auth_headers, admin_user, db_session: AsyncSession,
):
    # Mock plan generation response
    PLAN_RESPONSE = {
        "items": [
            {"phase": "welcome", "title": "Знакомство с командой", "deadline_day": 1, "responsible": "manager"},
            {"phase": "welcome", "title": "Доступы", "deadline_day": 2, "responsible": "hr"},
            {"phase": "month1", "title": "1:1", "deadline_day": 7, "responsible": "manager"},
        ]
    }

    with patch('app.services.glafira.client.call_json', new_callable=AsyncMock) as mock_call_json:
        mock_call_json.return_value = PLAN_RESPONSE

        # 1. Создать вакансию через API
        vac = (await async_client.post(
            "/api/v1/vacancies", headers=auth_headers,
            json={
                "name": "Backend Dev",
                "funnel_template": "default",
                "positions_count": 1,
            },
        )).json()
        vacancy_id = vac["id"]

        # 2. Кандидат + application(stage='response') напрямую
        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name="Тестов", first_name="Иван", source="manual",
        )
        db_session.add(candidate)
        await db_session.flush()
        application = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate.id, vacancy_id=vacancy_id,
            stage="response",
        )
        db_session.add(application)
        await db_session.commit()

        # 3. Move → hired
        r = await async_client.post(
            f"/api/v1/applications/{application.id}/move",
            headers=auth_headers, json={"to_stage": "hired"},
        )
        assert r.status_code == 200, r.text

        # 4. В БД: ровно 1 employee и >=1 plan items
        employees = (await db_session.execute(
            select(Employee).where(Employee.application_id == application.id)
        )).scalars().all()
        assert len(employees) == 1
        employee = employees[0]
        assert employee.status == "onboarding"
        assert employee.start_date == date.today()

        plan_count = (await db_session.execute(
            select(func.count(PulsePlanItem.id)).where(PulsePlanItem.employee_id == employee.id)
        )).scalar_one()
        assert plan_count >= 1
        initial_plan = plan_count

        # 5. Идемпотентность: вызвать создание ещё раз напрямую
        from app.services.pulse.employee import create_employee_from_hire
        # перезагрузить application с relationships
        application = (await db_session.execute(
            select(Application).where(Application.id == application.id)
        )).scalar_one()
        await create_employee_from_hire(
            db_session, application=application,
            company_id=admin_user.company_id, actor_user_id=admin_user.id,
        )
        await db_session.commit()

        # 6. Должен остаться ровно 1 employee и ровно столько же plan items
        employees_after = (await db_session.execute(
            select(Employee).where(Employee.application_id == application.id)
        )).scalars().all()
        assert len(employees_after) == 1
        plan_count_after = (await db_session.execute(
            select(func.count(PulsePlanItem.id)).where(PulsePlanItem.employee_id == employee.id)
        )).scalar_one()
        assert plan_count_after == initial_plan


async def test_adapt_day_computed_from_start_date(
    async_client: AsyncClient, auth_headers, admin_user, test_candidate, db_session: AsyncSession,
):
    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        full_name="Тест Тестов",
        start_date=date.today() - timedelta(days=7),
        status="onboarding", risk_level="low",
    )
    db_session.add(employee)
    await db_session.commit()

    r = await async_client.get(f"/api/v1/pulse/employees/{employee.id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["adapt_day"] == 7


async def test_risk_level_computation(
    async_client: AsyncClient, auth_headers, admin_user, test_candidate, db_session: AsyncSession,
):
    # 2 пропущенных опроса за последние 7 дней → high
    employee = Employee(
        company_id=admin_user.company_id, candidate_id=test_candidate.id,
        full_name="Х", start_date=date.today() - timedelta(days=30),
        status="onboarding", risk_level="low",
    )
    db_session.add(employee)
    await db_session.flush()
    for _ in range(2):
        db_session.add(PulseSurvey(
            company_id=admin_user.company_id,
            employee_id=employee.id, type="weekly",
            sent_at=datetime.now(timezone.utc) - timedelta(days=2),
            answered_at=None,
        ))
    await db_session.commit()
    r = await async_client.get(f"/api/v1/pulse/employees/{employee.id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["risk_level"] == "high"


async def test_dismiss_alert(
    async_client: AsyncClient, auth_headers, admin_user, test_candidate, db_session: AsyncSession,
):
    employee = Employee(
        company_id=admin_user.company_id, candidate_id=test_candidate.id,
        full_name="Х", start_date=date.today(),
        status="onboarding", risk_level="low",
    )
    db_session.add(employee)
    await db_session.flush()
    alert = PulseAlert(
        company_id=admin_user.company_id, employee_id=employee.id,
        level="info",
        title="Test Alert",
        context="Test context",
    )
    db_session.add(alert)
    await db_session.commit()

    r = await async_client.post(f"/api/v1/pulse/alerts/{alert.id}/dismiss", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    # Проверить: в БД is_dismissed=True
    updated_alert = (await db_session.execute(
        select(PulseAlert).where(PulseAlert.id == alert.id)
    )).scalar_one()
    assert updated_alert.is_dismissed is True


async def test_patch_plan_item(
    async_client: AsyncClient, auth_headers, admin_user, test_candidate, db_session: AsyncSession,
):
    employee = Employee(
        company_id=admin_user.company_id, candidate_id=test_candidate.id,
        full_name="Х", start_date=date.today(),
        status="onboarding", risk_level="low",
    )
    db_session.add(employee)
    await db_session.flush()
    item = PulsePlanItem(
        company_id=admin_user.company_id, employee_id=employee.id,
        phase="welcome", title="Доступы", responsible="hr",
        order_index=0,
    )
    db_session.add(item)
    await db_session.commit()

    r = await async_client.patch(
        f"/api/v1/pulse/plan-items/{item.id}",
        headers=auth_headers, json={"is_done": True},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["is_done"] is True
    assert result["done_at"] is not None