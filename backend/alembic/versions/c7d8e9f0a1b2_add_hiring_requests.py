"""add hiring requests module (заявки на подбор)

Revision ID: c7d8e9f0a1b2
Revises: f5a6b7c8d9e1
Create Date: 2026-07-18

Модуль «Заявки на подбор»: таблицы hiring_requests / request_comments /
request_funnel_stages / request_settings; связь 1:1 vacancies.request_id;
роль hiring_manager (CHECK users.role); тип события 'request' (CHECK events.type)
+ events.request_id.

⚠️ Циклическая FK: hiring_requests.vacancy_id → vacancies.id И vacancies.request_id →
hiring_requests.id. Обе таблицы создаём БЕЗ этих FK, затем добавляем create_foreign_key
после существования обеих.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "f5a6b7c8d9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── hiring_requests (vacancy_id FK добавим позже) ──────────────────────────
    op.create_table(
        "hiring_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("num", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("positions", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("salary_from", sa.Integer(), nullable=True),
        sa.Column("salary_to", sa.Integer(), nullable=True),
        sa.Column("employment_format", sa.String(length=20), nullable=True),
        sa.Column("priority", sa.String(length=10), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("status", sa.String(length=40), server_default=sa.text("'new'"), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("via", sa.String(length=10), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("author_name", sa.String(length=160), nullable=True),
        sa.Column("author_role", sa.String(length=160), nullable=True),
        sa.Column("author_contact", sa.String(length=200), nullable=True),
        sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("closed_note", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("priority IN ('normal', 'high')", name="check_request_priority"),
        sa.CheckConstraint("via IN ('cabinet', 'form', 'manual')", name="check_request_via"),
        sa.UniqueConstraint("company_id", "num", name="uq_request_company_num"),
        sa.UniqueConstraint("vacancy_id", name="uq_request_vacancy"),
    )
    op.create_index("ix_hiring_requests_company_status", "hiring_requests", ["company_id", "status"])
    op.create_index("ix_hiring_requests_company_author", "hiring_requests", ["company_id", "author_user_id"])

    # ── vacancies.request_id + FK (обе таблицы теперь существуют) ─────────────
    op.add_column("vacancies", sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_vacancies_request_id", "vacancies", "hiring_requests",
        ["request_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_hiring_requests_vacancy_id", "hiring_requests", "vacancies",
        ["vacancy_id"], ["id"], ondelete="SET NULL",
    )

    # ── request_comments ──────────────────────────────────────────────────────
    op.create_table(
        "request_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_name", sa.String(length=160), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["hiring_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("side IN ('recruiter', 'manager')", name="check_request_comment_side"),
    )
    op.create_index("ix_request_comments_request", "request_comments", ["request_id", "created_at"])

    # ── request_funnel_stages ────────────────────────────────────────────────
    op.create_table(
        "request_funnel_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "stage_key", name="uq_request_stage_company_key"),
    )

    # ── request_settings ──────────────────────────────────────────────────────
    op.create_table(
        "request_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("autoclose_on", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("question_moves_to_work", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notify_manager_on_stage", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("form_token", sa.String(length=64), nullable=True),
        sa.Column("form_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_request_settings_company"),
        sa.UniqueConstraint("form_token", name="uq_request_settings_form_token"),
    )

    # ── events.request_id + расширение CHECK type ────────────────────────────
    op.add_column("events", sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_events_request_id", "events", "hiring_requests",
        ["request_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("check_event_type", "events", type_="check")
    op.create_check_constraint(
        "check_event_type", "events",
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify', 'comment', 'document', 'interview', 'request')",
    )

    # ── роль hiring_manager (CHECK users.role) ───────────────────────────────
    op.drop_constraint("check_user_role", "users", type_="check")
    op.create_check_constraint(
        "check_user_role", "users",
        "role IN ('admin', 'recruiter', 'manager', 'hiring_manager')",
    )


def downgrade() -> None:
    # роль
    op.drop_constraint("check_user_role", "users", type_="check")
    op.create_check_constraint(
        "check_user_role", "users",
        "role IN ('admin', 'recruiter', 'manager')",
    )
    # events
    op.drop_constraint("check_event_type", "events", type_="check")
    op.create_check_constraint(
        "check_event_type", "events",
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify', 'comment', 'document', 'interview')",
    )
    op.drop_constraint("fk_events_request_id", "events", type_="foreignkey")
    op.drop_column("events", "request_id")
    # settings / stages / comments
    op.drop_table("request_settings")
    op.drop_table("request_funnel_stages")
    op.drop_index("ix_request_comments_request", table_name="request_comments")
    op.drop_table("request_comments")
    # разорвать циклические FK перед удалением hiring_requests
    op.drop_constraint("fk_vacancies_request_id", "vacancies", type_="foreignkey")
    op.drop_column("vacancies", "request_id")
    op.drop_constraint("fk_hiring_requests_vacancy_id", "hiring_requests", type_="foreignkey")
    op.drop_index("ix_hiring_requests_company_author", table_name="hiring_requests")
    op.drop_index("ix_hiring_requests_company_status", table_name="hiring_requests")
    op.drop_table("hiring_requests")
