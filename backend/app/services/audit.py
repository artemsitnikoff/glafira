from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime, timezone

from ..models import AuditLog


async def audit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    before: dict | None = None,
    after: dict | None = None,
    actor_user_id: UUID,
    company_id: UUID,
    actor_type: str = "human"
) -> AuditLog:
    """Create audit log entry"""
    changes = {}
    if before is not None:
        changes["before"] = before
    if after is not None:
        changes["after"] = after

    audit_entry = AuditLog(
        company_id=company_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        created_at=datetime.now(timezone.utc)
    )

    session.add(audit_entry)
    await session.flush()
    return audit_entry