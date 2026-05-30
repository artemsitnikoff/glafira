"""add_document_event_type

Revision ID: d3b8f2a91c4e
Revises: f1b2c3d4e5f6
Create Date: 2026-05-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3b8f2a91c4e'
down_revision: Union[str, None] = 'f1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing constraint
    op.drop_constraint('check_event_type', 'events', type_='check')

    # Create new constraint with 'document' type added
    op.create_check_constraint(
        'check_event_type',
        'events',
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify', 'comment', 'document')"
    )


def downgrade() -> None:
    # Drop extended constraint
    op.drop_constraint('check_event_type', 'events', type_='check')

    # Restore previous constraint (without 'document')
    op.create_check_constraint(
        'check_event_type',
        'events',
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify', 'comment')"
    )