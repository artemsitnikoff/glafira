"""Analytics: Overview отчёт"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, and_, or_

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.periods import resolve_analytics_window
from ...models import Application, Vacancy
from ...schemas.analytics import AnalyticsResponse, ChartData, KpiCard, TableData, TableColumn
from .common import AnalyticsFilters, compute_delta, apply_vacancy_filter, apply_recruiter_filter


async def _get_open_vacancies(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> tuple[float, float | None]:
    """Количество открытых вакансий"""
    current_query = select(func.count(Vacancy.id)).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'active'
    )

    # Фильтр по recruiter_ids для overview применяется к вакансиям напрямую
    if filters.recruiter_ids:
        current_query = current_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0)

    if not filters.compare:
        return current, None

    # previous = вакансии, которые БЫЛИ active на начало периода
    # Используем тот же подход что в home/kpi.py
    from ...core.periods import ANALYTICS_PERIODS
    period_days = ANALYTICS_PERIODS.get(filters.period)
    if period_days:
        period_start = datetime.now(timezone.utc) - timedelta(days=period_days)
    elif filters.period == 'custom' and filters.date_from:
        period_start = datetime.combine(filters.date_from, datetime.min.time(), tzinfo=timezone.utc)
    else:
        # period='all' или нет date_from при custom — историческое сравнение невозможно
        return current, None

    try:
        previous_query = select(func.count(Vacancy.id)).where(
            Vacancy.company_id == company_id,
            Vacancy.created_at < period_start,
            or_(
                Vacancy.status == 'active',
                and_(Vacancy.status == 'archived', Vacancy.closed_at > period_start.date())
            )
        )
        if filters.recruiter_ids:
            previous_query = previous_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

        previous_result = await session.execute(previous_query)
        previous = float(previous_result.scalar() or 0)
    except Exception as e:
        logger.warning("Failed to compute previous open_vacancies snapshot: %s", e)
        return current, None
    return current, previous


async def _get_applications_count(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> tuple[float, float | None]:
    """Количество откликов за период"""
    start_date, end_date = window

    current_query = select(func.count(Application.id)).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    )

    # Применяем фильтры
    current_query = apply_vacancy_filter(current_query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        current_query = current_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0)

    if not filters.compare:
        return current, None

    # Предыдущий период
    period_days = (end_date - start_date).days
    prev_start = start_date - timedelta(days=period_days)
    prev_end = start_date

    prev_query = select(func.count(Application.id)).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(prev_start, datetime.min.time()),
        Application.created_at < datetime.combine(prev_end, datetime.min.time())
    )

    prev_query = apply_vacancy_filter(prev_query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        prev_query = prev_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    prev_result = await session.execute(prev_query)
    previous = float(prev_result.scalar() or 0)

    return current, previous


async def _get_closed_vacancies(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> tuple[float, float | None]:
    """Количество закрытых вакансий"""
    start_date, end_date = window

    current_query = select(func.count(Vacancy.id)).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.closed_at >= start_date,
        Vacancy.closed_at <= end_date
    )

    if filters.recruiter_ids:
        current_query = current_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0)

    if not filters.compare:
        return current, None

    # Предыдущий период
    period_days = (end_date - start_date).days
    prev_start = start_date - timedelta(days=period_days)
    prev_end = start_date

    prev_query = select(func.count(Vacancy.id)).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.closed_at >= prev_start,
        Vacancy.closed_at < prev_end
    )

    if filters.recruiter_ids:
        prev_query = prev_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    prev_result = await session.execute(prev_query)
    previous = float(prev_result.scalar() or 0)

    return current, previous


async def _get_avg_time_to_hire(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> tuple[float, float | None]:
    """Средний срок найма в днях"""
    start_date, end_date = window

    current_query = select(
        func.avg(func.extract('epoch', Vacancy.closed_at - Vacancy.created_at) / 86400)
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.archive_result == 'hired',
        Vacancy.closed_at >= start_date,
        Vacancy.closed_at <= end_date,
        Vacancy.closed_at.is_not(None)
    )

    if filters.recruiter_ids:
        current_query = current_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0.0)

    if not filters.compare:
        return current, None

    # Предыдущий период
    period_days = (end_date - start_date).days
    prev_start = start_date - timedelta(days=period_days)
    prev_end = start_date

    prev_query = select(
        func.avg(func.extract('epoch', Vacancy.closed_at - Vacancy.created_at) / 86400)
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.archive_result == 'hired',
        Vacancy.closed_at >= prev_start,
        Vacancy.closed_at < prev_end,
        Vacancy.closed_at.is_not(None)
    )

    if filters.recruiter_ids:
        prev_query = prev_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    prev_result = await session.execute(prev_query)
    previous = float(prev_result.scalar() or 0.0)

    return current, previous


async def _get_cost_per_hire(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> tuple[float, float | None]:
    """Стоимость найма (₽) - TODO: нет источника данных"""
    # TODO(post-MVP): source attribution cost
    return None, None


async def _build_dynamics_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Динамика откликов - line chart"""
    start_date, end_date = window

    query = select(
        func.date(Application.created_at).label('date'),
        func.count(Application.id).label('value')
    ).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(func.date(Application.created_at)).order_by('date')

    query = apply_vacancy_filter(query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        query = query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    result = await session.execute(query)
    points = [{'date': str(row.date), 'value': row.value} for row in result]

    return ChartData(
        type='line',
        title='Динамика откликов',
        data={'points': points}
    )


async def _build_stages_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Карта активности воронки - stacked chart"""
    start_date, end_date = window

    stages = [
        ('response', 'Отклик', '#5B6573'),
        ('added', 'Добавлен', '#7E5CF0'),
        ('selected', 'Отобран', '#9AA3AE'),
        ('recruiter', 'Контакт с рекрутёром', '#7AB4F5'),
        ('interview', 'Интервью', '#2A8AF0'),
        ('manager', 'Контакт с менеджером', '#5778E8'),
        ('offer', 'Оффер', '#E0A21A'),
        ('hired', 'Нанят', '#16A34A'),
        ('rejected', 'Отказ', '#DC4646')
    ]

    query = select(
        Application.stage,
        func.count(Application.id).label('count')
    ).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(Application.stage)

    query = apply_vacancy_filter(query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        query = query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    result = await session.execute(query)
    stage_counts = {row.stage: row.count for row in result}

    stages_data = []
    for stage_key, label, color in stages:
        count = stage_counts.get(stage_key, 0)
        stages_data.append({
            'stage_key': stage_key,
            'label': label,
            'color': color,
            'count': count
        })

    return ChartData(
        type='stacked',
        title='Карта активности воронки',
        data={'stages': stages_data}
    )


async def _build_top_vacancies_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Top-5 вакансий по откликам - hbar chart"""
    start_date, end_date = window

    # Упрощенный запрос без сложных JOIN
    basic_query = select(
        Vacancy.name,
        func.count(Application.id).label('value')
    ).join(
        Application, Application.vacancy_id == Vacancy.id
    ).where(
        Vacancy.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    )

    # Применяем фильтры
    if filters.vacancy_ids:
        basic_query = basic_query.where(Vacancy.id.in_(filters.vacancy_ids))

    if filters.recruiter_ids:
        basic_query = basic_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    query = basic_query.group_by(Vacancy.id, Vacancy.name).order_by(func.count(Application.id).desc()).limit(5)

    result = await session.execute(query)
    items = [{'label': row.name, 'value': row.value} for row in result]

    return ChartData(
        type='hbar',
        title='Top-5 вакансий по откликам',
        data={'items': items}
    )


async def build_overview(session: AsyncSession, filters: AnalyticsFilters, company_id: UUID) -> AnalyticsResponse:
    """Строит отчёт Overview"""
    window = resolve_analytics_window(filters.period, filters.date_from, filters.date_to)

    # KPI расчёты
    kpi_funcs = [
        ('open_vacancies', None, _get_open_vacancies, False),
        ('applications_count', None, _get_applications_count, False),
        ('closed_vacancies', None, _get_closed_vacancies, False),
        ('avg_time_to_hire', 'дней', _get_avg_time_to_hire, True),
        ('cost_per_hire', '₽', _get_cost_per_hire, True),
    ]

    kpis = []
    for key, unit, func, lower_is_better in kpi_funcs:
        current, previous = await func(session, company_id, window, filters)

        delta, delta_dir = compute_delta(current, previous, lower_is_better=lower_is_better)

        kpis.append(KpiCard(
            key=key,
            value=current,
            unit=unit,
            delta=delta,
            delta_dir=delta_dir
        ))

    # Charts
    charts = [
        await _build_dynamics_chart(session, company_id, window, filters),
        await _build_stages_chart(session, company_id, window, filters),
        await _build_top_vacancies_chart(session, company_id, window, filters)
    ]

    return AnalyticsResponse(
        report='overview',
        period=filters.period,
        kpis=kpis,
        charts=charts,
        tables=[]
    )