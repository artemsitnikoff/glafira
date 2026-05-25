"""Analytics: Funnel отчёт"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.periods import resolve_analytics_window
from ...models import Application, Candidate, Vacancy
from ...schemas.analytics import AnalyticsResponse, ChartData, TableData, TableColumn
from .common import AnalyticsFilters, apply_vacancy_filter


async def _build_funnel_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Funnel chart - конверсии по этапам"""
    start_date, end_date = window

    stages_order = [
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

    # Считаем количество заявок на каждом этапе
    stage_query = select(
        Application.stage,
        func.count(Application.id).label('count')
    ).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(Application.stage)

    stage_query = apply_vacancy_filter(stage_query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        stage_query = stage_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
            Vacancy.responsible_user_id.in_(filters.recruiter_ids)
        )

    result = await session.execute(stage_query)
    stage_counts = {row.stage: row.count for row in result}

    stages_data = []
    prev_count = None

    for stage_key, label, color in stages_order:
        count = stage_counts.get(stage_key, 0)

        # Конверсия от предыдущего этапа
        conversion_from_prev_pct = None
        if prev_count is not None and prev_count > 0:
            conversion_from_prev_pct = round((count / prev_count) * 100, 1)

        stages_data.append({
            'stage_key': stage_key,
            'label': label,
            'color': color,
            'count': count,
            'conversion_from_prev_pct': conversion_from_prev_pct
        })

        if stage_key not in ['hired', 'rejected']:  # Terminals не участвуют в последовательности
            prev_count = count

    # Terminals отдельно
    hired_count = stage_counts.get('hired', 0)
    rejected_count = stage_counts.get('rejected', 0)
    total_terminals = hired_count + rejected_count
    total_applications = sum(stage_counts.values())

    terminals = {
        'hired': {
            'n': hired_count,
            'pct': round((hired_count / total_applications) * 100, 1) if total_applications > 0 else 0.0
        },
        'rejected': {
            'n': rejected_count,
            'pct': round((rejected_count / total_applications) * 100, 1) if total_applications > 0 else 0.0
        }
    }

    # Исключаем terminals из основного funnel
    funnel_stages = [s for s in stages_data if s['stage_key'] not in ['hired', 'rejected']]

    return ChartData(
        type='funnel',
        title='Воронка конверсий',
        data={
            'stages': funnel_stages,
            'terminals': terminals
        }
    )


async def _build_conversion_table(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> TableData:
    """Таблица конверсий в разрезах источника"""
    start_date, end_date = window

    # Разрез по источникам
    source_query = select(
        Candidate.source,
        func.count(Application.id).label('applied'),
        func.count(case((Application.stage.in_(['selected', 'recruiter', 'interview', 'manager', 'offer', 'hired']), 1))).label('screening'),
        func.count(case((Application.stage.in_(['interview', 'manager', 'offer', 'hired']), 1))).label('interview'),
        func.count(case((Application.stage == 'hired', 1))).label('hired')
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
        applied = row.applied
        screening = row.screening
        interview = row.interview
        hired = row.hired

        # Конверсии в процентах
        screening_pct = round((screening / applied) * 100, 1) if applied > 0 else 0.0
        interview_pct = round((interview / applied) * 100, 1) if applied > 0 else 0.0
        hired_pct = round((hired / applied) * 100, 1) if applied > 0 else 0.0

        rows.append({
            'source': source,
            'applied': applied,
            'screening_count': screening,
            'screening_pct': f'{screening_pct}%',
            'interview_count': interview,
            'interview_pct': f'{interview_pct}%',
            'hired_count': hired,
            'hired_pct': f'{hired_pct}%'
        })

    columns = [
        TableColumn(key='source', label='Источник', type='text'),
        TableColumn(key='applied', label='Подано', type='mono'),
        TableColumn(key='screening_count', label='Скрининг', type='mono'),
        TableColumn(key='screening_pct', label='%', type='mono'),
        TableColumn(key='interview_count', label='Интервью', type='mono'),
        TableColumn(key='interview_pct', label='%', type='mono'),
        TableColumn(key='hired_count', label='Найм', type='mono'),
        TableColumn(key='hired_pct', label='%', type='mono')
    ]

    return TableData(
        title='Конверсии по источникам',
        columns=columns,
        rows=rows
    )


async def build_funnel(session: AsyncSession, filters: AnalyticsFilters, company_id: UUID) -> AnalyticsResponse:
    """Строит отчёт Funnel"""
    window = resolve_analytics_window(filters.period, filters.date_from, filters.date_to)

    charts = [
        await _build_funnel_chart(session, company_id, window, filters)
    ]

    tables = [
        await _build_conversion_table(session, company_id, window, filters)
    ]

    return AnalyticsResponse(
        report='funnel',
        period=filters.period,
        kpis=None,
        charts=charts,
        tables=tables
    )