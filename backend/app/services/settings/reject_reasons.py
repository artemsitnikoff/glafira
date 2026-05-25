from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from uuid import UUID

from ...models import RejectReason
from ...core.errors import NotFoundError, ValidationError
from ...services.audit import audit


async def list_reject_reasons(
    session: AsyncSession, company_id: UUID, side: Optional[str] = None, include_inactive: bool = False
) -> list[RejectReason]:
    """List reject reasons for company"""
    query = select(RejectReason).where(RejectReason.company_id == company_id)

    if side:
        query = query.where(RejectReason.side == side)

    if not include_inactive:
        query = query.where(RejectReason.is_active == True)

    query = query.order_by(RejectReason.order_index, RejectReason.label)

    result = await session.execute(query)
    return list(result.scalars().all())


async def create_reject_reason(
    session: AsyncSession, company_id: UUID, data, actor_user_id: UUID
) -> RejectReason:
    """Create new reject reason"""
    if not data.label or not data.label.strip():
        raise ValidationError("label не может быть пустым")

    if data.side not in ("company", "candidate"):
        raise ValidationError("side должен быть 'company' или 'candidate'")

    reason = RejectReason(
        company_id=company_id,
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
    session: AsyncSession, reason_id: UUID, company_id: UUID, data, actor_user_id: UUID
) -> RejectReason:
    """Update reject reason"""
    result = await session.execute(
        select(RejectReason)
        .where(RejectReason.id == reason_id)
        .where(RejectReason.company_id == company_id)
    )
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
    session: AsyncSession, reason_id: UUID, company_id: UUID, actor_user_id: UUID
) -> RejectReason:
    """Soft delete reject reason (set is_active=false)"""
    result = await session.execute(
        select(RejectReason)
        .where(RejectReason.id == reason_id)
        .where(RejectReason.company_id == company_id)
    )
    reason = result.scalar_one_or_none()

    if not reason:
        raise NotFoundError("Причина отказа")

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