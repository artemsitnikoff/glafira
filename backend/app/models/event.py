import uuid
from typing import Optional

from sqlalchemy import String, ForeignKey, CheckConstraint, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, CreatedAtMixin, CompanyMixin


class Event(Base, CreatedAtMixin, CompanyMixin):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        server_default=sql_text("'00000000-0000-0000-0000-000000000001'")
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sql_text("'[]'::jsonb"))
    candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=True
    )
    vacancy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="CASCADE"),
        nullable=True
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify')",
            name="check_event_type"
        ),
        CheckConstraint(
            "actor_type IN ('human', 'ai', 'system')",
            name="check_event_actor_type"
        ),
    )

    # Relationships
    actor_user: Mapped[Optional["User"]] = relationship("User")
    candidate: Mapped[Optional["Candidate"]] = relationship("Candidate")
    vacancy: Mapped[Optional["Vacancy"]] = relationship("Vacancy")