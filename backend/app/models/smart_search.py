"""Модель умного поиска кандидатов"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, ForeignKey, Boolean, text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class SmartSearchRun(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "smart_search_runs"

    # Частичный уникальный индекс: не более одного активного (running) поиска на
    # (company, вакансия) — DB-атомарный guard против двойного запуска платного hh-сорсинга.
    # Дублирует индекс из миграции p7q8r9s0t1u2 (для prod через alembic), здесь — чтобы он
    # попадал и в create_all (тесты), и не давал autogenerate-дрейфа (модель↔миграция в синхроне).
    __table_args__ = (
        Index(
            "uq_smart_search_run_active",
            "company_id",
            "vacancy_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

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

    # Флаг пропуска приглашений (для превью режима)
    invites_skipped: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false")
    )

    # Новые поля для улучшенной отчётности
    scored_candidates: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb")
    )
    passed_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0")
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    log: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb")
    )

    # Relationships
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="smart_search_runs")
    company: Mapped["Company"] = relationship("Company")