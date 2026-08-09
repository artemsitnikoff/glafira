"""add message_reads (пер-юзер состояние прочтения диалога с кандидатом)

Revision ID: f7a8b9c0d1e2
Revises: d5f6a7b8c9e2
Create Date: 2026-08-09

Фаза 1 модуля «Чаты»: таблица состояний прочтения. Диалог = кандидат, одна
строка на пару (user_id, candidate_id). last_read_at — отметка «до какого
момента юзер прочитал диалог»; непрочитанность считается на лету сравнением с
Message.sent_at (см. services/chats.py). Message-таблица НЕ трогается (статусов
доставки не храним). Conversation не заводим.

⚠️ down_revision = d5f6a7b8c9e2 (add_vacancy_auto_test) — РЕАЛЬНАЯ и
ЕДИНСТВЕННАЯ голова, пересчитана по графу ревизий. Только create/drop новой
таблицы — существующие данные не затрагиваются.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "d5f6a7b8c9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_reads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_read_at", sa.TIMESTAMP(timezone=True), nullable=False),
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
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "candidate_id", name="uq_message_read_user_candidate"
        ),
    )
    op.create_index(
        "ix_message_reads_company_user",
        "message_reads",
        ["company_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_reads_company_user", table_name="message_reads")
    op.drop_table("message_reads")
