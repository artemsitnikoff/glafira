"""Add source column to users

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Откуда заведён пользователь: 'manual' | 'b24'. Существующие → 'manual'.
    op.add_column(
        'users',
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
    )


def downgrade() -> None:
    op.drop_column('users', 'source')
