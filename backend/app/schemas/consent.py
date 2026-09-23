from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

from .base import ORMBase


class ConsentOut(ORMBase):
    id: UUID
    candidate_id: UUID
    number: str
    status: str
    channel: str | None = None
    signed_at: datetime | None = None
    requested_at: datetime | None = None
    expires_at: datetime | None = None
    signed_by: str | None = None


class ConsentRequestResult(ConsentOut):
    """Ответ на запрос согласия: сама запись + результат доставки ссылки кандидату.

    link — публичная ссылка подписания (рекрутёр может скопировать/переслать сам).
    delivered/delivery_channel/delivery_error — честный итог автоматической доставки:
    если канал недоступен или доставка упала, delivered=False (НЕ врём «отправлено»),
    но согласие всё равно создано и ссылка возвращена.
    """
    link: str
    delivered: bool
    delivery_channel: str | None = None
    delivery_error: str | None = None


class ConsentRequest(BaseModel):
    # None → сервер выберет канал автоматически (email → telegram → hh).
    channel: str | None = None
