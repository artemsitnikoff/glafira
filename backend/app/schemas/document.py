from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

from .base import ORMBase


class DocumentOut(ORMBase):
    id: UUID
    filename: str
    file_type: str
    size_bytes: int
    source: str | None = None
    uploaded_by_name: str | None = None
    created_at: datetime