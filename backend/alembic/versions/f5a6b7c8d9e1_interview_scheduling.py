"""Interview scheduling: users.b24_user_id, vacancies.auto_interview*, interview_links table, event type

Revision ID: f5a6b7c8d9e1
Revises: 3d4e5f6a7b8c
Create Date: 2026-07-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e1"
# Единственная реальная голова цепочки — 3d4e5f6a7b8c (проверено графом ревизий:
# y7z8a1b2c3d4/a9b0c1d2e3f4 — НЕ головы, а предки; на них чейнятся z8a1b2c3d4e5/
# b1c2d3e4f5a6). Один родитель. Итог — одна голова f5a6b7c8d9e1.
down_revision: Union[str, None] = "3d4e5f6a7b8c"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # --- users.b24_user_id ---
    op.add_column("users", sa.Column("b24_user_id", sa.Integer(), nullable=True))

    # --- vacancies.auto_interview, auto_interview_stage ---
    op.add_column(
        "vacancies",
        sa.Column("auto_interview", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "vacancies",
        sa.Column("auto_interview_stage", sa.String(64), nullable=True),
    )

    # --- interview_links table ---
    op.create_table(
        "interview_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("slot_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("slot_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("b24_event_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("booked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("token", name="uq_interview_links_token"),
        sa.CheckConstraint(
            "status IN ('active', 'booked', 'expired')",
            name="check_interview_link_status",
        ),
    )
    op.create_index("ix_interview_links_token", "interview_links", ["token"])
    op.create_index("ix_interview_links_application_id", "interview_links", ["application_id"])

    # --- Event.type: drop old constraint, recreate with 'interview' ---
    op.drop_constraint("check_event_type", "events", type_="check")
    op.create_check_constraint(
        "check_event_type",
        "events",
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify', 'comment', 'document', 'interview')",
    )


def downgrade() -> None:
    # Revert Event.type constraint
    op.drop_constraint("check_event_type", "events", type_="check")
    op.create_check_constraint(
        "check_event_type",
        "events",
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify', 'comment', 'document')",
    )

    # Drop interview_links
    op.drop_index("ix_interview_links_application_id", table_name="interview_links")
    op.drop_index("ix_interview_links_token", table_name="interview_links")
    op.drop_table("interview_links")

    # Drop vacancies columns
    op.drop_column("vacancies", "auto_interview_stage")
    op.drop_column("vacancies", "auto_interview")

    # Drop users column
    op.drop_column("users", "b24_user_id")
