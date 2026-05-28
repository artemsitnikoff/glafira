import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Application, Candidate, Employee, PulsePlanItem, PulseSurvey, PulseAlert, AuditLog


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


async def test_employees_survey_overdue_days_filter(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test survey_overdue_days filter: 3 employees - one with survey 20 days ago,
    one with no surveys, one with survey 5 days ago. Filter by 14 days should return 2."""
    from app.models import Candidate

    # Employee 1: Survey 20 days ago (overdue for 14 day filter)
    candidate1 = Candidate(
        company_id=admin_user.company_id,
        last_name="OldSurvey",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate1)
    await db_session.flush()

    employee1 = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate1.id,
        full_name="OldSurvey Test",
        start_date=date.today() - timedelta(days=30),
        status="onboarding",
    )
    db_session.add(employee1)
    await db_session.flush()

    # Survey 20 days ago
    survey1 = PulseSurvey(
        company_id=admin_user.company_id,
        employee_id=employee1.id,
        type="weekly",
        sent_at=datetime.now(timezone.utc) - timedelta(days=20),
        answered_at=datetime.now(timezone.utc) - timedelta(days=19),
    )
    db_session.add(survey1)

    # Employee 2: No surveys (should also be considered overdue)
    candidate2 = Candidate(
        company_id=admin_user.company_id,
        last_name="NoSurvey",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate2)
    await db_session.flush()

    employee2 = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate2.id,
        full_name="NoSurvey Test",
        start_date=date.today() - timedelta(days=30),
        status="onboarding",
    )
    db_session.add(employee2)

    # Employee 3: Recent survey 5 days ago (not overdue for 14 day filter)
    candidate3 = Candidate(
        company_id=admin_user.company_id,
        last_name="RecentSurvey",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate3)
    await db_session.flush()

    employee3 = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate3.id,
        full_name="RecentSurvey Test",
        start_date=date.today() - timedelta(days=30),
        status="onboarding",
    )
    db_session.add(employee3)
    await db_session.flush()

    # Recent survey 5 days ago
    survey3 = PulseSurvey(
        company_id=admin_user.company_id,
        employee_id=employee3.id,
        type="weekly",
        sent_at=datetime.now(timezone.utc) - timedelta(days=5),
        answered_at=datetime.now(timezone.utc) - timedelta(days=4),
    )
    db_session.add(survey3)

    await db_session.commit()

    # Test filter survey_overdue_days=14 - should return employee1 and employee2
    response_14d = await async_client.get(
        "/api/v1/pulse/employees?survey_overdue_days=14",
        headers=auth_headers
    )
    assert response_14d.status_code == 200
    body_14d = response_14d.json()
    assert body_14d["total"] == 2
    names_14d = [item["full_name"] for item in body_14d["items"]]
    assert "OldSurvey Test" in names_14d
    assert "NoSurvey Test" in names_14d

    # Test filter survey_overdue_days=30 - should return only employee2 (no surveys)
    response_30d = await async_client.get(
        "/api/v1/pulse/employees?survey_overdue_days=30",
        headers=auth_headers
    )
    assert response_30d.status_code == 200
    body_30d = response_30d.json()
    assert body_30d["total"] == 1
    assert "NoSurvey Test" in body_30d["items"][0]["full_name"]

    # Test without filter - should return all 3
    response_all = await async_client.get(
        "/api/v1/pulse/employees",
        headers=auth_headers
    )
    assert response_all.status_code == 200
    body_all = response_all.json()
    assert body_all["total"] == 3


async def test_patch_employee_status_onboarding_to_passed(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test successful status change from onboarding to passed"""
    from app.models import Candidate

    candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="TestEmployee",
        first_name="Status",
        source="manual",
    )
    db_session.add(candidate)
    await db_session.flush()

    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate.id,
        full_name="TestEmployee Status",
        start_date=date.today() - timedelta(days=30),
        status="onboarding",
    )
    db_session.add(employee)
    await db_session.commit()

    # Update status to passed
    response = await async_client.patch(
        f"/api/v1/pulse/employees/{employee.id}",
        headers=auth_headers,
        json={"status": "passed"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "passed"
    assert data["left_at"] is None
    assert data["left_reason"] is None


async def test_patch_employee_status_to_left_with_required_fields(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test successful status change to left with required fields"""
    from app.models import Candidate

    candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="LeavingEmployee",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate)
    await db_session.flush()

    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate.id,
        full_name="LeavingEmployee Test",
        start_date=date.today() - timedelta(days=30),
        status="passed",
    )
    db_session.add(employee)
    await db_session.commit()

    # Update status to left with required fields
    left_date = date.today()
    response = await async_client.patch(
        f"/api/v1/pulse/employees/{employee.id}",
        headers=auth_headers,
        json={
            "status": "left",
            "left_at": left_date.isoformat(),
            "left_reason": "Found better opportunity"
        }
    )
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "left"
    assert data["left_at"] == left_date.isoformat()
    assert data["left_reason"] == "Found better opportunity"


async def test_patch_employee_status_to_left_without_required_fields(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test validation error when changing to left without required fields"""
    from app.models import Candidate

    candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="ValidateEmployee",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate)
    await db_session.flush()

    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate.id,
        full_name="ValidateEmployee Test",
        start_date=date.today() - timedelta(days=30),
        status="onboarding",
    )
    db_session.add(employee)
    await db_session.commit()

    # Try to change to left without required fields
    response = await async_client.patch(
        f"/api/v1/pulse/employees/{employee.id}",
        headers=auth_headers,
        json={"status": "left"}
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"


async def test_patch_employee_status_from_left_forbidden(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test that changing status from left is forbidden"""
    from app.models import Candidate

    candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="LeftEmployee",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate)
    await db_session.flush()

    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate.id,
        full_name="LeftEmployee Test",
        start_date=date.today() - timedelta(days=30),
        status="left",
        left_at=date.today(),
        left_reason="Personal reasons",
    )
    db_session.add(employee)
    await db_session.commit()

    # Try to change status from left
    response = await async_client.patch(
        f"/api/v1/pulse/employees/{employee.id}",
        headers=auth_headers,
        json={"status": "onboarding"}
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "INVALID_TRANSITION" in error["details"]["code"]


async def test_patch_employee_status_creates_audit_log(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test that status change creates proper audit log entry"""
    from app.models import Candidate, AuditLog

    candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="AuditEmployee",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate)
    await db_session.flush()

    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate.id,
        full_name="AuditEmployee Test",
        start_date=date.today() - timedelta(days=30),
        status="onboarding",
    )
    db_session.add(employee)
    await db_session.commit()

    # Update status
    await async_client.patch(
        f"/api/v1/pulse/employees/{employee.id}",
        headers=auth_headers,
        json={"status": "passed"}
    )

    # Check audit log
    audit_entry = (
        await db_session.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "employee",
                AuditLog.entity_id == employee.id,
                AuditLog.action == "employee_status_change"
            )
        )
    ).scalar_one()

    assert audit_entry is not None
    assert audit_entry.action == "employee_status_change"
    assert audit_entry.changes["before"]["status"] == "onboarding"
    assert audit_entry.changes["after"]["status"] == "passed"


async def test_bulk_run_survey_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test successful bulk survey run for 3 employees"""
    from app.models import Candidate

    # Create 3 employees
    employee_ids = []
    for i in range(3):
        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name=f"BulkSurvey{i}",
            first_name="Test",
            source="manual",
        )
        db_session.add(candidate)
        await db_session.flush()

        employee = Employee(
            company_id=admin_user.company_id,
            candidate_id=candidate.id,
            full_name=f"BulkSurvey{i} Test",
            start_date=date.today() - timedelta(days=30),
            status="onboarding",
        )
        db_session.add(employee)
        await db_session.flush()
        employee_ids.append(str(employee.id))

    await db_session.commit()

    # Count surveys before
    surveys_before = (
        await db_session.execute(select(func.count(PulseSurvey.id)))
    ).scalar_one()

    # Run bulk survey
    response = await async_client.post(
        "/api/v1/pulse/employees/bulk/run-survey",
        headers=auth_headers,
        json={
            "employee_ids": employee_ids,
            "template_key": "weekly_check",
        }
    )
    assert response.status_code == 200

    data = response.json()
    assert data["launched_count"] == 3

    # Count surveys after
    surveys_after = (
        await db_session.execute(select(func.count(PulseSurvey.id)))
    ).scalar_one()

    assert surveys_after == surveys_before + 3


async def test_bulk_run_survey_invalid_employee_id(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test atomic failure - 1 invalid ID among 3 should fail all"""
    from app.models import Candidate
    from uuid import uuid4

    # Create 2 valid employees
    employee_ids = []
    for i in range(2):
        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name=f"AtomicTest{i}",
            first_name="Test",
            source="manual",
        )
        db_session.add(candidate)
        await db_session.flush()

        employee = Employee(
            company_id=admin_user.company_id,
            candidate_id=candidate.id,
            full_name=f"AtomicTest{i} Test",
            start_date=date.today() - timedelta(days=30),
            status="onboarding",
        )
        db_session.add(employee)
        await db_session.flush()
        employee_ids.append(str(employee.id))

    # Add invalid ID
    invalid_id = str(uuid4())
    employee_ids.append(invalid_id)

    await db_session.commit()

    # Count surveys before
    surveys_before = (
        await db_session.execute(select(func.count(PulseSurvey.id)))
    ).scalar_one()

    # Try bulk survey with invalid ID
    response = await async_client.post(
        "/api/v1/pulse/employees/bulk/run-survey",
        headers=auth_headers,
        json={
            "employee_ids": employee_ids,
            "template_key": "weekly_check",
        }
    )
    assert response.status_code == 404

    # Count surveys after - should be unchanged (atomic rollback)
    surveys_after = (
        await db_session.execute(select(func.count(PulseSurvey.id)))
    ).scalar_one()

    assert surveys_after == surveys_before  # No surveys created


async def test_bulk_run_survey_creates_audit_logs(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test that bulk survey creates audit log entries for each survey"""
    from app.models import Candidate, AuditLog

    # Create 3 employees
    employee_ids = []
    for i in range(3):
        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name=f"AuditBulk{i}",
            first_name="Test",
            source="manual",
        )
        db_session.add(candidate)
        await db_session.flush()

        employee = Employee(
            company_id=admin_user.company_id,
            candidate_id=candidate.id,
            full_name=f"AuditBulk{i} Test",
            start_date=date.today() - timedelta(days=30),
            status="onboarding",
        )
        db_session.add(employee)
        await db_session.flush()
        employee_ids.append(str(employee.id))

    await db_session.commit()

    # Run bulk survey
    await async_client.post(
        "/api/v1/pulse/employees/bulk/run-survey",
        headers=auth_headers,
        json={
            "employee_ids": employee_ids,
            "template_key": "team_check",
        }
    )

    # Check audit log entries
    audit_entries = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "survey_run",
                AuditLog.entity_type == "pulse_survey"
            )
        )
    ).scalars().all()

    # Should have exactly 3 audit entries
    assert len(audit_entries) == 3

    # All entries should be for team_check template
    for entry in audit_entries:
        assert entry.changes["after"]["template_key"] == "team_check"
        assert entry.changes["after"]["bulk_operation"] is True


async def test_bulk_run_survey_with_custom_template(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db_session: AsyncSession,
):
    """Test bulk survey with custom template_key stores correctly"""
    from app.models import Candidate

    # Create 1 employee
    candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="CustomTemplate",
        first_name="Test",
        source="manual",
    )
    db_session.add(candidate)
    await db_session.flush()

    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=candidate.id,
        full_name="CustomTemplate Test",
        start_date=date.today() - timedelta(days=30),
        status="onboarding",
    )
    db_session.add(employee)
    await db_session.commit()

    # Run with custom template
    response = await async_client.post(
        "/api/v1/pulse/employees/bulk/run-survey",
        headers=auth_headers,
        json={
            "employee_ids": [str(employee.id)],
            "template_key": "custom_onboarding_survey_v2",
        }
    )
    assert response.status_code == 200

    # Check survey was created with correct template
    survey = (
        await db_session.execute(
            select(PulseSurvey).where(PulseSurvey.employee_id == employee.id)
        )
    ).scalar_one()

    assert survey.template_key == "custom_onboarding_survey_v2"