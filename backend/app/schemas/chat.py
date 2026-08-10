"""Pydantic-схемы модуля «Чаты» (фаза 2 — агрегаты поверх единой ленты сообщений).

Лента и отправка сообщений — СУЩЕСТВУЮЩИЕ `GET/POST /candidates/{id}/messages`
(schemas/message.py::MessageOut/MessageCreate). Здесь только НОВЫЕ агрегаты для
попапа сайдбара и шапки/композера обоих UI: список диалогов, суммарный бейдж
непрочитанных и мета доступных каналов.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChatDialogOut(BaseModel):
    """Один диалог = один кандидат (человек), не per-application.

    Контекст (vacancy_id/vacancy_name/channel/preview) — от ПОСЛЕДНЕГО сообщения
    диалога. unread_count — пер-юзер (из chats.unread_counts_bulk, без N+1).
    """
    candidate_id: UUID
    name: str
    avatar_url: str | None = None
    vacancy_id: UUID | None = None
    vacancy_name: str | None = None
    channel: str
    preview: str
    sent_at: datetime
    last_sender_type: str
    unread_count: int
    # Момент последнего входящего — для честного «был на связи» (не online-presence).
    last_inbound_at: datetime | None = None


class ChatUnreadTotal(BaseModel):
    """Суммарно непрочитанных по всем диалогам юзера — бейдж сайдбара (лёгкий поллинг)."""
    total: int


class ChatMetaOut(BaseModel):
    """Мета каналов кандидата для композера/шапки чата (единая для попапа и вкладки).

    В available_channels — ТОЛЬКО реально доступные каналы (подмножество
    ['telegram','hh']). hh попадает СТРОГО при наличии Application.hh_chat_id.
    Max/WhatsApp/SMS/Email сюда НЕ входят. Статусов доставки/«онлайн» здесь нет —
    каналы их честно не отдают.
    """
    candidate_id: UUID
    hh_available: bool
    telegram_available: bool
    last_inbound_at: datetime | None = None
    last_inbound_channel: str | None = None
    default_channel: str | None = None
    available_channels: list[str]


class MarkReadOut(BaseModel):
    """Ответ POST .../messages/read: диалог помечен прочитанным (unread обнулён)."""
    ok: bool
    unread: int


class ChatReadAllOut(BaseModel):
    """Ответ POST /chats/read-all: помечены прочитанными ВСЕ диалоги юзера.

    marked — число затронутых диалогов (кандидатов с входящими). Пер-юзер: чужие
    ReadState не тронуты.
    """
    ok: bool
    marked: int
