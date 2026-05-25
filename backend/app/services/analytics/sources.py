"""Analytics: Sources отчёт"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.periods import resolve_analytics_window
from ...models import Application, Candidate, Vacancy
from ...schemas.analytics import AnalyticsResponse, ChartData, TableData, TableColumn
from .common import AnalyticsFilters, apply_vacancy_filter


async def _build_sources_table(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> TableData:
    """Таблица эффективности источников"""
    start_date, end_date = window

    source_query = select(
        Candidate.source,
        func.count(Application.id).label('applications_count'),
        func.count(case((Application.stage.in_(['selected', 'recruiter', 'interview', 'manager', 'offer', 'hired']), 1))).label('screening_count'),
        func.count(case((Application.stage.in_(['interview', 'manager', 'offer', 'hired']), 1))).label('interview_count'),
        func.count(case((Application.stage == 'hired', 1))).label('hired_count')
    ).select_from(
        Application.__table__.join(Candidate.__table__, Application.candidate_id == Candidate.id)
    ).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(Candidate.source)

    source_query = apply_vacancy_filter(source_query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        source_query = source_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    result = await session.execute(source_query)
    rows = []

    for row in result:
        source = row.source or 'Неизвестно'
        applications_count = row.applications_count
        screening_count = row.screening_count
        interview_count = row.interview_count
        hired_count = row.hired_count

        # Проценты
        screening_pct = round((screening_count / applications_count) * 100, 1) if applications_count > 0 else 0.0
        interview_pct = round((interview_count / applications_count) * 100, 1) if applications_count > 0 else 0.0
        hired_pct = round((hired_count / applications_count) * 100, 1) if applications_count > 0 else 0.0

        rows.append({
            'source': source,
            'applications_count': applications_count,
            'screening_count': screening_count,
            'screening_pct': f'{screening_pct}%',
            'interview_count': interview_count,
            'interview_pct': f'{interview_pct}%',
            'hired_count': hired_count,
            'hired_pct': f'{hired_pct}%',
            'cost': None,  # TODO(post-MVP): source attribution cost
            'roi': None    # TODO(post-MVP): source attribution cost
        })

    columns = [
        TableColumn(key='source', label='Источник', type='text'),
        TableColumn(key='applications_count', label='Откликов', type='mono'),
        TableColumn(key='screening_count', label='Прошли скрининг', type='mono'),
        TableColumn(key='screening_pct', label='%', type='mono'),
        TableColumn(key='interview_count', label='Дошли до интервью', type='mono'),
        TableColumn(key='interview_pct', label='%', type='mono'),
        TableColumn(key='hired_count', label='Нанято', type='mono'),
        TableColumn(key='hired_pct', label='%', type='mono'),
        TableColumn(key='cost', label='Стоимость (₽)', type='mono'),
        TableColumn(key='roi', label='ROI', type='mono')
    ]

    return TableData(
        title='Эффективность источников',
        columns=columns,
        rows=rows
    )


async def _build_stacked_sources_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Stacked chart: этапы по источникам"""
    start_date, end_date = window

    # Получаем данные по источникам и этапам
    query = select(
        Candidate.source,
        Application.stage,
        func.count(Application.id).label('count')
    ).select_from(
        Application.__table__.join(Candidate.__table__, Application.candidate_id == Candidate.id)
    ).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(Candidate.source, Application.stage)

    query = apply_vacancy_filter(query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        query = query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    result = await session.execute(query)

    # Группируем данные
    data = {}
    for row in result:
        source = row.source or 'Неизвестно'
        stage = row.stage
        count = row.count

        if source not in data:
            data[source] = {}
        data[source][stage] = count

    # Формируем массив для stacked chart
    stages = [
        ('response', 'Отклик', '#5B6573'),
        ('selected', 'Отобран', '#9AA3AE'),
        ('recruiter', 'Контакт с рекрутёром', '#7AB4F5'),
        ('interview', 'Интервью', '#2A8AF0'),
        ('manager', 'Контакт с менеджером', '#5778E8'),
        ('offer', 'Оффер', '#E0A21A'),
        ('hired', 'Нанят', '#16A34A'),
        ('rejected', 'Отказ', '#DC4646')
    ]

    sources_data = []
    for source, stage_counts in data.items():
        source_stages = []
        for stage_key, label, color in stages:
            count = stage_counts.get(stage_key, 0)
            source_stages.append({
                'stage_key': stage_key,
                'label': label,
                'color': color,
                'count': count
            })

        sources_data.append({
            'source': source,
            'stages': source_stages
        })

    return ChartData(
        type='stacked',
        title='Отклики→найм по источникам',
        data={'sources': sources_data}
    )


async def _build_scatter_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Scatter chart: качество × объём по источникам"""
    start_date, end_date = window

    # Получаем средний AI-скоринг и объём заявок по источникам
    query = select(
        Candidate.source,
        func.avg(Application.ai_score).label('avg_score'),
        func.count(Application.id).label('volume')
    ).select_from(
        Application.__table__.join(Candidate.__table__, Application.candidate_id == Candidate.id)
    ).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
        Application.ai_score.is_not(None)
    ).group_by(Candidate.source)

    query = apply_vacancy_filter(query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        query = query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    result = await session.execute(query)

    points = []
    for row in result:
        source = row.source or 'Неизвестно'
        avg_score = round(row.avg_score, 1) if row.avg_score is not None else 0.0
        volume = row.volume

        points.append({
            'label': source,
            'x': avg_score,  # качество (avg AI-скоринг)
            'y': volume      # объём
        })

    return ChartData(
        type='scatter',
        title='Качество × объём по источникам',
        data={'points': points}
    )


async def build_sources(session: AsyncSession, filters: AnalyticsFilters, company_id: UUID) -> AnalyticsResponse:
    """Строит отчёт Sources"""
    window = resolve_analytics_window(filters.period, filters.date_from, filters.date_to)

    tables = [
        await _build_sources_table(session, company_id, window, filters)
    ]

    charts = [
        await _build_stacked_sources_chart(session, company_id, window, filters),
        await _build_scatter_chart(session, company_id, window, filters)
    ]

    return AnalyticsResponse(
        report='sources',
        period=filters.period,
        kpis=None,
        charts=charts,
        tables=tables
    )