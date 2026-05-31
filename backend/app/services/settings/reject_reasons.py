from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from uuid import UUID

from ...models import RejectReason
from ...core.errors import NotFoundError, ValidationError
from ...services.audit import audit


async def list_reject_reasons(
    session: AsyncSession,
    company_id: UUID,
    side: Optional[str] = None,
    include_inactive: bool = False,
    vacancy_id: Optional[UUID] = None,
) -> list[RejectReason]:
    """List reject reasons.

    vacancy_id=None → дефолты компании (шаблон из Настроек, vacancy_id IS NULL).
    vacancy_id=X    → причины, привязанные к вакансии X.
    """
    query = select(RejectReason).where(RejectReason.company_id == company_id)

    if vacancy_id is None:
        query = query.where(RejectReason.vacancy_id.is_(None))
    else:
        query = query.where(RejectReason.vacancy_id == vacancy_id)

    if side:
        query = query.where(RejectReason.side == side)

    if not include_inactive:
        query = query.where(RejectReason.is_active == True)

    query = query.order_by(RejectReason.order_index, RejectReason.label)

    result = await session.execute(query)
    return list(result.scalars().all())


async def copy_default_reasons_to_vacancy(
    session: AsyncSession, company_id: UUID, vacancy_id: UUID
) -> None:
    """Копирует активные дефолты компании (vacancy_id IS NULL) в вакансию.
    Системность (is_system) сохраняется → у вакансии тоже ≥1 системная на сторону."""
    defaults = await list_reject_reasons(session, company_id, include_inactive=False, vacancy_id=None)
    for d in defaults:
        session.add(
            RejectReason(
                company_id=company_id,
                vacancy_id=vacancy_id,
                side=d.side,
                label=d.label,
                order_index=d.order_index,
                is_system=d.is_system,
                is_active=True,
            )
        )
    await session.flush()


async def ensure_vacancy_reject_reasons(
    session: AsyncSession, company_id: UUID, vacancy_id: UUID
) -> list[RejectReason]:
    """Инвариант: у вакансии всегда есть причины отказа.

    Если у вакансии их нет (старая вакансия до фичи / не скопированы) — копирует дефолты
    компании. Идемпотентна. Вызывающий обязан закоммитить (на GET — после сборки ответа).
    """
    existing = await list_reject_reasons(session, company_id, include_inactive=False, vacancy_id=vacancy_id)
    if existing:
        return existing
    await copy_default_reasons_to_vacancy(session, company_id, vacancy_id)
    return await list_reject_reasons(session, company_id, include_inactive=False, vacancy_id=vacancy_id)


async def create_reject_reason(
    session: AsyncSession, company_id: UUID, data, actor_user_id: UUID,
    vacancy_id: Optional[UUID] = None,
) -> RejectReason:
    """Create new reject reason (vacancy_id=None → дефолт компании; X → привязка к вакансии)"""
    if not data.label or not data.label.strip():
        raise ValidationError("label не может быть пустым")

    if data.side not in ("company", "candidate"):
        raise ValidationError("side должен быть 'company' или 'candidate'")

    reason = RejectReason(
        company_id=company_id,
        vacancy_id=vacancy_id,
        side=data.side,
        label=data.label.strip(),
        order_index=data.order_index or 0,
    )

    session.add(reason)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="create_reject_reason",
        entity_type="reject_reason",
        entity_id=reason.id,
        after={"side": reason.side, "label": reason.label, "order_index": reason.order_index},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return reason


async def update_reject_reason(
    session: AsyncSession, reason_id: UUID, company_id: UUID, data, actor_user_id: UUID,
    vacancy_id: Optional[UUID] = None,
) -> RejectReason:
    """Update reject reason (scoped: vacancy_id=None → дефолт компании; X → причина вакансии X)"""
    query = (
        select(RejectReason)
        .where(RejectReason.id == reason_id)
        .where(RejectReason.company_id == company_id)
    )
    if vacancy_id is None:
        query = query.where(RejectReason.vacancy_id.is_(None))
    else:
        query = query.where(RejectReason.vacancy_id == vacancy_id)
    result = await session.execute(query)
    reason = result.scalar_one_or_none()

    if not reason:
        raise NotFoundError("Причина отказа")

    # Store original values for audit
    before = {"label": reason.label, "order_index": reason.order_index, "is_active": reason.is_active}

    # Update fields
    if data.label is not None:
        if not data.label.strip():
            raise ValidationError("label не может быть пустым")
        reason.label = data.label.strip()

    if data.order_index is not None:
        reason.order_index = data.order_index

    if data.is_active is not None:
        reason.is_active = data.is_active

    await session.flush()

    # Audit log
    after = {"label": reason.label, "order_index": reason.order_index, "is_active": reason.is_active}

    await audit(
        session,
        action="update_reject_reason",
        entity_type="reject_reason",
        entity_id=reason.id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return reason


async def delete_reject_reason(
    session: AsyncSession, reason_id: UUID, company_id: UUID, actor_user_id: UUID,
    vacancy_id: Optional[UUID] = None,
) -> RejectReason:
    """Soft delete reject reason (scoped: vacancy_id=None → дефолт компании; X → причина вакансии X)"""
    query = (
        select(RejectReason)
        .where(RejectReason.id == reason_id)
        .where(RejectReason.company_id == company_id)
    )
    if vacancy_id is None:
        query = query.where(RejectReason.vacancy_id.is_(None))
    else:
        query = query.where(RejectReason.vacancy_id == vacancy_id)
    result = await session.execute(query)
    reason = result.scalar_one_or_none()

    if not reason:
        raise NotFoundError("Причина отказа")

    # Системную причину удалять нельзя — гарантия непустоты (≥1 на каждую сторону).
    if reason.is_system:
        raise ValidationError("Системную причину отказа нельзя удалить")

    # Store original values for audit
    before = {"is_active": reason.is_active}

    reason.is_active = False
    await session.flush()

    # Audit log
    after = {"is_active": reason.is_active}

    await audit(
        session,
        action="delete_reject_reason",
        entity_type="reject_reason",
        entity_id=reason.id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return reason


async def reorder_reject_reasons(
    session: AsyncSession, company_id: UUID, side: str, reason_ids: list[UUID], actor_user_id: UUID
) -> None:
    """Reorder reject reasons by side"""
    if side not in ("company", "candidate"):
        raise ValidationError("side должен быть 'company' или 'candidate'")

    if not reason_ids:
        raise ValidationError("Список идентификаторов не может быть пустым")

    # Get existing reasons
    result = await session.execute(
        select(RejectReason)
        .where(
            RejectReason.company_id == company_id,
            RejectReason.side == side
        )
    )
    reasons = {reason.id: reason for reason in result.scalars().all()}

    # Validate all reasons exist
    for reason_id in reason_ids:
        if reason_id not in reasons:
            raise ValidationError(f"Причина отказа '{reason_id}' не найдена")

    # Store original order for audit
    before = {str(reason.id): reason.order_index for reason in reasons.values()}

    # Update order_index
    for new_index, reason_id in enumerate(reason_ids, start=1):
        reasons[reason_id].order_index = new_index

    await session.flush()

    # Store new order for audit
    after = {str(reason.id): reason.order_index for reason in reasons.values()}

    # Audit log
    await audit(
        session,
        action="reorder_reject_reasons",
        entity_type="reject_reason",
        entity_id=None,  # Multiple entities affected
        before={"side": side, "order": before},
        after={"side": side, "order": after},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )