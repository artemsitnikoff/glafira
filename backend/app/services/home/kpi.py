"""Сервис для расчёта KPI главной страницы"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...core.periods import parse_home_period
from ...models import Vacancy, Application, Candidate, Employee, Message
from ...schemas.home import HomeKpi, KpiCard


def compute_delta_dir(current: float, previous: float | None, *, lower_is_better: bool = False) -> str:
    """Вычисляет направление изменения для KPI"""
    if previous is None or current == previous:
        return 'flat'

    is_growing = current > previous

    if lower_is_better:
        return 'up-bad' if is_growing else 'down-good'
    else:
        return 'up' if is_growing else 'down'


async def _get_open_vacancies(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Количество открытых вакансий"""
    # Snapshot на конец текущего периода
    current_query = select(func.count(Vacancy.id)).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'active'
    )
    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0)

    # Для period='all' дельта не считается
    if period_days is None:
        return current, None

    # previous = вакансии, которые БЫЛИ active на начало периода
    period_start = datetime.now(timezone.utc) - timedelta(days=period_days)
    previous_query = select(func.count(Vacancy.id)).where(
        Vacancy.company_id == company_id,
        Vacancy.created_at < period_start,
        or_(
            Vacancy.status == 'active',
            and_(Vacancy.status == 'archived', Vacancy.closed_at > period_start.date())
        )
    )
    previous_result = await session.execute(previous_query)
    previous = float(previous_result.scalar() or 0)

    return current, previous


async def _get_closed_vacancies(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Количество закрытых вакансий"""
    now = datetime.now(timezone.utc)

    if period_days is None:
        # Все время
        current_query = select(func.count(Vacancy.id)).where(
            Vacancy.company_id == company_id,
            Vacancy.status == 'archived',
            Vacancy.closed_at.is_not(None)
        )
        current_result = await session.execute(current_query)
        current = float(current_result.scalar() or 0)
        return current, None

    # Текущий период
    start_date = now - timedelta(days=period_days)
    current_query = select(func.count(Vacancy.id)).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.closed_at >= start_date.date(),
        Vacancy.closed_at <= now.date()
    )
    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0)

    # Предыдущий период
    prev_start = start_date - timedelta(days=period_days)
    prev_query = select(func.count(Vacancy.id)).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.closed_at >= prev_start.date(),
        Vacancy.closed_at < start_date.date()
    )
    prev_result = await session.execute(prev_query)
    previous = float(prev_result.scalar() or 0)

    return current, previous


async def _get_avg_time_to_hire(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Среднее время найма"""
    now = datetime.now(timezone.utc)

    if period_days is None:
        # Все время
        query = select(
            func.avg(func.date_part('day', Vacancy.closed_at - Vacancy.created_at))
        ).where(
            Vacancy.company_id == company_id,
            Vacancy.status == 'archived',
            Vacancy.archive_result == 'hired',
            Vacancy.closed_at.is_not(None)
        )
        result = await session.execute(query)
        current = float(result.scalar() or 0.0)
        return current, None

    # Текущий период
    start_date = now - timedelta(days=period_days)
    current_query = select(
        func.avg(func.date_part('day', Vacancy.closed_at - Vacancy.created_at))
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.archive_result == 'hired',
        Vacancy.closed_at >= start_date.date(),
        Vacancy.closed_at <= now.date()
    )
    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0.0)

    # Предыдущий период
    prev_start = start_date - timedelta(days=period_days)
    prev_query = select(
        func.avg(func.date_part('day', Vacancy.closed_at - Vacancy.created_at))
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'archived',
        Vacancy.archive_result == 'hired',
        Vacancy.closed_at >= prev_start.date(),
        Vacancy.closed_at < start_date.date()
    )
    prev_result = await session.execute(prev_query)
    prev_val = prev_result.scalar()
    previous = float(prev_val) if prev_val else 0.0

    return current, previous


async def _get_turnover_90d(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Текучесть 90 дней"""
    now = datetime.now(timezone.utc)

    if period_days is None:
        # Все время - считаем общую текучесть за все время
        left_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id,
            Employee.status == 'left',
            Employee.left_at.is_not(None),
            (Employee.left_at - Employee.start_date) < 90
        )
        left_result = await session.execute(left_query)
        left_count = left_result.scalar() or 0

        total_query = select(func.count(Employee.id)).where(
            Employee.company_id == company_id
        )
        total_result = await session.execute(total_query)
        total_count = total_result.scalar() or 0

        current = (left_count / total_count * 100) if total_count > 0 else 0.0
        return current, None

    # Текущий период
    start_date = now - timedelta(days=period_days)

    # Ушедшие в первые 90 дней среди нанятых в текущем периоде
    left_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.status == 'left',
        Employee.start_date >= start_date.date(),
        Employee.start_date <= now.date(),
        (Employee.left_at - Employee.start_date) < 90
    )
    left_result = await session.execute(left_query)
    left_current = left_result.scalar() or 0

    # Всего нанятых в текущем периоде
    total_current_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.start_date >= start_date.date(),
        Employee.start_date <= now.date()
    )
    total_current_result = await session.execute(total_current_query)
    total_current = total_current_result.scalar() or 0

    current = (left_current / total_current * 100) if total_current > 0 else 0.0

    # Предыдущий период
    prev_start = start_date - timedelta(days=period_days)

    left_prev_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.status == 'left',
        Employee.start_date >= prev_start.date(),
        Employee.start_date < start_date.date(),
        (Employee.left_at - Employee.start_date) < 90
    )
    left_prev_result = await session.execute(left_prev_query)
    left_prev = left_prev_result.scalar() or 0

    total_prev_query = select(func.count(Employee.id)).where(
        Employee.company_id == company_id,
        Employee.start_date >= prev_start.date(),
        Employee.start_date < start_date.date()
    )
    total_prev_result = await session.execute(total_prev_query)
    total_prev = total_prev_result.scalar() or 0

    previous = (left_prev / total_prev * 100) if total_prev > 0 else 0.0

    return current, previous


async def _get_active_candidates(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Активные кандидаты"""
    now = datetime.now(timezone.utc)

    if period_days is None:
        # Все время - все кандидаты с активными заявками
        query = select(func.count(func.distinct(Application.candidate_id))).where(
            Application.company_id == company_id,
            ~Application.stage.in_(['hired', 'rejected'])
        )
        result = await session.execute(query)
        current = float(result.scalar() or 0)
        return current, None

    # Текущий период
    start_date = now - timedelta(days=period_days)
    current_query = select(func.count(func.distinct(Application.candidate_id))).where(
        Application.company_id == company_id,
        ~Application.stage.in_(['hired', 'rejected']),
        Application.created_at >= start_date,
        Application.created_at <= now
    )
    current_result = await session.execute(current_query)
    current = float(current_result.scalar() or 0)

    # Предыдущий период
    prev_start = start_date - timedelta(days=period_days)
    prev_query = select(func.count(func.distinct(Application.candidate_id))).where(
        Application.company_id == company_id,
        ~Application.stage.in_(['hired', 'rejected']),
        Application.created_at >= prev_start,
        Application.created_at < start_date
    )
    prev_result = await session.execute(prev_query)
    previous = float(prev_result.scalar() or 0)

    return current, previous


async def _get_conversion(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Конверсия отклик→найм"""
    now = datetime.now(timezone.utc)

    if period_days is None:
        # Все время
        hired_query = select(func.count(Application.id)).where(
            Application.company_id == company_id,
            Application.stage == 'hired'
        )
        hired_result = await session.execute(hired_query)
        hired_count = hired_result.scalar() or 0

        total_query = select(func.count(Application.id)).where(
            Application.company_id == company_id
        )
        total_result = await session.execute(total_query)
        total_count = total_result.scalar() or 0

        current = (hired_count / total_count * 100) if total_count > 0 else 0.0
        return current, None

    # Текущий период
    start_date = now - timedelta(days=period_days)

    hired_current_query = select(func.count(Application.id)).where(
        Application.company_id == company_id,
        Application.stage == 'hired',
        Application.created_at >= start_date,
        Application.created_at <= now
    )
    hired_current_result = await session.execute(hired_current_query)
    hired_current = hired_current_result.scalar() or 0

    total_current_query = select(func.count(Application.id)).where(
        Application.company_id == company_id,
        Application.created_at >= start_date,
        Application.created_at <= now
    )
    total_current_result = await session.execute(total_current_query)
    total_current = total_current_result.scalar() or 0

    current = (hired_current / total_current * 100) if total_current > 0 else 0.0

    # Предыдущий период
    prev_start = start_date - timedelta(days=period_days)

    hired_prev_query = select(func.count(Application.id)).where(
        Application.company_id == company_id,
        Application.stage == 'hired',
        Application.created_at >= prev_start,
        Application.created_at < start_date
    )
    hired_prev_result = await session.execute(hired_prev_query)
    hired_prev = hired_prev_result.scalar() or 0

    total_prev_query = select(func.count(Application.id)).where(
        Application.company_id == company_id,
        Application.created_at >= prev_start,
        Application.created_at < start_date
    )
    total_prev_result = await session.execute(total_prev_query)
    total_prev = total_prev_result.scalar() or 0

    previous = (hired_prev / total_prev * 100) if total_prev > 0 else 0.0

    return current, previous


async def _get_cost_per_hire(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Стоимость найма - TODO: нет источника данных"""
    # TODO: Implement when cost tracking is available
    return 0.0, 0.0 if period_days is not None else None


async def _get_recruiter_response_speed(session: AsyncSession, company_id: UUID, period_days: int | None) -> tuple[float, float | None]:
    """Скорость отклика рекрутеров"""
    from ...models import Message
    now = datetime.now(timezone.utc)

    if period_days is None:
        # Все время
        first_out_sent = (
            select(func.min(Message.sent_at))
            .where(
                Message.application_id == Application.id,
                Message.direction == 'out',
                Message.sender_type.in_(['recruiter', 'ai']),
            )
            .scalar_subquery()
        )

        stmt = (
            select(
                func.avg(
                    func.extract('epoch', first_out_sent - Application.created_at) / 3600.0
                )
            )
            .select_from(Application)
            .where(
                Application.company_id == company_id,
                first_out_sent.is_not(None),  # только те у кого есть ответ
            )
        )
        result = await session.execute(stmt)
        current = result.scalar()
        return float(current) if current else 0.0, None

    # Текущий период
    start_date = now - timedelta(days=period_days)

    first_out_sent = (
        select(func.min(Message.sent_at))
        .where(
            Message.application_id == Application.id,
            Message.direction == 'out',
            Message.sender_type.in_(['recruiter', 'ai']),
        )
        .scalar_subquery()
    )

    current_stmt = (
        select(
            func.avg(
                func.extract('epoch', first_out_sent - Application.created_at) / 3600.0
            )
        )
        .select_from(Application)
        .where(
            Application.company_id == company_id,
            Application.created_at >= start_date,
            Application.created_at < now,
            first_out_sent.is_not(None),  # только те у кого есть ответ
        )
    )
    current_result = await session.execute(current_stmt)
    current = current_result.scalar()
    current_value = float(current) if current else 0.0

    # Предыдущий период
    prev_start = start_date - timedelta(days=period_days)

    prev_stmt = (
        select(
            func.avg(
                func.extract('epoch', first_out_sent - Application.created_at) / 3600.0
            )
        )
        .select_from(Application)
        .where(
            Application.company_id == company_id,
            Application.created_at >= prev_start,
            Application.created_at < start_date,
            first_out_sent.is_not(None),  # только те у кого есть ответ
        )
    )
    prev_result = await session.execute(prev_stmt)
    previous = prev_result.scalar()
    previous_value = float(previous) if previous else 0.0

    return current_value, previous_value


async def compute_home_kpi(session: AsyncSession, company_id: UUID, period: str = 'month', extended: bool = False) -> HomeKpi:
    """Вычисляет KPI для главной страницы"""
    period_days = parse_home_period(period)

    # Базовые KPI
    kpi_funcs = [
        ('open_vacancies', None, _get_open_vacancies, False),
        ('closed_vacancies', None, _get_closed_vacancies, False),
        ('avg_time_to_hire', 'дней', _get_avg_time_to_hire, True),
        ('turnover_90d', '%', _get_turnover_90d, True),
        ('active_candidates', None, _get_active_candidates, False),
        ('conversion', '%', _get_conversion, False),
    ]

    # Расширенные KPI
    if extended:
        kpi_funcs.extend([
            ('cost_per_hire', '₽', _get_cost_per_hire, True),
            ('recruiter_response_speed', 'часа', _get_recruiter_response_speed, True),
        ])

    cards = []

    for key, unit, kpi_func, lower_is_better in kpi_funcs:
        current, previous = await kpi_func(session, company_id, period_days)

        # Специальная обработка для recruiter_response_speed
        if key == 'recruiter_response_speed' and current == 0.0:
            # Проверяем действительно ли нет данных
            has_data_query = select(func.count(Application.id)).select_from(Application).join(
                Message, Message.application_id == Application.id
            ).where(
                Application.company_id == company_id,
                Message.direction == 'out',
                Message.sender_type.in_(['recruiter', 'ai'])
            )

            if period_days is not None:
                now = datetime.now(timezone.utc)
                start_date = now - timedelta(days=period_days)
                has_data_query = has_data_query.where(
                    Application.created_at >= start_date,
                    Application.created_at < now
                )

            has_data_result = await session.execute(has_data_query)
            has_data = has_data_result.scalar() > 0

            if not has_data:
                card = KpiCard(
                    key=key,
                    value=None,
                    unit=unit,
                    delta=None,
                    delta_dir='flat',
                    caption='нет данных'
                )
                cards.append(card)
                continue

        # Округление для recruiter_response_speed
        if key == 'recruiter_response_speed' and current > 0:
            current = round(current, 1)
            if previous and previous > 0:
                previous = round(previous, 1)

        # Для period='all' delta всегда None
        if period == 'all':
            delta = None
            delta_dir = 'flat'
        else:
            delta = (current - previous) if previous is not None else None
            delta_dir = compute_delta_dir(current, previous, lower_is_better=lower_is_better)

        card = KpiCard(
            key=key,
            value=current,
            unit=unit,
            delta=delta,
            delta_dir=delta_dir,
            caption=None
        )
        cards.append(card)

    return HomeKpi(period=period, cards=cards)