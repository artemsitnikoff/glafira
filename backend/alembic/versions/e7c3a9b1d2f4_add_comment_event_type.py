"""add_comment_event_type

Revision ID: e7c3a9b1d2f4
Revises: aab4f3698d75
Create Date: 2026-05-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c3a9b1d2f4'
down_revision: Union[str, None] = 'aab4f3698d75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing constraint
    op.drop_constraint('check_event_type', 'events', type_='check')

    # Create new constraint with 'comment' type added
    op.create_check_constraint(
        'check_event_type',
        'events',
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify', 'comment')"
    )


def downgrade() -> None:
    # Drop extended constraint
    op.drop_constraint('check_event_type', 'events', type_='check')

    # Restore previous constraint (without 'comment')
    op.create_check_constraint(
        'check_event_type',
        'events',
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify')"
    )
