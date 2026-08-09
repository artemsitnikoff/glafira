"""Пер-юзер состояние прочтения диалога с кандидатом (модуль «Чаты», фаза 1).

Диалог = кандидат (одна строка на пару user↔candidate), НЕ per-application:
hh-треды одного кандидата делят один candidate-level счётчик непрочитанных —
этого достаточно для бейджа списка чатов и сайдбара.

Статусов доставки сообщений НЕ храним (каналы их честно не отдают) — состояние
прочтения выражено единственной отметкой last_read_at «до какого момента этот
юзер прочитал диалог». Непрочитанность вычисляется на лету сравнением с
Message.sent_at (см. services/chats.py). Отсутствие строки = диалог не открывали
→ все входящие непрочитаны.
"""
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class MessageRead(Base, TimestampMixin):
    __tablename__ = "message_reads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Мультитенантность (§2.3): все запросы дополнительно скоупятся по company_id.
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    # До какого момента этот юзер прочитал диалог с этим кандидатом.
    # Проставляется upsert-ом mark_read (последним прочитанным моментом / now).
    last_read_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    __table_args__ = (
        # Одна строка на пару (юзер, кандидат) — таргет ON CONFLICT для upsert.
        UniqueConstraint(
            "user_id", "candidate_id", name="uq_message_read_user_candidate"
        ),
        # Быстрый скан диалогов конкретного юзера в рамках компании.
        Index("ix_message_reads_company_user", "company_id", "user_id"),
    )

    # Relationships (lazy, только для навигации; в подсчётах не используются)
    company: Mapped["Company"] = relationship("Company")
    user: Mapped["User"] = relationship("User")
    candidate: Mapped["Candidate"] = relationship("Candidate")
