"""Сервис генерации AI-сводок сотрудников"""

from uuid import UUID
from datetime import datetime, date, timezone
from statistics import mean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from ...models.pulse import Employee, PulseSurvey
from ...models.audit import AuditLog
from ...core.errors import NotFoundError
from .client import call_text
from .prompts import build_employee_summary_prompt


async def generate_employee_summary(
    session: AsyncSession,
    employee_id: UUID,
    company_id: UUID,
    actor_user_id: UUID | None = None
) -> str | None:
    """Генерация AI-сводки для сотрудника

    Args:
        session: Async database session
        employee_id: ID сотрудника
        company_id: ID компании
        actor_user_id: ID пользователя, инициировавшего генерацию (None для AI)

    Returns:
        Сгенерированная сводка или None если данных недостаточно
    """

    # 1. Load employee с eager loading
    query = (
        select(Employee)
        .options(
            selectinload(Employee.surveys),
            selectinload(Employee.plan_items),
            selectinload(Employee.alerts)
        )
        .where(Employee.id == employee_id, Employee.company_id == company_id)
    )
    result = await session.execute(query)
    employee = result.scalar_one_or_none()

    if not employee:
        raise NotFoundError(f"Employee {employee_id} not found in company {company_id}")

    # 2. Filter answered surveys
    answered_surveys = [s for s in employee.surveys if s.answered_at is not None]

    # 3. Guard: если нет отвеченных опросов, очищаем сводку
    if len(answered_surveys) == 0:
        employee.ai_summary = None
        employee.ai_summary_generated_at = None

        # Audit log для пропуска
        audit_entry = AuditLog(
            company_id=company_id,
            actor_type='human' if actor_user_id else 'ai',
            actor_user_id=actor_user_id,
            action='employee_summary_skipped',
            entity_type='employee',
            entity_id=employee_id,
            changes={'reason': 'no_answered_surveys'}
        )
        session.add(audit_entry)

        return None

    # 4. Собираем facts
    # Сортируем опросы по дате отправки по убыванию
    answered_surveys_sorted = sorted(answered_surveys, key=lambda x: x.sent_at, reverse=True)

    # Вычисляем средний балл по последним опросам (до 3)
    recent_surveys = answered_surveys_sorted[:3]
    scores_with_values = [s.overall_score for s in recent_surveys if s.overall_score is not None]
    avg_score = mean(scores_with_values) if scores_with_values else None

    # Вычисляем тренд
    trend = _compute_trend(answered_surveys_sorted)

    # План адаптации
    plan_done = len([item for item in employee.plan_items if item.is_done])
    plan_total = len(employee.plan_items)

    # Просроченные элементы плана
    adapt_day = (date.today() - employee.start_date).days
    overdue_items = [
        item for item in employee.plan_items
        if item.deadline_day is not None
        and item.deadline_day < adapt_day
        and not item.is_done
    ]

    # Активные алерты
    active_alerts = [alert for alert in employee.alerts if not alert.is_dismissed]

    facts = {
        'full_name': employee.full_name,
        'position': employee.position,
        'adapt_day': adapt_day,
        'probation_days': employee.probation_days,
        'risk_level': employee.risk_level,
        'surveys_count': len(answered_surveys),
        'last_survey': {
            'sent_at': answered_surveys_sorted[0].sent_at.isoformat(),
            'overall_score': answered_surveys_sorted[0].overall_score
        } if answered_surveys_sorted else None,
        'avg_score': avg_score,
        'trend': trend,
        'plan_progress': {'done': plan_done, 'total': plan_total},
        'overdue_items': [item.title for item in overdue_items],
        'active_alerts': [
            {'level': alert.level, 'title': alert.title}
            for alert in active_alerts
        ]
    }

    # 5. Генерируем промпт и вызываем LLM
    system_prompt, user_prompt = build_employee_summary_prompt(facts)
    text = await call_text(system=system_prompt, user=user_prompt, max_tokens=1024)

    # 6. Сохраняем результат
    employee.ai_summary = text.strip()
    employee.ai_summary_generated_at = datetime.now(timezone.utc)

    # 7. Audit log для успешной генерации (БЕЗ PII)
    audit_entry = AuditLog(
        company_id=company_id,
        actor_type='human' if actor_user_id else 'ai',
        actor_user_id=actor_user_id,
        action='employee_summary_generated',
        entity_type='employee',
        entity_id=employee_id,
        changes={
            'after': {
                'length': len(text.strip()),
                'has_summary': True,
                'surveys_count': len(answered_surveys)
            }
        }
    )
    session.add(audit_entry)

    return text.strip()


def _compute_trend(answered_surveys: list[PulseSurvey]) -> str | None:
    """Вычисляет тренд удовлетворённости по последним опросам

    Args:
        answered_surveys: Список опросов, отсортированный по дате по убыванию

    Returns:
        'rising', 'falling', 'stable' или None если недостаточно данных
    """
    if len(answered_surveys) < 2:
        return None

    # Берём последние 2-3 опроса с оценками
    recent_with_scores = [
        s for s in answered_surveys[:3]
        if s.overall_score is not None
    ]

    if len(recent_with_scores) < 2:
        return None

    scores = [s.overall_score for s in recent_with_scores]
    # Поскольку сортировка по убыванию даты, первый элемент - самый новый
    # Обращаем порядок для анализа тренда (от старого к новому)
    scores.reverse()

    if len(scores) == 2:
        if scores[1] > scores[0]:
            return 'rising'
        elif scores[1] < scores[0]:
            return 'falling'
        else:
            return 'stable'

    # Для 3+ точек проверяем монотонность
    if all(scores[i] <= scores[i+1] for i in range(len(scores)-1)):
        return 'rising'
    elif all(scores[i] >= scores[i+1] for i in range(len(scores)-1)):
        return 'falling'
    else:
        return 'stable'