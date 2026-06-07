"""add message indexes

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-06-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add indexes for performance on messages table
    op.create_index('ix_messages_application_id', 'messages', ['application_id'])
    op.create_index('ix_messages_company_id', 'messages', ['company_id'])


def downgrade() -> None:
    # Remove indexes
    op.drop_index('ix_messages_application_id', 'messages')
    op.drop_index('ix_messages_company_id', 'messages')