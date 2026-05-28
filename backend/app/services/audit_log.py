"""Service for reading audit logs"""

from datetime import date
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog
from ..schemas.base import Paginated
from ..schemas.audit import AuditLogOut


async def get_audit_logs_paginated(
    session: AsyncSession,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24,
    entity_type: str | None = None,
    actor_user_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Paginated[AuditLogOut]:
    """Get paginated audit logs with filters"""

    # Base filters
    filters = [AuditLog.company_id == company_id]

    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)

    if actor_user_id:
        filters.append(AuditLog.actor_user_id == actor_user_id)

    if date_from:
        filters.append(AuditLog.created_at >= date_from)

    if date_to:
        # Include the whole day by adding time component
        from datetime import datetime, timezone
        date_to_end = datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc)
        filters.append(AuditLog.created_at <= date_to_end)

    # Count total
    from sqlalchemy import func
    count_result = await session.execute(
        select(func.count(AuditLog.id)).where(and_(*filters))
    )
    total = count_result.scalar_one()

    # Get paginated data
    offset = (page - 1) * page_size
    query = (
        select(AuditLog)
        .where(and_(*filters))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .offset(offset)
        .limit(page_size)
    )

    result = await session.execute(query)
    audit_logs = result.scalars().all()

    # Convert to schema
    items = [AuditLogOut.model_validate(log) for log in audit_logs]

    pages = (total + page_size - 1) // page_size

    return Paginated[AuditLogOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )