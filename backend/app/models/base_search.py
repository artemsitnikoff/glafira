"""Модель поиска по собственной базе кандидатов"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, ForeignKey, text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
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

    # Статус выполнения
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'running'")
    )

    # Текущая стадия
    stage: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    # Количество кандидатов для оценки
    to_evaluate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0")
    )

    # Количество оценённых кандидатов
    evaluated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0")
    )

    # Финальные результаты поиска
    results: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb")
    )

    # Критерии поиска
    criteria: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Эхо запроса
    query_echo: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Название вакансии
    vacancy_title: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Ошибка (если есть)
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Время завершения (naive UTC как в SmartSearchRun)
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    # Relationships
    vacancy: Mapped[Optional["Vacancy"]] = relationship("Vacancy")
    company: Mapped["Company"] = relationship("Company")