"""Сервис для сводки пульса на главной странице"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...core.periods import parse_home_period
from ...models import Employee, PulseSurvey
from ...schemas.home import PulseSummary, AttentionHrItem


async def compute_pulse_summary(session: AsyncSession, company_id: UUID, period: str = 'month') -> PulseSummary:
    """Вычисляет сводку пульса для главной страницы"""
    period_days = parse_home_period(period)
    now = datetime.now(timezone.utc)

    if period_days:
        start_date = now - timedelta(days=period_days)
    else:
        start_date = None

    # 1. Количество сотрудников на адаптации
    onboarding_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.status == 'onboarding'
    )
    if start_date:
        onboarding_query = onboarding_query.where(Employee.start_date >= start_date.date())

    onboarding_result = await session.execute(onboarding_query)
    onboarding_count = onboarding_result.scalar() or 0

    # 2. Дельта по адаптации vs предыдущий месяц
    onboarding_delta = 0
    if period_days:
        prev_start = start_date - timedelta(days=period_days)
        prev_onboarding_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.status == 'onboarding',
            Employee.start_date >= prev_start.date(),
            Employee.start_date < start_date.date()
        )
        prev_result = await session.execute(prev_onboarding_query)
        prev_count = prev_result.scalar() or 0
        onboarding_delta = onboarding_count - prev_count

    # 3. Распределение по уровню риска
    risk_query = select(
        Employee.risk_level,
        func.count(Employee.id)
    ).where(
        Employee.company_id == company_id,
        Employee.status == 'onboarding'
    ).group_by(Employee.risk_level)

    risk_result = await session.execute(risk_query)
    risk_rows = risk_result.fetchall()

    risk_split = {'high': 0, 'mid': 0, 'low': 0}
    for risk_level, count in risk_rows:
        risk_split[risk_level] = count

    # 4. Средняя оценка удовлетворённости
    satisfaction_query = select(func.avg(PulseSurvey.overall_score)).where(
        PulseSurvey.company_id == company_id,
        PulseSurvey.type == 'monthly',
        PulseSurvey.overall_score.is_not(None)
    )
    if start_date:
        satisfaction_query = satisfaction_query.where(PulseSurvey.answered_at >= start_date)

    satisfaction_result = await session.execute(satisfaction_query)
    satisfaction_avg = satisfaction_result.scalar()
    satisfaction_avg = round(satisfaction_avg, 1) if satisfaction_avg else None

    # 5. Процент ответивших на опросы
    if start_date:
        total_surveys_query = select(func.count(PulseSurvey.id)).where(
            PulseSurvey.company_id == company_id,
            PulseSurvey.sent_at >= start_date
        )
        answered_surveys_query = select(func.count(PulseSurvey.id)).where(
            PulseSurvey.company_id == company_id,
            PulseSurvey.sent_at >= start_date,
            PulseSurvey.answered_at.is_not(None)
        )
    else:
        total_surveys_query = select(func.count(PulseSurvey.id)).where(
            PulseSurvey.company_id == company_id
        )
        answered_surveys_query = select(func.count(PulseSurvey.id)).where(
            PulseSurvey.company_id == company_id,
            PulseSurvey.answered_at.is_not(None)
        )

    total_surveys_result = await session.execute(total_surveys_query)
    total_surveys = total_surveys_result.scalar() or 0

    answered_surveys_result = await session.execute(answered_surveys_query)
    answered_surveys = answered_surveys_result.scalar() or 0

    answered_pct = (answered_surveys / total_surveys * 100) if total_surveys > 0 else 0.0

    # 6. Процент молчащих сотрудников
    if start_date:
        silent_employees_query = select(func.count(func.distinct(Employee.id))).where(
            Employee.company_id == company_id,
            Employee.status == 'onboarding',
            ~Employee.id.in_(
                select(PulseSurvey.employee_id).where(
                    PulseSurvey.company_id == company_id,
                    PulseSurvey.sent_at >= start_date
                ).distinct()
            )
        )
        total_employees_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.status == 'onboarding'
        )
    else:
        silent_employees_query = select(func.count(func.distinct(Employee.id))).where(
            Employee.company_id == company_id,
            Employee.status == 'onboarding',
            ~Employee.id.in_(
                select(PulseSurvey.employee_id).where(
                    PulseSurvey.company_id == company_id
                ).distinct()
            )
        )
        total_employees_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.status == 'onboarding'
        )

    silent_result = await session.execute(silent_employees_query)
    silent_count = silent_result.scalar() or 0

    total_employees_result = await session.execute(total_employees_query)
    total_employees = total_employees_result.scalar() or 0

    silent_pct = (silent_count / total_employees * 100) if total_employees > 0 else 0.0

    # 7. eNPS
    # eNPS по опросам типа 'enps' (промоутеры 9-10 минус детракторы 0-6)
    promoters_query = select(func.count(PulseSurvey.id)).where(
        PulseSurvey.company_id == company_id,
        PulseSurvey.type == 'enps',
        PulseSurvey.overall_score >= 9,
        PulseSurvey.answered_at.is_not(None)
    )
    detractors_query = select(func.count(PulseSurvey.id)).where(
        PulseSurvey.company_id == company_id,
        PulseSurvey.type == 'enps',
        PulseSurvey.overall_score <= 6,
        PulseSurvey.answered_at.is_not(None)
    )
    total_enps_query = select(func.count(PulseSurvey.id)).where(
        PulseSurvey.company_id == company_id,
        PulseSurvey.type == 'enps',
        PulseSurvey.answered_at.is_not(None)
    )

    if start_date:
        promoters_query = promoters_query.where(PulseSurvey.answered_at >= start_date)
        detractors_query = detractors_query.where(PulseSurvey.answered_at >= start_date)
        total_enps_query = total_enps_query.where(PulseSurvey.answered_at >= start_date)

    promoters_result = await session.execute(promoters_query)
    promoters = promoters_result.scalar() or 0

    detractors_result = await session.execute(detractors_query)
    detractors = detractors_result.scalar() or 0

    total_enps_result = await session.execute(total_enps_query)
    total_enps = total_enps_result.scalar() or 0

    enps = None
    if total_enps > 0:
        promoters_pct = promoters / total_enps * 100
        detractors_pct = detractors / total_enps * 100
        enps = int(promoters_pct - detractors_pct)

    # 8. Дельта eNPS vs предыдущий период
    enps_delta = None
    if period_days and enps is not None:
        prev_start_enps = start_date - timedelta(days=period_days)

        prev_promoters_query = select(func.count(PulseSurvey.id)).where(
            PulseSurvey.company_id == company_id,
            PulseSurvey.type == 'enps',
            PulseSurvey.overall_score >= 9,
            PulseSurvey.answered_at >= prev_start_enps,
            PulseSurvey.answered_at < start_date
        )
        prev_detractors_query = select(func.count(PulseSurvey.id)).where(
            PulseSurvey.company_id == company_id,
            PulseSurvey.type == 'enps',
            PulseSurvey.overall_score <= 6,
            PulseSurvey.answered_at >= prev_start_enps,
            PulseSurvey.answered_at < start_date
        )
        prev_total_enps_query = select(func.count(PulseSurvey.id)).where(
            PulseSurvey.company_id == company_id,
            PulseSurvey.type == 'enps',
            PulseSurvey.answered_at >= prev_start_enps,
            PulseSurvey.answered_at < start_date
        )

        prev_promoters_result = await session.execute(prev_promoters_query)
        prev_promoters = prev_promoters_result.scalar() or 0

        prev_detractors_result = await session.execute(prev_detractors_query)
        prev_detractors = prev_detractors_result.scalar() or 0

        prev_total_enps_result = await session.execute(prev_total_enps_query)
        prev_total_enps = prev_total_enps_result.scalar() or 0

        if prev_total_enps > 0:
            prev_promoters_pct = prev_promoters / prev_total_enps * 100
            prev_detractors_pct = prev_detractors / prev_total_enps * 100
            prev_enps = int(prev_promoters_pct - prev_detractors_pct)
            enps_delta = enps - prev_enps

    # 9. Требуют внимания HR
    attention_hr = await _compute_attention_hr(session, company_id, now)

    return PulseSummary(
        onboarding_count=onboarding_count,
        onboarding_delta=onboarding_delta,
        risk_split=risk_split,
        satisfaction_avg=satisfaction_avg,
        answered_pct=round(answered_pct, 1),
        silent_pct=round(silent_pct, 1),
        enps=enps,
        enps_delta=enps_delta,
        attention_hr=attention_hr
    )


async def _compute_attention_hr(session: AsyncSession, company_id: UUID, now: datetime) -> list[AttentionHrItem]:
    """Вычисляет список сотрудников, требующих внимания HR"""
    attention_hr = []

    # Получаем всех сотрудников на адаптации
    employees_query = select(Employee).where(
        Employee.company_id == company_id,
        Employee.status == 'onboarding'
    )
    employees_result = await session.execute(employees_query)
    employees = employees_result.scalars().all()

    for employee in employees:
        adapt_day = (now.date() - employee.start_date).days
        signals = []
        max_risk_score = 0

        # Сигнал 1: 2+ пропущенных survey подряд
        recent_surveys_query = select(PulseSurvey).where(
            PulseSurvey.employee_id == employee.id,
            PulseSurvey.sent_at >= now - timedelta(days=14)  # Последние 2 недели
        ).order_by(PulseSurvey.sent_at.desc()).limit(2)

        recent_surveys_result = await session.execute(recent_surveys_query)
        recent_surveys = recent_surveys_result.scalars().all()

        if len(recent_surveys) >= 2:
            unanswered_count = sum(1 for s in recent_surveys if s.answered_at is None)
            if unanswered_count >= 2:
                signals.append('Нет ответов на 2 опроса')
                max_risk_score = max(max_risk_score, 80)

        # Сигнал 2: overall_score < 3 в последнем survey
        last_survey_query = select(PulseSurvey).where(
            PulseSurvey.employee_id == employee.id,
            PulseSurvey.answered_at.is_not(None),
            PulseSurvey.overall_score.is_not(None)
        ).order_by(PulseSurvey.answered_at.desc()).limit(1)

        last_survey_result = await session.execute(last_survey_query)
        last_survey = last_survey_result.scalar_one_or_none()

        if last_survey and last_survey.overall_score < 3:
            signals.append('Низкая оценка')
            max_risk_score = max(max_risk_score, 65)

        # Сигнал 3: 5+ дней без survey для сотрудника со стажем > 14 дней
        if adapt_day > 14:
            last_any_survey_query = select(PulseSurvey).where(
                PulseSurvey.employee_id == employee.id
            ).order_by(PulseSurvey.sent_at.desc()).limit(1)

            last_any_survey_result = await session.execute(last_any_survey_query)
            last_any_survey = last_any_survey_result.scalar_one_or_none()

            if (
                not last_any_survey or
                (now - last_any_survey.sent_at).days > 5
            ):
                signals.append('Долго без опроса')
                max_risk_score = max(max_risk_score, 55)

        # Если есть сигналы, добавляем в список внимания
        if signals:
            reason = signals[0]  # Берём первый (наиболее критичный) сигнал

            attention_hr.append(AttentionHrItem(
                employee_id=employee.id,
                full_name=employee.full_name,
                position=employee.position,
                reason=reason,
                adapt_day=adapt_day,
                risk_score=max_risk_score
            ))

    return attention_hr