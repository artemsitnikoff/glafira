"""add auto_search tables

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-21

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- auto_searches ---
    op.create_table(
        "auto_searches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("'00000000-0000-0000-0000-000000000001'"),
            nullable=False,
        ),
        sa.Column("hh_saved_search_id", sa.String(64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("items_url", sa.Text(), nullable=True),
        sa.Column("new_items_url", sa.Text(), nullable=True),
        sa.Column(
            "subscribed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("new_count", sa.Integer(), nullable=True),
        sa.Column(
            "auto_eval",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("basis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "hh_saved_search_id",
            name="uq_auto_search_company_hh",
        ),
    )

    # --- auto_search_runs ---
    op.create_table(
        "auto_search_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("'00000000-0000-0000-0000-000000000001'"),
            nullable=False,
        ),
        sa.Column("auto_search_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(20), nullable=True),
        sa.Column("basis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "to_evaluate",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "evaluated",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "scored_candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("log", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # ⚠️ TIMESTAMP БЕЗ timezone (наивный UTC) — как в smart_search_runs/base_search_runs
        sa.Column("finished_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["auto_search_id"],
            ["auto_searches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Частичный уникальный индекс: только один активный прогон на (company, auto_search)
    # Живёт ТОЛЬКО здесь (не в __table_args__ модели) — см. комментарий в AutoSearchRun
    op.create_index(
        "uq_auto_search_run_active",
        "auto_search_runs",
        ["company_id", "auto_search_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_auto_search_run_active", table_name="auto_search_runs")
    op.drop_table("auto_search_runs")
    op.drop_table("auto_searches")
