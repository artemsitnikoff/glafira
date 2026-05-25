"""Сервис для определения вакансий, требующих внимания"""

from datetime import datetime, timedelta, timezone, date
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...models import Vacancy, Application
from ...schemas.home import AttentionItem


async def compute_attention(session: AsyncSession, company_id: UUID) -> list[AttentionItem]:
    """Вычисляет список вакансий, требующих внимания"""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(hours=24)
    today = date.today()
    week_from_today = today + timedelta(days=7)

    attention_items = []

    # 1. URGENT: вакансии без новых applications за 7 дней
    urgent_query = select(
        Vacancy.id,
        Vacancy.name
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'active',
        ~Vacancy.id.in_(
            select(Application.vacancy_id).where(
                Application.company_id == company_id,
                Application.created_at >= week_ago
            ).distinct()
        )
    )

    urgent_result = await session.execute(urgent_query)
    urgent_vacancies = urgent_result.fetchall()

    for vacancy_id, vacancy_name in urgent_vacancies:
        attention_items.append(AttentionItem(
            vacancy_id=vacancy_id,
            vacancy_name=vacancy_name,
            kind='urgent',
            text='Нет движения 7+ дней'
        ))

    # 2. WARN: вакансии с необработанными откликами > 24ч
    warn_query = select(
        Vacancy.id,
        Vacancy.name,
        func.count(Application.id).label('count')
    ).select_from(
        Vacancy
    ).join(
        Application,
        and_(
            Application.vacancy_id == Vacancy.id,
            Application.stage == 'response',
            Application.created_at <= day_ago
        )
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'active'
    ).group_by(
        Vacancy.id,
        Vacancy.name
    ).having(
        func.count(Application.id) > 0
    )

    warn_result = await session.execute(warn_query)
    warn_vacancies = warn_result.fetchall()

    for vacancy_id, vacancy_name, count in warn_vacancies:
        if count == 1:
            text = 'Отклик ждёт ответа > 24ч'
        else:
            text = f'{count} необработанных откликов'

        attention_items.append(AttentionItem(
            vacancy_id=vacancy_id,
            vacancy_name=vacancy_name,
            kind='warn',
            text=text
        ))

    # 3. DEADLINE: вакансии с дедлайном ≤ 7 дней
    deadline_query = select(
        Vacancy.id,
        Vacancy.name,
        Vacancy.deadline
    ).where(
        Vacancy.company_id == company_id,
        Vacancy.status == 'active',
        Vacancy.deadline.is_not(None),
        Vacancy.deadline <= week_from_today
    )

    deadline_result = await session.execute(deadline_query)
    deadline_vacancies = deadline_result.fetchall()

    for vacancy_id, vacancy_name, deadline in deadline_vacancies:
        days_left = (deadline - today).days

        if days_left < 0:
            text = 'Дедлайн истёк'
        elif days_left == 0:
            text = 'Дедлайн сегодня'
        else:
            text = f'Дедлайн через {days_left} дней'

        attention_items.append(AttentionItem(
            vacancy_id=vacancy_id,
            vacancy_name=vacancy_name,
            kind='deadline',
            text=text
        ))

    # Сортировка по приоритету: urgent -> warn -> deadline
    # Внутри каждой группы по created_at DESC (приближение - используем имя)
    priority_order = {'urgent': 0, 'warn': 1, 'deadline': 2}
    attention_items.sort(key=lambda x: (priority_order[x.kind], x.vacancy_name))

    return attention_items