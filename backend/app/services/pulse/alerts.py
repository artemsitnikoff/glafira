"""Сервис для управления алертами пульса"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...core.errors import NotFoundError
from ...models import Employee, PulseAlert
from ...services.audit import audit


async def list_alerts(
    session: AsyncSession,
    company_id: UUID,
    dismissed: bool | None = None,
    period_days: int | None = None,
    manager_user_id: UUID | None = None,
) -> list[PulseAlert]:
    """Получает список алертов.

    Параметр manager_user_id (опциональный): если задан — возвращает только алерты
    сотрудников, у которых Employee.manager_user_id == manager_user_id.
    Используется для RBAC-скоупа роли manager.
    """

    query = select(PulseAlert).where(PulseAlert.company_id == company_id)

    if manager_user_id is not None:
        # Подзапрос: id сотрудников этого менеджера в рамках компании
        allowed_ids_sq = select(Employee.id).where(
            Employee.manager_user_id == manager_user_id,
            Employee.company_id == company_id,
        ).scalar_subquery()
        query = query.where(PulseAlert.employee_id.in_(allowed_ids_sq))

    if dismissed is not None:
        query = query.where(PulseAlert.is_dismissed == dismissed)

    if period_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        query = query.where(PulseAlert.created_at >= cutoff)

    query = query.order_by(PulseAlert.created_at.desc())

    result = await session.execute(query)
    return result.scalars().all()


async def dismiss_alert(
    session: AsyncSession,
    *,
    alert_id: UUID,
    company_id: UUID,
    actor_user_id: UUID,
) -> None:
    """Скрывает алерт"""

    # Проверяем, что алерт существует и принадлежит компании
    query = select(PulseAlert).where(
        PulseAlert.id == alert_id,
        PulseAlert.company_id == company_id
    )
    result = await session.execute(query)
    alert = result.scalar_one_or_none()

    if not alert:
        raise NotFoundError("Алерт")

    # Обновляем статус
    update_stmt = update(PulseAlert).where(
        PulseAlert.id == alert_id
    ).values(
        is_dismissed=True
    )

    await session.execute(update_stmt)

    # Audit log
    await audit(
        session,
        action="dismiss_alert",
        entity_type="pulse_alert",
        entity_id=alert.id,
        before={"is_dismissed": False},
        after={"is_dismissed": True},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()