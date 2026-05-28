"""Тесты для генерации AI-сводок сотрудников"""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pulse import Employee, PulseSurvey, PulsePlanItem, PulseAlert
from app.models.audit import AuditLog
from app.services.glafira.employee_summary import generate_employee_summary
from app.jobs.regenerate_employee_summaries import regenerate_all_summaries
from app.database import AsyncSessionLocal


@pytest.fixture
async def test_employee_with_survey(admin_user, test_candidate, db_session: AsyncSession):
    """Создаёт сотрудника с отвеченным опросом"""
    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        full_name="Иван Иванов",
        position="Backend Developer",
        start_date=date.today() - timedelta(days=15),
        status="onboarding",
        risk_level="low",
        probation_days=90,
    )
    db_session.add(employee)
    await db_session.flush()

    # Добавим отвеченный опрос
    survey = PulseSurvey(
        company_id=admin_user.company_id,
        employee_id=employee.id,
        type="weekly",
        sent_at=datetime.now(timezone.utc) - timedelta(days=3),
        answered_at=datetime.now(timezone.utc) - timedelta(days=2),
        overall_score=4.5,
        answers=[]
    )
    db_session.add(survey)

    # Добавим план адаптации
    plan_item1 = PulsePlanItem(
        company_id=admin_user.company_id,
        employee_id=employee.id,
        phase="welcome",
        title="Знакомство с командой",
        deadline_day=1,
        responsible="manager",
        is_done=True,
        order_index=1
    )
    plan_item2 = PulsePlanItem(
        company_id=admin_user.company_id,
        employee_id=employee.id,
        phase="month1",
        title="Изучение кодовой базы",
        deadline_day=14,
        responsible="employee",
        is_done=False,
        order_index=2
    )
    db_session.add_all([plan_item1, plan_item2])

    await db_session.commit()
    return employee


@pytest.fixture
async def test_employee_no_surveys(admin_user, test_candidate, db_session: AsyncSession):
    """Создаёт сотрудника без опросов"""
    employee = Employee(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        full_name="Пётр Петров",
        position="Frontend Developer",
        start_date=date.today() - timedelta(days=5),
        status="onboarding",
        risk_level="low",
        probation_days=90,
    )
    db_session.add(employee)
    await db_session.commit()
    return employee


async def test_generate_summary_with_answered_survey(
    test_employee_with_survey, db_session: AsyncSession
):
    """Тест генерации сводки для сотрудника с отвеченным опросом"""

    with patch('app.services.glafira.employee_summary.call_text', new_callable=AsyncMock) as mock_call_text:
        mock_call_text.return_value = "Mocked summary"

        result = await generate_employee_summary(
            session=db_session,
            employee_id=test_employee_with_survey.id,
            company_id=test_employee_with_survey.company_id,
            actor_user_id=None
        )
        await db_session.commit()

        # Проверяем результат
        assert result == "Mocked summary"
        assert mock_call_text.call_count == 1

        # Проверяем, что данные сохранились в БД
        await db_session.refresh(test_employee_with_survey)
        assert test_employee_with_survey.ai_summary == "Mocked summary"
        assert test_employee_with_survey.ai_summary_generated_at is not None

        # Проверяем audit log
        audit_logs = (await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == 'employee_summary_generated',
                AuditLog.entity_id == test_employee_with_survey.id
            )
        )).scalars().all()
        assert len(audit_logs) == 1
        log = audit_logs[0]
        assert log.actor_type == 'ai'
        assert log.actor_user_id is None
        assert log.changes['after']['length'] == len("Mocked summary")
        assert log.changes['after']['has_summary'] is True


async def test_generate_summary_no_answered_surveys(
    test_employee_no_surveys, db_session: AsyncSession
):
    """Тест пропуска генерации для сотрудника без отвеченных опросов"""

    with patch('app.services.glafira.employee_summary.call_text', new_callable=AsyncMock) as mock_call_text:
        mock_call_text.return_value = "Should not be called"

        result = await generate_employee_summary(
            session=db_session,
            employee_id=test_employee_no_surveys.id,
            company_id=test_employee_no_surveys.company_id,
            actor_user_id=None
        )
        await db_session.commit()

        # LLM не должен вызываться
        assert result is None
        assert mock_call_text.call_count == 0

        # Проверяем, что поля очищены
        await db_session.refresh(test_employee_no_surveys)
        assert test_employee_no_surveys.ai_summary is None
        assert test_employee_no_surveys.ai_summary_generated_at is None

        # Проверяем audit log для skip
        audit_logs = (await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == 'employee_summary_skipped',
                AuditLog.entity_id == test_employee_no_surveys.id
            )
        )).scalars().all()
        assert len(audit_logs) == 1


async def test_regenerate_command_imports():
    """Тест что команда корректно импортируется"""

    # Проверяем, что можем импортировать main функцию
    from app.jobs.regenerate_employee_summaries import main
    assert callable(main)


async def test_ai_summary_endpoint(
    async_client: AsyncClient, auth_headers, test_employee_with_survey, db_session: AsyncSession
):
    """Тест POST /api/v1/pulse/employees/{id}/ai-summary"""

    with patch('app.services.glafira.employee_summary.call_text', new_callable=AsyncMock) as mock_call_text:
        mock_call_text.return_value = "Generated via API"

        response = await async_client.post(
            f"/api/v1/pulse/employees/{test_employee_with_survey.id}/ai-summary",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "Generated via API"
        assert data["generated_at"] is not None
        assert mock_call_text.call_count == 1


async def test_audit_log_details(
    test_employee_with_survey, admin_user, db_session: AsyncSession
):
    """Тест детального содержимого audit log"""

    with patch('app.services.glafira.employee_summary.call_text', new_callable=AsyncMock) as mock_call_text:
        mock_call_text.return_value = "Test summary for audit"

        await generate_employee_summary(
            session=db_session,
            employee_id=test_employee_with_survey.id,
            company_id=test_employee_with_survey.company_id,
            actor_user_id=admin_user.id  # Human actor
        )
        await db_session.commit()

        # Проверяем audit log
        audit_logs = (await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == 'employee_summary_generated',
                AuditLog.entity_id == test_employee_with_survey.id
            )
        )).scalars().all()
        assert len(audit_logs) == 1

        log = audit_logs[0]
        assert log.actor_type == 'human'
        assert log.actor_user_id == admin_user.id
        assert log.entity_type == 'employee'
        assert log.changes['after']['length'] == len("Test summary for audit")
        assert log.changes['after']['has_summary'] is True
        assert log.changes['after']['surveys_count'] == 1

        # Проверяем, что полный текст НЕ сохраняется (PII защита)
        assert 'summary_text' not in log.changes['after']
        assert 'Test summary for audit' not in str(log.changes)