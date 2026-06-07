"""Модель умного поиска кандидатов"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class SmartSearchRun(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "smart_search_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="RESTRICT"),
        nullable=False
    )

    # Статус выполнения
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'running'")
    )
    stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'search'")
    )

    # Параметры поиска (JSON с фильтрами + scan_n + invite_m + threshold)
    params: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb")
    )

    # Счетчики прогресса
    found: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    scanned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    evaluated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    invited: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # Список приглашенных кандидатов (JSON)
    invited_candidates: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb")
    )

    # Ошибка (если есть)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Время завершения
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="smart_search_runs")
    company: Mapped["Company"] = relationship("Company")