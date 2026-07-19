"""Модель ссылки для записи на интервью (одноразовая, по публичному токену)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, TIMESTAMP, ForeignKey, CheckConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class InterviewLink(Base):
    __tablename__ = "interview_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 'active' | 'booked' | 'expired'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    slot_from: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    slot_to: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    b24_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    booked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Сколько раз кандидат отменял/переносил встречу по этой ссылке. Отмена возвращает
    # статус в 'active' (кандидат выбирает время заново), поэтому лимит переносов
    # отслеживается этим счётчиком, а не статусом.
    reschedule_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("'0'")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'booked', 'expired')",
            name="check_interview_link_status",
        ),
    )

    # Relationships
    application: Mapped["Application"] = relationship("Application")
    company: Mapped["Company"] = relationship("Company")
