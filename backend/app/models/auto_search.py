"""
AutoSearch — сохранённые автопоиски резюме hh (saved searches).
AutoSearchRun — прогон AI-оценки кандидатов автопоиска.

IMPORTANT: Частичный unique-индекс активного прогона (uq_auto_search_run_active)
намеренно НЕ объявлен в __table_args__. Если добавить его сюда через
Index(..., postgresql_where=...), SQLAlchemy включит его в create_all
тестовой БД — но там нет postgresql-синтаксиса WHERE, что ломает все тесты.
Индекс живёт ТОЛЬКО в alembic-миграции. Этот же паттерн используется
в SmartSearchRun (uq_smart_search_run_active) и CallSyncJob.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AutoSearch(Base, TimestampMixin):
    """Долгоживущий автопоиск hh (привязан к saved_search hh)."""

    __tablename__ = "auto_searches"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id",
            "hh_saved_search_id",
            name="uq_auto_search_company_hh",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        server_default=text("'00000000-0000-0000-0000-000000000001'"),
    )
    hh_saved_search_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    region: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    items_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    new_items_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    subscribed: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=text("false")
    )
    total: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    new_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    auto_eval: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=text("false")
    )
    basis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=False), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=False), nullable=True
    )

    # relationships
    company: Mapped["Company"] = relationship("Company")  # type: ignore[name-defined]


class AutoSearchRun(Base, TimestampMixin):
    """Прогон AI-оценки кандидатов для одного автопоиска.

    IMPORTANT: Частичный unique-индекс активного прогона (uq_auto_search_run_active)
    намеренно НЕ объявлен в __table_args__ — он живёт ТОЛЬКО в alembic-миграции.
    Причина: при включении в __table_args__ SQLAlchemy добавляет его в create_all
    тестовой БД, но postgresql_where не поддерживается в этом контексте → все тесты ломаются.
    Тот же паттерн в SmartSearchRun и CallSyncJob.
    """

    __tablename__ = "auto_search_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        server_default=text("'00000000-0000-0000-0000-000000000001'"),
    )
    auto_search_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("auto_searches.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=text("'running'")
    )
    stage: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    basis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    to_evaluate: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0")
    )
    evaluated: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=text("0")
    )
    scored_candidates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Прогон прерван (воркер убит деплоем/рестартом, не доехал). Ставится reconcile/
    # sweep при финализации мёртвого прогона. Self-heal cron находит такие и
    # авто-продолжает (skip_scored). Снимается, когда продолжение поставлено в очередь.
    interrupted: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    # ⚠️ TIMESTAMP БЕЗ timezone (наивный UTC) — как в SmartSearchRun/BaseSearchRun.
    # timezone=True вызывает asyncpg DataError при записи aware-datetime объектов.
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=False), nullable=True
    )

    # relationships
    auto_search: Mapped["AutoSearch"] = relationship("AutoSearch")
    company: Mapped["Company"] = relationship("Company")  # type: ignore[name-defined]
