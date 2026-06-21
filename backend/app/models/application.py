import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, ForeignKey, CheckConstraint, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin, CreatedAtMixin


class Application(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        server_default=text("'00000000-0000-0000-0000-000000000001'")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="CASCADE"),
        nullable=False
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'response'"))
    ai_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_score_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    selected_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    stage_changed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    reject_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    reject_side: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_repeat: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hh_negotiation_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    hh_chat_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    hh_discard_synced_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    habr_response_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    avito_application_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Automation tracking fields
    auto_qa_asked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    auto_reject_suggested_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "reject_side IN ('candidate', 'company')",
            name="check_reject_side"
        ),
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="applications")
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="applications")
    stage_history: Mapped[list["StageHistory"]] = relationship(
        "StageHistory", back_populates="application"
    )


class StageHistory(Base, CreatedAtMixin):
    __tablename__ = "stage_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False
    )
    from_stage: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('human', 'ai', 'system')",
            name="check_actor_type"
        ),
    )

    # Relationships
    application: Mapped["Application"] = relationship("Application", back_populates="stage_history")
    actor_user: Mapped[Optional["User"]] = relationship("User")