"""Модель поиска по собственной базе кандидатов"""

import uuid
from typing import Optional

from sqlalchemy import String, Integer, Text, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class BaseSearchRun(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "base_search_runs"

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

    # Тип поиска: 'prompt' или 'vacancy'
    search_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    # Текст запроса или название вакансии
    query_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # ID вакансии (опционально, для типа 'vacancy')
    vacancy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Количество найденных кандидатов
    found: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0")
    )

    # Количество добавленных в воронку
    added_to_funnel: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0")
    )

    # Relationships
    vacancy: Mapped[Optional["Vacancy"]] = relationship("Vacancy")
    company: Mapped["Company"] = relationship("Company")