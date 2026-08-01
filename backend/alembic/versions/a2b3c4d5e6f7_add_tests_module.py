"""add tests module (когнитивное тестирование кандидатов)

Revision ID: a2b3c4d5e6f7
Revises: e6f7a8b9c0d1
Create Date: 2026-08-01

Фаза 1 модуля «Тесты» (data-слой): таблицы tests / test_blocks / test_items /
test_assignments / test_attempts / test_answers / test_results.

⚠️ correct_option_id (test_items) — ОТДЕЛЬНАЯ server-only колонка; тело задания
(body) и варианты (options) признака правильности НЕ содержат.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tests ──────────────────────────────────────────────────────────────────
    op.create_table(
        "tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("randomize_options", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("allow_back", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("category_thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("auto_reject_below", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('single', 'blocked')", name="check_test_kind"),
        sa.CheckConstraint("status IN ('active', 'draft')", name="check_test_status"),
        sa.UniqueConstraint("company_id", "key", name="uq_test_company_key"),
    )
    op.create_index("ix_tests_company", "tests", ["company_id"])

    # ── test_blocks ────────────────────────────────────────────────────────────
    op.create_table(
        "test_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_id"], ["tests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_id", "key", name="uq_test_block_key"),
    )
    op.create_index("ix_test_blocks_company", "test_blocks", ["company_id"])
    op.create_index("ix_test_blocks_test", "test_blocks", ["test_id"])

    # ── test_items (⚠️ correct_option_id — server-only колонка) ─────────────────
    op.create_table(
        "test_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("difficulty", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct_option_id", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_id"], ["tests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["block_id"], ["test_blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('matrix', 'text')", name="check_test_item_kind"),
    )
    op.create_index("ix_test_items_company", "test_items", ["company_id"])
    op.create_index("ix_test_items_test", "test_items", ["test_id", "order_index"])
    op.create_index("ix_test_items_block", "test_items", ["block_id"])

    # ── test_assignments ───────────────────────────────────────────────────────
    op.create_table(
        "test_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'sent'"), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_id"], ["tests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('sent', 'started', 'completed', 'expired', 'cancelled')",
            name="check_test_assignment_status",
        ),
        sa.UniqueConstraint("token", name="uq_test_assignment_token"),
    )
    op.create_index("ix_test_assignments_company", "test_assignments", ["company_id"])
    op.create_index("ix_test_assignments_application", "test_assignments", ["application_id"])

    # ── test_attempts ──────────────────────────────────────────────────────────
    op.create_table(
        "test_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consent_agreed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consent_ip", sa.String(length=64), nullable=True),
        sa.Column("current_block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_item_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("block_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("options_seed", sa.Integer(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'in_progress'"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id"], ["test_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_block_id"], ["test_blocks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'abandoned', 'expired')",
            name="check_test_attempt_status",
        ),
    )
    op.create_index("ix_test_attempts_company", "test_attempts", ["company_id"])
    op.create_index("ix_test_attempts_assignment", "test_attempts", ["assignment_id"])
    op.create_index("ix_test_attempts_application", "test_attempts", ["application_id"])

    # ── test_answers ───────────────────────────────────────────────────────────
    op.create_table(
        "test_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chosen_option_id", sa.String(length=40), nullable=True),
        sa.Column("is_correct", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("answered_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["test_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["test_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "item_id", name="uq_test_answer_attempt_item"),
    )
    op.create_index("ix_test_answers_company", "test_answers", ["company_id"])
    op.create_index("ix_test_answers_attempt", "test_answers", ["attempt_id"])

    # ── test_results ───────────────────────────────────────────────────────────
    op.create_table(
        "test_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("test_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("block_scores", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("percentile", sa.Integer(), nullable=True),
        sa.Column("validity_flags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id"], ["test_assignments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["test_id"], ["tests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_results_company", "test_results", ["company_id"])
    op.create_index("ix_test_results_application", "test_results", ["application_id"])
    op.create_index("ix_test_results_assignment", "test_results", ["assignment_id"])


def downgrade() -> None:
    # Обратный порядок (сначала зависимые таблицы).
    op.drop_index("ix_test_results_assignment", table_name="test_results")
    op.drop_index("ix_test_results_application", table_name="test_results")
    op.drop_index("ix_test_results_company", table_name="test_results")
    op.drop_table("test_results")

    op.drop_index("ix_test_answers_attempt", table_name="test_answers")
    op.drop_index("ix_test_answers_company", table_name="test_answers")
    op.drop_table("test_answers")

    op.drop_index("ix_test_attempts_application", table_name="test_attempts")
    op.drop_index("ix_test_attempts_assignment", table_name="test_attempts")
    op.drop_index("ix_test_attempts_company", table_name="test_attempts")
    op.drop_table("test_attempts")

    op.drop_index("ix_test_assignments_application", table_name="test_assignments")
    op.drop_index("ix_test_assignments_company", table_name="test_assignments")
    op.drop_table("test_assignments")

    op.drop_index("ix_test_items_block", table_name="test_items")
    op.drop_index("ix_test_items_test", table_name="test_items")
    op.drop_index("ix_test_items_company", table_name="test_items")
    op.drop_table("test_items")

    op.drop_index("ix_test_blocks_test", table_name="test_blocks")
    op.drop_index("ix_test_blocks_company", table_name="test_blocks")
    op.drop_table("test_blocks")

    op.drop_index("ix_tests_company", table_name="tests")
    op.drop_table("tests")
