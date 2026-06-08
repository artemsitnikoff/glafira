"""Сервис для расчёта KPI пульса"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...core.errors import ValidationError
from ...models import Employee, PulseSurvey
from ...schemas.pulse import PulseKPI


PERIOD_DAYS = {'7d': 7, '30d': 30, '90d': 90, 'all': None}


async def compute_pulse_kpi(session: AsyncSession, company_id: UUID, period: str = '30d') -> PulseKPI:
    """Вычисляет KPI пульса за указанный период"""

    if period not in PERIOD_DAYS:
        raise ValidationError(f"Недопустимый период: {period}")

    days = PERIOD_DAYS[period]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None

    # Количество сотрудников на адаптации.
    # external_source IS NULL: Б24-импортированные сотрудники в Пульс/KPI не входят.
    onboarding_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.external_source.is_(None),
        Employee.status == 'onboarding'
    )
    if cutoff:
        onboarding_query = onboarding_query.where(Employee.start_date >= cutoff.date())

    onboarding_result = await session.execute(onboarding_query)
    onboarding_count = onboarding_result.scalar() or 0

    # Прошли испытательный срок в текущем периоде
    passed_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.external_source.is_(None),
        Employee.status == 'passed'
    )
    if cutoff:
        passed_query = passed_query.where(Employee.updated_at >= cutoff)

    passed_result = await session.execute(passed_query)
    passed_probation = passed_result.scalar() or 0

    # Дельта с предыдущим периодом для прошедших испытательный срок
    passed_probation_delta = 0
    if days:
        prev_cutoff = cutoff - timedelta(days=days)
        prev_passed_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.external_source.is_(None),
            Employee.status == 'passed',
            Employee.updated_at >= prev_cutoff,
            Employee.updated_at < cutoff
        )
        prev_passed_result = await session.execute(prev_passed_query)
        prev_passed = prev_passed_result.scalar() or 0
        passed_probation_delta = passed_probation - prev_passed

    # Ушли в первые 90 дней
    left_90d_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.external_source.is_(None),
        Employee.status == 'left',
        Employee.left_at.is_not(None),
        # left_at и start_date — DATE; в Postgres (date - date) = целое число дней,
        # поэтому сравниваем разность напрямую (EXTRACT(day FROM integer) не существует → 500).
        (Employee.left_at - Employee.start_date) < 90
    )
    if cutoff:
        left_90d_query = left_90d_query.where(Employee.left_at >= cutoff.date())

    left_90d_result = await session.execute(left_90d_query)
    left_in_90d = left_90d_result.scalar() or 0

    # Общее количество нанятых в периоде (для расчёта процента)
    total_hired_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.external_source.is_(None)
    )
    if cutoff:
        total_hired_query = total_hired_query.where(Employee.start_date >= cutoff.date())

    total_hired_result = await session.execute(total_hired_query)
    total_hired = total_hired_result.scalar() or 0

    left_in_90d_pct = (left_in_90d / total_hired * 100) if total_hired > 0 else 0.0

    # eNPS - процент промоутеров (9-10) минус процент детракторов (0-6) по опросам типа 'enps'
    promoters_query = select(func.count(PulseSurvey.id)).where(
        PulseSurvey.company_id == company_id,
        PulseSurvey.type == 'enps',
        PulseSurvey.overall_score >= 9
    )
    if cutoff:
        promoters_query = promoters_query.where(PulseSurvey.answered_at >= cutoff)

    promoters_result = await session.execute(promoters_query)
    promoters = promoters_result.scalar() or 0

    detractors_query = select(func.count(PulseSurvey.id)).where(
        PulseSurvey.company_id == company_id,
        PulseSurvey.type == 'enps',
        PulseSurvey.overall_score <= 6
    )
    if cutoff:
        detractors_query = detractors_query.where(PulseSurvey.answered_at >= cutoff)

    detractors_result = await session.execute(detractors_query)
    detractors = detractors_result.scalar() or 0

    total_enps_query = select(func.count(PulseSurvey.id)).where(
        PulseSurvey.company_id == company_id,
        PulseSurvey.type == 'enps',
        PulseSurvey.answered_at.is_not(None)
    )
    if cutoff:
        total_enps_query = total_enps_query.where(PulseSurvey.answered_at >= cutoff)

    total_enps_result = await session.execute(total_enps_query)
    total_enps = total_enps_result.scalar() or 0

    enps = 0
    if total_enps > 0:
        promoters_pct = promoters / total_enps * 100
        detractors_pct = detractors / total_enps * 100
        enps = int(promoters_pct - detractors_pct)

    return PulseKPI(
        onboarding_count=onboarding_count,
        passed_probation=passed_probation,
        passed_probation_delta=passed_probation_delta,
        left_in_90d=left_in_90d,
        left_in_90d_pct=round(left_in_90d_pct, 1),
        enps=enps,
    )