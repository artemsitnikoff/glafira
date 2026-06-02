"""add hh_chat_id to applications

Revision ID: a1b2c3d4e5f6
Revises: f4e5d6c7a8b9
Create Date: 2026-06-02 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f4e5d6c7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add hh_chat_id column for new Chats API
    op.add_column('applications', sa.Column('hh_chat_id', sa.String(length=40), nullable=True))
    op.create_index('ix_applications_hh_chat_id', 'applications', ['hh_chat_id'], unique=False)


def downgrade() -> None:
    # Remove hh_chat_id column
    op.drop_index('ix_applications_hh_chat_id', table_name='applications')
    op.drop_column('applications', 'hh_chat_id')