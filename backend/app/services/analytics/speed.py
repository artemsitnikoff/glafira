"""Analytics: Speed отчёт"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.periods import resolve_analytics_window
from ...models import Application, StageHistory, Vacancy
from ...schemas.analytics import AnalyticsResponse, ChartData, TableData, TableColumn
from .common import AnalyticsFilters, apply_vacancy_filter


async def _build_boxplot_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Boxplot по этапам - время в днях"""
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
        # Упрощенный расчет времени - время от начала заявки до этапа
        time_query = select(
            func.extract('epoch',
                StageHistory.created_at - Application.created_at
            ) / 86400
        ).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
        ).where(
            Application.company_id == company_id,
            StageHistory.to_stage == stage_key,
            StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
            StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

        time_query = apply_vacancy_filter(time_query, Application.vacancy_id, filters.vacancy_ids)
        if filters.recruiter_ids:
            time_query = time_query.join(Vacancy, Application.vacancy_id == Vacancy.id).where(
                Vacancy.responsible_user_id.in_(filters.recruiter_ids)
            )

        # Получаем значения времени
        result = await session.execute(time_query)
        times = [row[0] for row in result if row[0] is not None and row[0] > 0]

        if times:
            times.sort()
            n = len(times)

            # Расчёт квартилей
            q1_idx = int(0.25 * (n - 1))
            q2_idx = int(0.5 * (n - 1))
            q3_idx = int(0.75 * (n - 1))

            q1 = times[q1_idx]
            median = times[q2_idx]
            q3 = times[q3_idx]

            # IQR method для outliers
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            # Outliers
            outliers = [t for t in times if t < lower_bound or t > upper_bound]

            # Min/max в пределах bounds
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
            # Нет данных для этапа
            stages_data.append({
                'stage_key': stage_key,
                'label': label,
                'median': 0,
                'q1': 0,
                'q3': 0,
                'min': 0,
                'max': 0,
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
            # Среднее время для пары (вакансия, этап) - упрощенный расчет
            time_query = select(
                func.avg(
                    func.extract('epoch',
                        StageHistory.created_at - Application.created_at
                    ) / 86400
                )
            ).select_from(
                StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            ).where(
                Application.company_id == company_id,
                Application.vacancy_id == vacancy_id,
                StageHistory.to_stage == stage_key,
                StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
                StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
            )

            result = await session.execute(time_query)
            avg_days = result.scalar()
            value_days = round(avg_days, 1) if avg_days is not None else 0.0

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
    """Таблица time-to-hire по вакансиям"""
    start_date, end_date = window

    # Запрос для статистик по вакансиям с нанятыми кандидатами
    query = select(
        Vacancy.name,
        func.percentile_cont(0.5).within_group(
            func.extract('epoch', Vacancy.closed_at - Vacancy.created_at) / 86400
        ).label('p50'),
        func.percentile_cont(0.9).within_group(
            func.extract('epoch', Vacancy.closed_at - Vacancy.created_at) / 86400
        ).label('p90'),
        func.avg(
            func.extract('epoch', Vacancy.closed_at - Vacancy.created_at) / 86400
        ).label('avg')
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.archive_result == 'hired',
        Vacancy.closed_at >= start_date,
        Vacancy.closed_at <= end_date,
        Vacancy.closed_at.is_not(None)
    ).group_by(Vacancy.id, Vacancy.name).order_by('avg')

    if filters.recruiter_ids:
        query = query.where(Vacancy.responsible_user_id.in_(filters.recruiter_ids))

    result = await session.execute(query)
    rows = []
    for row in result:
        rows.append({
            'vacancy': row.name,
            'p50': round(row.p50, 1) if row.p50 is not None else 0.0,
            'p90': round(row.p90, 1) if row.p90 is not None else 0.0,
            'avg': round(row.avg, 1) if row.avg is not None else 0.0
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