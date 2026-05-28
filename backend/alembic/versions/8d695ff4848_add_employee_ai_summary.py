"""add employee ai summary

Revision ID: 8d695ff4848
Revises: b5057cdcc35c
Create Date: 2026-05-28 12:04:17.786646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

# revision identifiers, used by Alembic.
revision: str = '8d695ff4848'
down_revision: Union[str, None] = '938e078d54a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add AI summary columns to employees table
    op.add_column("employees", sa.Column("ai_summary", sa.Text, nullable=True))
    op.add_column("employees", sa.Column("ai_summary_generated_at", TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove AI summary columns from employees table
    op.drop_column("employees", "ai_summary_generated_at")
    op.drop_column("employees", "ai_summary")