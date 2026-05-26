from pydantic import BaseModel, ConfigDict
from typing import Generic, TypeVar
from datetime import datetime
from uuid import UUID

T = TypeVar('T')


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class MessageResult(BaseModel):
    message: str


class StatusResult(BaseModel):
    status: str