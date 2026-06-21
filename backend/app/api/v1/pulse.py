"""Pulse API endpoints"""

from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...schemas.base import Paginated, StatusResult
from ...schemas.pulse import (
    EmployeeListItem, EmployeeDetail, PulseKPI, EmployeeSummaryResponse,
    AlertOut, PlanItemOut, PlanItemUpdate,
    SurveyOut, SurveyCreate, NoteCreate,
    EmployeeStatusUpdate, BulkRunSurveyRequest, BulkRunSurveyResult,
)
from ...services.pulse import employee as employee_svc
from ...services.pulse import kpi as kpi_svc
from ...services.pulse import alerts as alerts_svc
from ...services.pulse import plan as plan_svc
from ...services.pulse import surveys as surveys_svc
from ...services.glafira.employee_summary import generate_employee_summary
from ...core.errors import ForbiddenError

router = APIRouter()


# ---------------------------------------------------------------------------
# Вспомогательная проверка: может ли текущий пользователь (manager) работать
# с конкретным сотрудником. admin/recruiter — без ограничений.
# ---------------------------------------------------------------------------

async def _assert_employee_access(
    session,
    employee_id: UUID,
    current_user: User,
    company_id: UUID,
) -> None:
    """Бросает ForbiddenError, если manager пытается обратиться к чужому сотруднику."""
    if current_user.role == "manager" and not await employee_svc.is_employee_managed_by(
        session, employee_id, current_user.id, company_id
    ):
        raise ForbiddenError("Нет доступа к этому сотруднику")


@router.get("/kpi", response_model=PulseKPI)
async def get_kpi(
    period: str = Query("30d"),  # 7d|30d|90d|all
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить KPI пульса"""
    manager_user_id = current_user.id if current_user.role == "manager" else None
    return await kpi_svc.compute_pulse_kpi(session, company_id, period, manager_user_id=manager_user_id)


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    dismissed: bool | None = Query(None),
    period_days: int | None = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить список алертов"""
    manager_user_id = current_user.id if current_user.role == "manager" else None
    return await alerts_svc.list_alerts(
        session, company_id, dismissed=dismissed, period_days=period_days,
        manager_user_id=manager_user_id,
    )


@router.post("/alerts/{alert_id}/dismiss", response_model=StatusResult)
async def dismiss_alert(
    alert_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Отметить алерт как просмотренный"""
    # Для manager: проверяем, что алерт принадлежит одному из его сотрудников.
    if current_user.role == "manager":
        from sqlalchemy import select
        from ...models import PulseAlert
        alert_row = (await session.execute(
            select(PulseAlert).where(
                PulseAlert.id == alert_id,
                PulseAlert.company_id == company_id,
            )
        )).scalar_one_or_none()
        if alert_row is not None:
            # Алерт существует — проверяем доступ по employee_id
            if not await employee_svc.is_employee_managed_by(
                session, alert_row.employee_id, current_user.id, company_id
            ):
                raise ForbiddenError("Нет доступа к этому сотруднику")
        # Если alert_row is None — штатный NotFoundError выбросит сервис

    await alerts_svc.dismiss_alert(
        session,
        alert_id=alert_id,
        company_id=company_id,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return {"status": "success"}


@router.patch("/plan-items/{item_id}", response_model=PlanItemOut)
async def patch_plan_item(
    item_id: UUID,
    data: PlanItemUpdate,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить пункт плана адаптации"""
    # Для manager: проверяем, что план-айтем принадлежит его сотруднику.
    if current_user.role == "manager":
        from sqlalchemy import select
        from ...models import PulsePlanItem
        item_row = (await session.execute(
            select(PulsePlanItem).where(
                PulsePlanItem.id == item_id,
                PulsePlanItem.company_id == company_id,
            )
        )).scalar_one_or_none()
        if item_row is not None:
            if not await employee_svc.is_employee_managed_by(
                session, item_row.employee_id, current_user.id, company_id
            ):
                raise ForbiddenError("Нет доступа к этому сотруднику")
        # Если item_row is None — штатный NotFoundError выбросит сервис

    result = await plan_svc.patch_plan_item(
        session,
        item_id=item_id,
        data=data,
        company_id=company_id,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.get("/employees", response_model=Paginated[EmployeeListItem])
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    manager_user_id: UUID | None = Query(None),
    department: str | None = Query(None),
    risk_level: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    survey_overdue_days: int | None = Query(None),
    q: str | None = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить список сотрудников с фильтрацией и пагинацией"""
    # Для manager — принудительно подставляем его id, игнорируя query-параметр.
    effective_manager_id = current_user.id if current_user.role == "manager" else manager_user_id
    return await employee_svc.list_employees_paginated(
        session,
        company_id,
        page=page,
        page_size=page_size,
        manager_user_id=effective_manager_id,
        department=department,
        risk_level=risk_level,
        status_filter=status_filter,
        survey_overdue_days=survey_overdue_days,
        q=q,
    )


@router.get("/employees/{employee_id}", response_model=EmployeeDetail)
async def get_employee(
    employee_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить подробную информацию о сотруднике"""
    await _assert_employee_access(session, employee_id, current_user, company_id)

    employee = await employee_svc.get_employee(session, employee_id, company_id)

    # Compute dynamic fields
    adapt_day = employee_svc.compute_adapt_day(employee.start_date)
    risk_level = await employee_svc.compute_risk_level(session, employee)

    # Convert notes from JSONB to schema format
    notes = []
    for note in (employee.notes or []):
        if isinstance(note, dict) and 'text' in note:
            notes.append({
                "text": note.get("text", ""),
                "author_user_id": note.get("author_user_id", ""),
                "created_at": note.get("created_at", ""),
            })

    return EmployeeDetail(
        id=employee.id,
        full_name=employee.full_name,
        position=employee.position,
        department=employee.department,
        start_date=employee.start_date,
        probation_days=employee.probation_days,
        adapt_day=adapt_day,
        status=employee.status,
        risk_level=risk_level,
        enps=employee.enps,
        manager_full_name=employee.manager_user.full_name if employee.manager_user else None,
        recruiter_full_name=employee.recruiter_user.full_name if employee.recruiter_user else None,
        hire_source=employee.hire_source,
        candidate_id=employee.candidate_id,
        left_at=employee.left_at,
        left_reason=employee.left_reason,
        ai_summary=employee.ai_summary,
        ai_summary_generated_at=employee.ai_summary_generated_at,
        plan=[PlanItemOut.model_validate(item) for item in employee.plan_items],
        surveys=[SurveyOut.model_validate(survey) for survey in employee.surveys],
        alerts=[AlertOut.model_validate(alert) for alert in employee.alerts],
        notes=notes,
    )


@router.patch("/employees/{employee_id}", response_model=EmployeeDetail)
async def update_employee_status(
    employee_id: UUID,
    data: EmployeeStatusUpdate,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить статус сотрудника"""
    await _assert_employee_access(session, employee_id, current_user, company_id)

    employee = await employee_svc.update_employee_status(
        session, employee_id, data, company_id, current_user.id
    )
    await session.commit()

    # Return updated employee detail
    adapt_day = employee_svc.compute_adapt_day(employee.start_date)
    risk_level = await employee_svc.compute_risk_level(session, employee)

    # Convert notes from JSONB to schema format
    notes = []
    for note in (employee.notes or []):
        if isinstance(note, dict) and 'text' in note:
            notes.append({
                "text": note.get("text", ""),
                "author_user_id": note.get("author_user_id", ""),
                "created_at": note.get("created_at", ""),
            })

    return EmployeeDetail(
        id=employee.id,
        full_name=employee.full_name,
        position=employee.position,
        department=employee.department,
        start_date=employee.start_date,
        probation_days=employee.probation_days,
        adapt_day=adapt_day,
        status=employee.status,
        risk_level=risk_level,
        enps=employee.enps,
        manager_full_name=employee.manager_user.full_name if employee.manager_user else None,
        recruiter_full_name=employee.recruiter_user.full_name if employee.recruiter_user else None,
        hire_source=employee.hire_source,
        candidate_id=employee.candidate_id,
        left_at=employee.left_at,
        left_reason=employee.left_reason,
        ai_summary=employee.ai_summary,
        ai_summary_generated_at=employee.ai_summary_generated_at,
        plan=[PlanItemOut.model_validate(item) for item in employee.plan_items],
        surveys=[SurveyOut.model_validate(survey) for survey in employee.surveys],
        alerts=[AlertOut.model_validate(alert) for alert in employee.alerts],
        notes=notes,
    )


@router.get("/employees/{employee_id}/plan", response_model=list[PlanItemOut])
async def get_employee_plan(
    employee_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить план адаптации сотрудника"""
    await _assert_employee_access(session, employee_id, current_user, company_id)

    employee = await employee_svc.get_employee(session, employee_id, company_id)
    return [PlanItemOut.model_validate(item) for item in employee.plan_items]


@router.get("/employees/{employee_id}/surveys", response_model=list[SurveyOut])
async def list_employee_surveys(
    employee_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить список опросов сотрудника"""
    await _assert_employee_access(session, employee_id, current_user, company_id)

    surveys = await surveys_svc.list_employee_surveys(session, employee_id, company_id)
    return [SurveyOut.model_validate(survey) for survey in surveys]


@router.post("/employees/{employee_id}/surveys", response_model=SurveyOut, status_code=201)
async def launch_employee_survey(
    employee_id: UUID,
    data: SurveyCreate,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Запустить опрос для сотрудника по выбранному шаблону.

    Снапшотит вопросы шаблона и генерит публичный токен (ссылку для респондента).
    Реальной отправки пока нет — HR копирует ссылку из ответа (public_token) вручную.
    """
    await _assert_employee_access(session, employee_id, current_user, company_id)

    survey = await surveys_svc.launch_survey(
        session, employee_id, data.template_id, company_id, current_user.id
    )
    await session.commit()
    return SurveyOut.model_validate(survey)


@router.post("/employees/bulk/run-survey", response_model=BulkRunSurveyResult)
async def bulk_run_survey(
    data: BulkRunSurveyRequest,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Запуск опросов для группы сотрудников"""
    # Для manager: все запрошенные employee_ids должны принадлежать ему (fail-closed).
    if current_user.role == "manager" and data.employee_ids:
        from sqlalchemy import select
        allowed_ids_result = await session.execute(
            select(employee_svc.Employee.id).where(
                employee_svc.Employee.id.in_(data.employee_ids),
                employee_svc.Employee.manager_user_id == current_user.id,
                employee_svc.Employee.company_id == company_id,
            )
        )
        allowed_ids = {row[0] for row in allowed_ids_result.all()}
        requested_ids = set(data.employee_ids)
        if not requested_ids.issubset(allowed_ids):
            raise ForbiddenError("Нет доступа к одному или нескольким из указанных сотрудников")

    result = await surveys_svc.bulk_run_survey(
        session, data, company_id, current_user.id
    )
    await session.commit()
    return result


@router.post("/employees/{employee_id}/note", response_model=EmployeeDetail)
async def add_employee_note(
    employee_id: UUID,
    data: NoteCreate,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Добавить заметку к сотруднику"""
    await _assert_employee_access(session, employee_id, current_user, company_id)

    employee = await employee_svc.add_note(
        session,
        employee_id=employee_id,
        text=data.text,
        company_id=company_id,
        actor_user_id=current_user.id,
    )
    await session.commit()

    # Return updated employee detail
    adapt_day = employee_svc.compute_adapt_day(employee.start_date)
    risk_level = await employee_svc.compute_risk_level(session, employee)

    # Convert notes from JSONB to schema format
    notes = []
    for note in (employee.notes or []):
        if isinstance(note, dict) and 'text' in note:
            notes.append({
                "text": note.get("text", ""),
                "author_user_id": note.get("author_user_id", ""),
                "created_at": note.get("created_at", ""),
            })

    return EmployeeDetail(
        id=employee.id,
        full_name=employee.full_name,
        position=employee.position,
        department=employee.department,
        start_date=employee.start_date,
        probation_days=employee.probation_days,
        adapt_day=adapt_day,
        status=employee.status,
        risk_level=risk_level,
        enps=employee.enps,
        manager_full_name=employee.manager_user.full_name if employee.manager_user else None,
        recruiter_full_name=employee.recruiter_user.full_name if employee.recruiter_user else None,
        hire_source=employee.hire_source,
        plan=[PlanItemOut.model_validate(item) for item in employee.plan_items],
        surveys=[SurveyOut.model_validate(survey) for survey in employee.surveys],
        alerts=[AlertOut.model_validate(alert) for alert in employee.alerts],
        notes=notes,
    )


@router.post("/employees/{employee_id}/ai-summary", response_model=EmployeeSummaryResponse)
async def regenerate_summary(
    employee_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Регенерировать AI-сводку для сотрудника"""
    # Проверяем ПЕРЕД вызовом AI, чтобы менеджер не жёг токены на чужом сотруднике.
    await _assert_employee_access(session, employee_id, current_user, company_id)

    await generate_employee_summary(
        session=session,
        employee_id=employee_id,
        company_id=company_id,
        actor_user_id=current_user.id
    )
    await session.commit()

    # Reload employee для получения свежих данных
    employee = await employee_svc.get_employee(session, employee_id, company_id)

    return EmployeeSummaryResponse(
        summary=employee.ai_summary,
        generated_at=employee.ai_summary_generated_at
    )
