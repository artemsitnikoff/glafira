"""add hh_discard_synced_at to applications

Revision ID: d5e6f7a8b9c0
Revises: a1b2c3d4e5f6
Create Date: 2026-06-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add hh_discard_synced_at column for tracking sync status of rejected hh negotiations
    op.add_column('applications', sa.Column('hh_discard_synced_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_index('ix_applications_hh_discard_synced_at', 'applications', ['hh_discard_synced_at'], unique=False)


def downgrade() -> None:
    # Remove hh_discard_synced_at column
    op.drop_index('ix_applications_hh_discard_synced_at', table_name='applications')
    op.drop_column('applications', 'hh_discard_synced_at')