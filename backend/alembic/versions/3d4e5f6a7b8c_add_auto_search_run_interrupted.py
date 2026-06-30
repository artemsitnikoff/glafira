"""add interrupted flag to auto_search_runs (self-heal of interrupted evals)

Revision ID: 3d4e5f6a7b8c
Revises: 2c3d4e5f6a7b
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3d4e5f6a7b8c"
down_revision: str = "2c3d4e5f6a7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auto_search_runs",
        sa.Column("interrupted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("auto_search_runs", "interrupted")
