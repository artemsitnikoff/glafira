"""Модель эмбеддингов кандидатов для семантического поиска"""

import uuid
from typing import Optional

from sqlalchemy import String, Text, ForeignKey, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from .base import Base, TimestampMixin


class CandidateEmbedding(Base, TimestampMixin):
    """Эмбеддинги кандидатов для семантического поиска"""

    __tablename__ = "candidate_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False
    )

    embedding: Mapped[list[float]] = mapped_column(
        Vector(384),  # paraphrase-multilingual-MiniLM-L12-v2 размерность
        nullable=False
    )

    source_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint('candidate_id', name='uq_candidate_embedding_candidate_id'),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    candidate: Mapped["Candidate"] = relationship("Candidate")