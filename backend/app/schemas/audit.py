from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

from .base import ORMBase


class AuditLogOut(ORMBase):
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    actor_user_id: UUID | None
    actor_type: str
    changes: dict | None
    created_at: datetime
    ip: str | None