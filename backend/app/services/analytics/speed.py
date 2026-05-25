"""Analytics: Speed отчёт"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ...core.periods import resolve_analytics_window
from ...models import Application, StageHistory, Vacancy
from ...schemas.analytics import AnalyticsResponse, ChartData, TableData, TableColumn
from .common import AnalyticsFilters, apply_vacancy_filter


async def _build_boxplot_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Boxplot по этапам - dwell time (время нахождения в этапе)"""
    start_date, end_date = window

    stages = [
        ('response', 'Отклик'),
        ('selected', 'Отобран'),
        ('recruiter', 'Контакт с рекрутёром'),
        ('interview', 'Интервью'),
        ('manager', 'Контакт с менеджером'),
        ('offer', 'Оффер'),
        ('hired', 'Нанят')
    ]

    stages_data = []

    for stage_key, label in stages:
        # Dwell time calculation: entry time to exit time for each stage
        sh_in = aliased(StageHistory)
        sh_out = aliased(StageHistory)

        # Subquery: for each entry into stage_key, find the next exit from stage_key
        subq = (
            select(
                sh_in.application_id,
                sh_in.to_stage.label('stage_key'),
                sh_in.created_at.label('entered_at'),
                (
                    select(func.min(sh_out.created_at))
                    .where(
                        sh_out.application_id == sh_in.application_id,
                        sh_out.from_stage == sh_in.to_stage,
                        sh_out.created_at > sh_in.created_at,
                    )
                    .scalar_subquery()
                ).label('exited_at'),
            )
            .where(
                sh_in.to_stage == stage_key,
                sh_in.created_at >= datetime.combine(start_date, datetime.min.time()),
                sh_in.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
            )
            .subquery()
        )

        # dwell_days calculation (if exited_at is NULL, use current_timestamp)
        dwell_seconds = func.extract('epoch',
            func.coalesce(subq.c.exited_at, func.current_timestamp()) - subq.c.entered_at)
        dwell_days = dwell_seconds / 86400.0

        # Main query with filters
        dwell_query = select(dwell_days).select_from(
            subq.join(Application, subq.c.application_id == Application.id)
        ).where(
            Application.company_id == company_id
        )

        dwell_query = apply_vacancy_filter(dwell_query, Application.vacancy_id, filters.vacancy_ids)
        if filters.recruiter_ids:
            dwell_query = dwell_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
                Vacancy.responsible_user_id.in_(filters.recruiter_ids)
            )

        # Execute and get dwell times
        result = await session.execute(dwell_query)
        times = [float(row[0]) for row in result if row[0] is not None and row[0] > 0]

        if times:
            times.sort()
            n = len(times)

            # Calculate percentiles using Python (simpler than SQL PERCENTILE_CONT for this case)
            q1_idx = int(0.25 * (n - 1))
            q2_idx = int(0.5 * (n - 1))
            q3_idx = int(0.75 * (n - 1))

            q1 = times[q1_idx]
            median = times[q2_idx]
            q3 = times[q3_idx]

            # IQR method for outliers
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            # Outliers
            outliers = [t for t in times if t < lower_bound or t > upper_bound]

            # Min/max within bounds
            filtered_times = [t for t in times if lower_bound <= t <= upper_bound]
            min_val = min(filtered_times) if filtered_times else q1
            max_val = max(filtered_times) if filtered_times else q3

            stages_data.append({
                'stage_key': stage_key,
                'label': label,
                'median': round(median, 1),
                'q1': round(q1, 1),
                'q3': round(q3, 1),
                'min': round(min_val, 1),
                'max': round(max_val, 1),
                'outliers': [round(o, 1) for o in outliers]
            })
        else:
            # No data for this stage - return null values instead of 0
            stages_data.append({
                'stage_key': stage_key,
                'label': label,
                'median': None,
                'q1': None,
                'q3': None,
                'min': None,
                'max': None,
                'outliers': []
            })

    return ChartData(
        type='boxplot',
        title='Время на этапах (дни)',
        data={'stages': stages_data}
    )


async def _build_heatmap_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Heatmap вакансия × этап - среднее время в днях"""
    start_date, end_date = window

    # Топ-10 вакансий по количеству заявок
    top_vacancies_query = select(
        Vacancy.id,
        Vacancy.name,
        func.count(Application.id).label('applications_count')
    ).select_from(
        Application.__table__.join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
    ).where(
        Application.company_id == company_id,
        Application.created_at >= datetime.combine(start_date, datetime.min.time()),
        Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(Vacancy.id, Vacancy.name).order_by(func.count(Application.id).desc()).limit(10)

    top_vacancies_query = apply_vacancy_filter(top_vacancies_query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        top_vacancies_query = top_vacancies_query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    top_vacancies_result = await session.execute(top_vacancies_query)
    top_vacancies = [(row.id, row.name) for row in top_vacancies_result]

    if not top_vacancies:
        return ChartData(
            type='heatmap',
            title='Время по этапам и вакансиям',
            data={'x_labels': [], 'y_labels': [], 'cells': []}
        )

    stages = ['response', 'selected', 'recruiter', 'interview', 'manager', 'offer', 'hired']
    x_labels = stages
    y_labels = [name for _, name in top_vacancies]

    cells = []
    for y, (vacancy_id, _) in enumerate(top_vacancies):
        for x, stage_key in enumerate(stages):
            # Average dwell time for (vacancy, stage) pair using stage_history transitions
            sh_in = aliased(StageHistory)
            sh_out = aliased(StageHistory)

            # Subquery: for each entry into stage_key for this vacancy, find the next exit
            subq = (
                select(
                    sh_in.application_id,
                    sh_in.created_at.label('entered_at'),
                    (
                        select(func.min(sh_out.created_at))
                        .where(
                            sh_out.application_id == sh_in.application_id,
                            sh_out.from_stage == sh_in.to_stage,
                            sh_out.created_at > sh_in.created_at,
                        )
                        .scalar_subquery()
                    ).label('exited_at'),
                )
                .where(
                    sh_in.to_stage == stage_key,
                    sh_in.created_at >= datetime.combine(start_date, datetime.min.time()),
                    sh_in.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
                )
                .subquery()
            )

            # Average dwell time for this vacancy+stage
            dwell_seconds = func.extract('epoch',
                func.coalesce(subq.c.exited_at, func.current_timestamp()) - subq.c.entered_at)
            dwell_days = dwell_seconds / 86400.0

            avg_query = select(func.avg(dwell_days)).select_from(
                subq.join(Application, subq.c.application_id == Application.id)
            ).where(
                Application.company_id == company_id,
                Application.vacancy_id == vacancy_id
            )

            result = await session.execute(avg_query)
            avg_days = result.scalar()
            value_days = round(avg_days, 1) if avg_days is not None else None

            cells.append({
                'x': x,
                'y': y,
                'value': value_days
            })

    return ChartData(
        type='heatmap',
        title='Время по этапам и вакансиям',
        data={
            'x_labels': x_labels,
            'y_labels': y_labels,
            'cells': cells
        }
    )


async def _build_time_to_hire_table(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> TableData:
    """Таблица time-to-hire по вакансиям (от первой записи stage_history до hired)"""
    start_date, end_date = window

    # Subquery: for each application, calculate time from first stage_history to hired stage
    first_history_subq = (
        select(
            StageHistory.application_id,
            func.min(StageHistory.created_at).label('first_history_at')
        )
        .group_by(StageHistory.application_id)
        .subquery()
    )

    hired_history_subq = (
        select(
            StageHistory.application_id,
            StageHistory.created_at.label('hired_at')
        )
        .where(StageHistory.to_stage == 'hired')
        .subquery()
    )

    # Main query: join to get time-to-hire per application, then aggregate by vacancy
    time_to_hire_seconds = func.extract('epoch',
        hired_history_subq.c.hired_at - first_history_subq.c.first_history_at)
    time_to_hire_days = time_to_hire_seconds / 86400.0

    query = select(
        Vacancy.name,
        func.percentile_cont(0.5).within_group(time_to_hire_days).label('p50'),
        func.percentile_cont(0.9).within_group(time_to_hire_days).label('p90'),
        func.avg(time_to_hire_days).label('avg')
    ).select_from(
        first_history_subq.join(
            hired_history_subq,
            first_history_subq.c.application_id == hired_history_subq.c.application_id
        ).join(
            Application,
            first_history_subq.c.application_id == Application.id
        ).join(
            Vacancy,
            Application.vacancy_id == Vacancy.id
        )
    ).where(
        Application.company_id == company_id,
        hired_history_subq.c.hired_at >= datetime.combine(start_date, datetime.min.time()),
        hired_history_subq.c.hired_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(Vacancy.id, Vacancy.name).order_by(func.avg(time_to_hire_days))

    query = apply_vacancy_filter(query, Application.vacancy_id, filters.vacancy_ids)
    if filters.recruiter_ids:
        query = query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    result = await session.execute(query)
    rows = []
    for row in result:
        rows.append({
            'vacancy': row.name,
            'p50': round(row.p50, 1) if row.p50 is not None else None,
            'p90': round(row.p90, 1) if row.p90 is not None else None,
            'avg': round(row.avg, 1) if row.avg is not None else None
        })

    columns = [
        TableColumn(key='vacancy', label='Вакансия', type='text'),
        TableColumn(key='p50', label='p50', type='mono'),
        TableColumn(key='p90', label='p90', type='mono'),
        TableColumn(key='avg', label='Среднее', type='mono')
    ]

    return TableData(
        title='Time-to-hire по вакансиям',
        columns=columns,
        rows=rows
    )


async def build_speed(session: AsyncSession, filters: AnalyticsFilters, company_id: UUID) -> AnalyticsResponse:
    """Строит отчёт Speed"""
    window = resolve_analytics_window(filters.period, filters.date_from, filters.date_to)

    charts = [
        await _build_boxplot_chart(session, company_id, window, filters),
        await _build_heatmap_chart(session, company_id, window, filters)
    ]

    tables = [
        await _build_time_to_hire_table(session, company_id, window, filters)
    ]

    return AnalyticsResponse(
        report='speed',
        period=filters.period,
        kpis=None,
        charts=charts,
        tables=tables
    )