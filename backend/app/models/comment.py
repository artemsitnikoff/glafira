import uuid
from typing import Optional

from sqlalchemy import String, ForeignKey, Text, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, CreatedAtMixin, CompanyMixin


class Comment(Base, CreatedAtMixin, CompanyMixin):
    __tablename__ = "comments"

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
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=True
    )
    # NULLABLE: у комментария, импортированного с hh (source='hh'), нашего автора
    # (пользователя Глафиры) нет — имя автора-заметки хранится в author_name_ext.
    author_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Источник записи: 'manual' — ручной комментарий рекрутёра (наш автор),
    # 'hh' — импортированная заметка работодателя к резюме на hh (read-only).
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'manual'")
    )
    # id заметки на hh — дедуп при повторном синке (по образцу Message.external_id).
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Имя автора заметки с hh (когда author_user_id пуст).
    author_name_ext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'hh')",
            name="check_comment_source",
        ),
        # Дедуп hh-комментариев на уровне БД (company-scoped). Ручные комментарии
        # (external_id IS NULL, source='manual') под partial-условие не попадают.
        Index(
            "uq_comment_hh_external",
            "company_id",
            "external_id",
            unique=True,
            postgresql_where=text("source = 'hh'"),
        ),
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate")
    application: Mapped[Optional["Application"]] = relationship("Application")
    author: Mapped[Optional["User"]] = relationship("User")
