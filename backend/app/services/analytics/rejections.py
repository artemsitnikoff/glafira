"""Analytics: Rejections отчёт"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.periods import resolve_analytics_window
from ...models import Application, Vacancy, RejectReason
from ...schemas.analytics import AnalyticsResponse, ChartData, TableData, TableColumn
from .common import AnalyticsFilters, apply_vacancy_filter


async def _build_rejections_pie_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Pie charts: отказы наши vs кандидатов"""
    start_date, end_date = window

    # Отказы с нашей стороны (company)
    our_query = select(
        Application.reject_reason,
        func.count(Application.id).label('count')
    ).where(
        Application.company_id == company_id,
        Application.stage == 'rejected',
        Application.reject_side == 'company',
        Application.stage_changed_at >= datetime.combine(start_date, datetime.min.time()),
        Application.stage_changed_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
        Application.reject_reason.is_not(None)
    ).group_by(Application.reject_reason)

    our_query = apply_vacancy_filter(our_query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        our_query = our_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    our_result = await session.execute(our_query)
    our_total = 0
    our_data = []
    for row in our_result:
        reason = row.reject_reason or 'Не указано'
        count = row.count
        our_total += count
        our_data.append({'reason': reason, 'value': count})

    # Проценты для наших отказов
    for item in our_data:
        item['pct'] = round((item['value'] / our_total) * 100, 1) if our_total > 0 else 0.0

    # Отказы кандидатов
    candidate_query = select(
        Application.reject_reason,
        func.count(Application.id).label('count')
    ).where(
        Application.company_id == company_id,
        Application.stage == 'rejected',
        Application.reject_side == 'candidate',
        Application.stage_changed_at >= datetime.combine(start_date, datetime.min.time()),
        Application.stage_changed_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
        Application.reject_reason.is_not(None)
    ).group_by(Application.reject_reason)

    candidate_query = apply_vacancy_filter(candidate_query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        candidate_query = candidate_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    candidate_result = await session.execute(candidate_query)
    candidate_total = 0
    candidate_data = []
    for row in candidate_result:
        reason = row.reject_reason or 'Не указано'
        count = row.count
        candidate_total += count
        candidate_data.append({'reason': reason, 'value': count})

    # Проценты для отказов кандидатов
    for item in candidate_data:
        item['pct'] = round((item['value'] / candidate_total) * 100, 1) if candidate_total > 0 else 0.0

    return ChartData(
        type='pie',
        title='Причины отказов',
        data={
            'our': our_data,
            'candidate': candidate_data
        }
    )


async def _build_rejections_dynamics_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Line chart: динамика отказов во времени"""
    start_date, end_date = window

    query = select(
        func.date(Application.stage_changed_at).label('date'),
        func.count(Application.id).label('value')
    ).where(
        Application.company_id == company_id,
        Application.stage == 'rejected',
        Application.stage_changed_at >= datetime.combine(start_date, datetime.min.time()),
        Application.stage_changed_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(func.date(Application.stage_changed_at)).order_by('date')

    query = apply_vacancy_filter(query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        query = query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    result = await session.execute(query)
    points = [{'date': str(row.date), 'value': row.value} for row in result]

    return ChartData(
        type='line',
        title='Динамика отказов',
        data={'points': points}
    )


async def _build_top_rejections_table(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> TableData:
    """Таблица топ-вакансий по отказам"""
    start_date, end_date = window

    query = select(
        Vacancy.name,
        func.count(Application.id).label('total_rejects'),
        func.count(case((Application.reject_side == 'company', 1))).label('our_rejects'),
        func.count(case((Application.reject_side == 'candidate', 1))).label('candidate_rejects')
    ).select_from(
        Application.__table__.join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
    ).where(
        Application.company_id == company_id,
        Application.stage == 'rejected',
        Application.stage_changed_at >= datetime.combine(start_date, datetime.min.time()),
        Application.stage_changed_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(Vacancy.id, Vacancy.name).order_by(func.count(Application.id).desc()).limit(10)

    query = apply_vacancy_filter(query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        query = query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    result = await session.execute(query)
    rows = []

    for row in result:
        rows.append({
            'vacancy': row.name,
            'total_rejects': row.total_rejects,
            'our_rejects': row.our_rejects,
            'candidate_rejects': row.candidate_rejects
        })

    columns = [
        TableColumn(key='vacancy', label='Вакансия', type='text'),
        TableColumn(key='total_rejects', label='Всего отказов', type='mono'),
        TableColumn(key='our_rejects', label='Наши отказы', type='mono'),
        TableColumn(key='candidate_rejects', label='Отказы кандидатов', type='mono')
    ]

    return TableData(
        title='Топ-вакансии по отказам',
        columns=columns,
        rows=rows
    )


async def build_rejections(session: AsyncSession, filters: AnalyticsFilters, company_id: UUID) -> AnalyticsResponse:
    """Строит отчёт Rejections"""
    window = resolve_analytics_window(filters.period, filters.date_from, filters.date_to)

    charts = [
        await _build_rejections_pie_chart(session, company_id, window, filters),
        await _build_rejections_dynamics_chart(session, company_id, window, filters)
    ]

    tables = [
        await _build_top_rejections_table(session, company_id, window, filters)
    ]

    return AnalyticsResponse(
        report='rejections',
        period=filters.period,
        kpis=None,
        charts=charts,
        tables=tables
    )