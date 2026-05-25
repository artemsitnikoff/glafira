"""Analytics: Turnover отчёт"""

from datetime import datetime, timedelta, date as date_type
from uuid import UUID

from sqlalchemy import func, select, and_, extract, case, TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.periods import resolve_analytics_window
from ...models import Employee, User
from ...schemas.analytics import AnalyticsResponse, ChartData, TableData, TableColumn
from .common import AnalyticsFilters


async def _build_cohort_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Cohort heatmap: retention по месяцам найма"""
    start_date, end_date = window

    # Окно когорт: последние 12 месяцев
    today = date_type.today()
    cohort_start = today.replace(day=1) - timedelta(days=365)

    # Дни retention для анализа
    retention_days = [30, 60, 90, 180, 360]

    cohorts = []

    # Перебираем месяцы когорт
    current_month = cohort_start.replace(day=1)
    while current_month <= today.replace(day=1):
        cohort_month_str = current_month.strftime('%Y-%m')

        # Месяц следующий для границ
        if current_month.month == 12:
            next_month = current_month.replace(year=current_month.year + 1, month=1)
        else:
            next_month = current_month.replace(month=current_month.month + 1)

        # Всего нанято в этой когорте
        hired_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.start_date >= current_month,
            Employee.start_date < next_month
        )

        # Применение фильтров recruiter_ids
        if filters.recruiter_ids:
            hired_query = hired_query.where(Employee.recruiter_user_id.in_(filters.recruiter_ids))

        hired_result = await session.execute(hired_query)
        hired_total = hired_result.scalar() or 0

        if hired_total == 0:
            # Пропускаем месяцы без найма
            current_month = next_month
            continue

        sizes = []
        for day in retention_days:
            # Сколько осталось через `day` дней
            cutoff_date = current_month + timedelta(days=day)
            if cutoff_date > today:
                # Слишком рано для расчёта retention
                sizes.append({'day': day, 'retained_pct': None})
                continue

            retained_query = select(func.count(Employee.id)).where(
                Employee.company_id == company_id,
                Employee.start_date >= current_month,
                Employee.start_date < next_month,
                and_(
                    Employee.left_at.is_(None),  # ещё работает
                    Employee.start_date + timedelta(days=day) <= today  # прошло day дней
                ).self_group() | and_(
                    Employee.left_at.is_not(None),  # ушёл
                    Employee.left_at > current_month + timedelta(days=day)  # но позже чем через day дней
                ).self_group()
            )

            if filters.recruiter_ids:
                retained_query = retained_query.where(Employee.recruiter_user_id.in_(filters.recruiter_ids))

            retained_result = await session.execute(retained_query)
            retained_count = retained_result.scalar() or 0

            retained_pct = round((retained_count / hired_total) * 100, 1) if hired_total > 0 else 0.0
            sizes.append({'day': day, 'retained_pct': retained_pct})

        cohorts.append({
            'month': cohort_month_str,
            'sizes': sizes
        })

        current_month = next_month

    return ChartData(
        type='cohort',
        title='Cohort retention',
        data={'cohorts': cohorts}
    )


async def _build_survival_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Survival curve: retention все сотрудники"""

    # Точки survival curve через каждые 30 дней до 360
    survival_days = list(range(30, 361, 30))  # [30, 60, 90, ..., 360]

    points = []
    today = date_type.today()

    for day in survival_days:
        # Всего сотрудников, которые могли проработать `day` дней (start_date + day <= today)
        eligible_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.start_date + timedelta(days=day) <= today
        )

        if filters.recruiter_ids:
            eligible_query = eligible_query.where(Employee.recruiter_user_id.in_(filters.recruiter_ids))

        eligible_result = await session.execute(eligible_query)
        eligible_count = eligible_result.scalar() or 0

        if eligible_count == 0:
            points.append({'day': day, 'retained_pct': 0.0})
            continue

        # Из них сколько осталось через `day` дней
        survived_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.start_date + timedelta(days=day) <= today,
            and_(
                Employee.left_at.is_(None),  # ещё работает
            ).self_group() | and_(
                Employee.left_at.is_not(None),  # ушёл
                Employee.left_at > Employee.start_date + timedelta(days=day)  # но позже чем через day дней
            ).self_group()
        )

        if filters.recruiter_ids:
            survived_query = survived_query.where(Employee.recruiter_user_id.in_(filters.recruiter_ids))

        survived_result = await session.execute(survived_query)
        survived_count = survived_result.scalar() or 0

        retained_pct = round((survived_count / eligible_count) * 100, 1) if eligible_count > 0 else 0.0
        points.append({'day': day, 'retained_pct': retained_pct})

    return ChartData(
        type='survival',
        title='Survival curve',
        data={'points': points}
    )


async def _build_managers_table(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> TableData:
    """Таблица по руководителям"""

    # Honest avg_tenure_days calculation: AVG((COALESCE(left_at, CURRENT_DATE) - start_date) in days)
    # Cast dates to timestamp to make EXTRACT(epoch) work
    left_at_ts = func.coalesce(func.cast(Employee.left_at, TIMESTAMP), func.current_timestamp())
    start_date_ts = func.cast(Employee.start_date, TIMESTAMP)
    tenure_seconds = func.extract('epoch', left_at_ts - start_date_ts)
    avg_tenure_days = func.avg(tenure_seconds / 86400.0)

    manager_query = select(
        User.id,
        User.full_name,
        func.count(Employee.id).label('hired_count'),
        func.count(case((Employee.status == 'left', 1))).label('left_count'),
        avg_tenure_days.label('avg_tenure_days')
    ).select_from(
        Employee.__table__.join(User.__table__, Employee.manager_user_id == User.id)
    ).where(
        Employee.company_id == company_id
    ).group_by(User.id, User.full_name).order_by(func.count(Employee.id).desc())

    if filters.recruiter_ids:
        manager_query = manager_query.where(Employee.recruiter_user_id.in_(filters.recruiter_ids))

    result = await session.execute(manager_query)
    rows = []

    for row in result:
        manager_id = row.id
        manager_name = row.full_name
        hired_count = row.hired_count
        left_count = row.left_count
        avg_tenure_days = round(row.avg_tenure_days, 1) if row.avg_tenure_days is not None else None

        # Retention 90d: кто проработал больше 90 дней
        retention_90d_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.manager_user_id == manager_id,
            and_(
                Employee.left_at.is_(None),  # ещё работает и прошло >90 дней
                Employee.start_date + timedelta(days=90) <= date_type.today()
            ).self_group() | and_(
                Employee.left_at.is_not(None),  # ушёл после >90 дней
                Employee.left_at > Employee.start_date + timedelta(days=90)
            ).self_group()
        )

        retention_90d_result = await session.execute(retention_90d_query)
        retention_90d_count = retention_90d_result.scalar() or 0

        # Eligible для 90d retention
        eligible_90d_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.manager_user_id == manager_id,
            Employee.start_date + timedelta(days=90) <= date_type.today()
        )

        eligible_90d_result = await session.execute(eligible_90d_query)
        eligible_90d_count = eligible_90d_result.scalar() or 0

        retention_90d_pct = round((retention_90d_count / eligible_90d_count) * 100, 1) if eligible_90d_count > 0 else 0.0

        rows.append({
            'manager_name': manager_name,
            'hired_count': hired_count,
            'left_count': left_count,
            'retention_90d_pct': f'{retention_90d_pct}%',
            'avg_tenure_days': avg_tenure_days
        })

    columns = [
        TableColumn(key='manager_name', label='Руководитель', type='text'),
        TableColumn(key='hired_count', label='Нанято', type='mono'),
        TableColumn(key='left_count', label='Ушло', type='mono'),
        TableColumn(key='retention_90d_pct', label='Retention 90d', type='mono'),
        TableColumn(key='avg_tenure_days', label='Срок работы (дни)', type='mono')
    ]

    return TableData(
        title='Статистика по руководителям',
        columns=columns,
        rows=rows
    )


async def build_turnover(session: AsyncSession, filters: AnalyticsFilters, company_id: UUID) -> AnalyticsResponse:
    """Строит отчёт Turnover"""
    window = resolve_analytics_window(filters.period, filters.date_from, filters.date_to)

    charts = [
        await _build_cohort_chart(session, company_id, window, filters),
        await _build_survival_chart(session, company_id, window, filters)
    ]

    tables = [
        await _build_managers_table(session, company_id, window, filters)
    ]

    return AnalyticsResponse(
        report='turnover',
        period=filters.period,
        kpis=None,
        charts=charts,
        tables=tables
    )