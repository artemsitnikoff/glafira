import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, CheckConstraint, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class Verification(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "verifications"

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
    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consents.id", ondelete="CASCADE"),
        nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    blocks: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('clean', 'info', 'warn', 'risk')",
            name="check_verification_status"
        ),
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate")
    consent: Mapped["Consent"] = relationship("Consent", back_populates="verifications")