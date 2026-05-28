"""Audit log API endpoints"""

from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...deps import get_current_company_id
from ...schemas.base import Paginated
from ...schemas.audit import AuditLogOut
from ...services.audit_log import get_audit_logs_paginated
from ...core.permissions import require_admin

router = APIRouter()


@router.get("", response_model=Paginated[AuditLogOut])
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    entity_type: str | None = Query(None),
    actor_user_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_admin),  # Requires admin role
):
    """Get audit logs with filters - admin only"""
    return await get_audit_logs_paginated(
        session=session,
        company_id=company_id,
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
    )