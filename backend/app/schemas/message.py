from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

from .base import ORMBase


class MessageOut(ORMBase):
    id: UUID
    channel: str
    direction: str
    sender_type: str
    sender_name: str | None = None
    body: str
    sent_at: datetime
    application_context: str | None = None
    vacancy_id: UUID | None = None
    # Отклик-владелец hh-треда (для ответа в ТОТ ЖЕ negotiation). TG → null.
    application_id: UUID | None = None


class MessageCreate(BaseModel):
    channel: str = "telegram"
    body: str
    application_id: UUID | None = None