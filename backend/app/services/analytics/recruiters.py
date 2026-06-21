"""Analytics: Recruiters отчёт"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, and_, desc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from ...core.periods import resolve_analytics_window
from ...models import Application, StageHistory, Vacancy, User
from ...schemas.analytics import AnalyticsResponse, ChartData, TableData, TableColumn
from .common import AnalyticsFilters, apply_vacancy_filter


async def _build_leaderboard_table(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> TableData:
    """Таблица лидерборда рекрутёров"""
    start_date, end_date = window

    # Базовый запрос по рекрутёрам
    recruiter_query = select(
        User.id.label('recruiter_id'),
        User.full_name.label('recruiter_name'),
        func.count(func.distinct(case((Vacancy.status == 'active', Vacancy.id)))).label('vacancies_active'),
        func.count(func.distinct(Application.id)).label('applications_handled')
    ).select_from(
        Vacancy.__table__.join(User.__table__, Vacancy.responsible_user_id == User.id).outerjoin(
            Application.__table__, and_(
                Application.vacancy_id == Vacancy.id,
                Application.created_at >= datetime.combine(start_date, datetime.min.time()),
                Application.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
            )
        )
    ).where(
        Vacancy.company_id == company_id
    ).group_by(User.id, User.full_name)

    # Фильтр по recruiter_ids для recruiters отчёта означает фильтр кого показать в лидерборде
    if filters.recruiter_ids:
        recruiter_query = recruiter_query.where(User.id.in_(filters.recruiter_ids))

    if filters.vacancy_ids:
        recruiter_query = recruiter_query.where(Vacancy.id.in_(filters.vacancy_ids))

    result = await session.execute(recruiter_query)
    recruiter_data = {
        row.recruiter_id: {
            'recruiter_id': str(row.recruiter_id),
            'recruiter_name': row.recruiter_name,
            'vacancies_active': row.vacancies_active or 0,
            'applications_handled': row.applications_handled or 0,
            'screenings': 0,
            'interviews': 0,
            'hires': 0,
            'avg_time_to_hire': 0.0,
            'glafira_autonomy_pct': 0.0
        }
        for row in result
    }

    # Дополняем данными по StageHistory
    for recruiter_id in recruiter_data.keys():
        # Скрининги: переходы to_stage='selected'
        screening_query = select(func.count(StageHistory.id)).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id,
            StageHistory.to_stage == 'selected',
            StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
            StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

        screening_result = await session.execute(screening_query)
        recruiter_data[recruiter_id]['screenings'] = screening_result.scalar() or 0

        # Интервью: переходы to_stage='interview'
        interview_query = select(func.count(StageHistory.id)).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id,
            StageHistory.to_stage == 'interview',
            StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
            StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

        interview_result = await session.execute(interview_query)
        recruiter_data[recruiter_id]['interviews'] = interview_result.scalar() or 0

        # Найм: переходы to_stage='hired'
        hires_query = select(func.count(StageHistory.id)).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id,
            StageHistory.to_stage == 'hired',
            StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
            StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

        hires_result = await session.execute(hires_query)
        recruiter_data[recruiter_id]['hires'] = hires_result.scalar() or 0

        # Среднее время до найма - упрощенно от начала заявки
        time_to_hire_query = select(
            func.avg(
                func.extract('epoch',
                    StageHistory.created_at - Application.created_at
                ) / 86400
            )
        ).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id,
            StageHistory.to_stage == 'hired',
            StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
            StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

        time_result = await session.execute(time_to_hire_query)
        avg_time = time_result.scalar()
        recruiter_data[recruiter_id]['avg_time_to_hire'] = round(avg_time, 1) if avg_time is not None else 0.0

        # Автономия Глафиры: доля AI-переходов
        total_transitions_query = select(func.count(StageHistory.id)).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id,
            StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
            StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

        total_transitions_result = await session.execute(total_transitions_query)
        total_transitions = total_transitions_result.scalar() or 0

        if total_transitions > 0:
            ai_transitions_query = select(func.count(StageHistory.id)).select_from(
                StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
                .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
            ).where(
                Application.company_id == company_id,
                Vacancy.responsible_user_id == recruiter_id,
                StageHistory.actor_type == 'ai',
                StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
                StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
            )

            ai_transitions_result = await session.execute(ai_transitions_query)
            ai_transitions = ai_transitions_result.scalar() or 0

            recruiter_data[recruiter_id]['glafira_autonomy_pct'] = round((ai_transitions / total_transitions) * 100, 1)

    # Сортируем по количеству найма и добавляем ранги
    sorted_recruiters = sorted(recruiter_data.values(), key=lambda x: x['hires'], reverse=True)

    rows = []
    for rank, recruiter in enumerate(sorted_recruiters, 1):
        recruiter['rank'] = rank
        rows.append(recruiter)

    columns = [
        TableColumn(key='rank', label='Место', type='mono'),
        TableColumn(key='recruiter_name', label='Рекрутёр', type='text'),
        TableColumn(key='vacancies_active', label='Активных вакансий', type='mono'),
        TableColumn(key='applications_handled', label='Заявок обработано', type='mono'),
        TableColumn(key='screenings', label='Скрининги', type='mono'),
        TableColumn(key='interviews', label='Интервью', type='mono'),
        TableColumn(key='hires', label='Найма', type='mono'),
        TableColumn(key='avg_time_to_hire', label='Время найма (дни)', type='mono'),
        TableColumn(key='glafira_autonomy_pct', label='Автономия Глафиры (%)', type='mono')
    ]

    return TableData(
        title='Лидерборд рекрутёров',
        columns=columns,
        rows=rows
    )


async def _build_hires_bar_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Bar chart: найма по рекрутёрам (топ-10)"""
    start_date, end_date = window

    query = select(
        User.full_name,
        func.count(StageHistory.id).label('hires')
    ).select_from(
        StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
        .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        .join(User.__table__, Vacancy.responsible_user_id == User.id)
    ).where(
        Application.company_id == company_id,
        StageHistory.to_stage == 'hired',
        StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
        StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(User.id, User.full_name).order_by(func.count(StageHistory.id).desc()).limit(10)

    if filters.recruiter_ids:
        query = query.where(User.id.in_(filters.recruiter_ids))

    if filters.vacancy_ids:
        query = query.where(Vacancy.id.in_(filters.vacancy_ids))

    result = await session.execute(query)
    items = [{'recruiter': row.full_name, 'value': row.hires} for row in result]

    return ChartData(
        type='bar',
        title='Найма по рекрутёрам',
        data={'items': items}
    )


async def _build_radar_chart(session: AsyncSession, company_id: UUID, window: tuple, filters: AnalyticsFilters) -> ChartData:
    """Radar chart: сравнение топ-3 рекрутёров"""
    start_date, end_date = window

    # Получаем топ-3 по найму
    top3_query = select(
        User.id,
        User.full_name,
        func.count(StageHistory.id).label('hires')
    ).select_from(
        StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
        .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        .join(User.__table__, Vacancy.responsible_user_id == User.id)
    ).where(
        Application.company_id == company_id,
        StageHistory.to_stage == 'hired',
        StageHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
        StageHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    ).group_by(User.id, User.full_name).order_by(func.count(StageHistory.id).desc()).limit(3)

    if filters.recruiter_ids:
        top3_query = top3_query.where(User.id.in_(filters.recruiter_ids))

    if filters.vacancy_ids:
        top3_query = top3_query.where(Vacancy.id.in_(filters.vacancy_ids))

    top3_result = await session.execute(top3_query)
    top3_recruiters = [(row.id, row.full_name, row.hires) for row in top3_result]

    if len(top3_recruiters) == 0:
        return ChartData(
            type='radar',
            title='Сравнение топ-рекрутёров',
            data={'axes': [], 'series': []}
        )

    # Оси для радара
    axes = ['скорость', 'объём', 'качество', 'автономия', 'конверсия']

    series = []
    for recruiter_id, recruiter_name, hires in top3_recruiters:
        # Расчёт метрик для нормализации

        # Скорость (обратная к времени найма) - упрощенно от начала заявки
        speed_query = select(
            func.avg(
                func.extract('epoch',
                    StageHistory.created_at - Application.created_at
                ) / 86400
            )
        ).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id,
            StageHistory.to_stage == 'hired'
        )

        speed_result = await session.execute(speed_query)
        avg_time = speed_result.scalar()
        # Если нет данных по времени найма — ось «скорость» исключается из расчёта (0).
        # Фронт ожидает number[], ?? 0 на клиенте тоже даёт 0 — поведение согласовано.
        speed_score = max(0, 100 - avg_time) if avg_time is not None else 0

        # Объём (количество найма)
        volume_score = min(100, hires * 10)  # нормализация

        # Качество: средний AI-скоринг нанятых; без данных — 0 (нет фейк-50)
        quality_query = select(func.avg(Application.ai_score)).select_from(
            Application.__table__.join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id,
            Application.stage == 'hired',
            Application.ai_score.is_not(None)
        )

        quality_result = await session.execute(quality_query)
        quality_score = quality_result.scalar() or 0  # 0 = нет данных, не фейк-50

        # Автономия Глафиры
        autonomy_query = select(
            func.count(case((StageHistory.actor_type == 'ai', 1))),
            func.count(StageHistory.id)
        ).select_from(
            StageHistory.__table__.join(Application.__table__, StageHistory.application_id == Application.id)
            .join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id
        )

        autonomy_result = await session.execute(autonomy_query)
        autonomy_row = autonomy_result.first()
        ai_count = autonomy_row[0] or 0
        total_count = autonomy_row[1] or 1
        autonomy_score = round((ai_count / total_count) * 100, 1)

        # Конверсия: hired / applications
        conversion_query = select(
            func.count(case((Application.stage == 'hired', 1))),
            func.count(Application.id)
        ).select_from(
            Application.__table__.join(Vacancy.__table__, Application.vacancy_id == Vacancy.id)
        ).where(
            Application.company_id == company_id,
            Vacancy.responsible_user_id == recruiter_id
        )

        conversion_result = await session.execute(conversion_query)
        conversion_row = conversion_result.first()
        hired_count = conversion_row[0] or 0
        total_applications = conversion_row[1] or 1
        conversion_score = round((hired_count / total_applications) * 100, 1)

        series.append({
            'name': recruiter_name,
            'values': [
                round(speed_score, 1),
                round(volume_score, 1),
                round(quality_score, 1),
                round(autonomy_score, 1),
                round(conversion_score, 1)
            ]
        })

    return ChartData(
        type='radar',
        title='Сравнение топ-рекрутёров',
        data={
            'axes': axes,
            'series': series
        }
    )


async def build_recruiters(session: AsyncSession, filters: AnalyticsFilters, company_id: UUID) -> AnalyticsResponse:
    """Строит отчёт Recruiters"""
    window = resolve_analytics_window(filters.period, filters.date_from, filters.date_to)

    tables = [
        await _build_leaderboard_table(session, company_id, window, filters)
    ]

    charts = [
        await _build_hires_bar_chart(session, company_id, window, filters),
        await _build_radar_chart(session, company_id, window, filters)
    ]

    return AnalyticsResponse(
        report='recruiters',
        period=filters.period,
        kpis=None,
        charts=charts,
        tables=tables
    )