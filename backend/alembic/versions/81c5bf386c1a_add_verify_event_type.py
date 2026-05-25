"""add_verify_event_type

Revision ID: 81c5bf386c1a
Revises: 3f7b59cfb26a
Create Date: 2026-05-25 10:01:36.145135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81c5bf386c1a'
down_revision: Union[str, None] = '3f7b59cfb26a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing constraint
    op.drop_constraint('check_event_type', 'events', type_='check')

    # Create new constraint with 'verify' type added
    op.create_check_constraint(
        'check_event_type',
        'events',
        "type IN ('qual', 'new', 'score', 'offer', 'move', 'verify')"
    )


def downgrade() -> None:
    # Drop extended constraint
    op.drop_constraint('check_event_type', 'events', type_='check')

    # Restore original constraint
    op.create_check_constraint(
        'check_event_type',
        'events',
        "type IN ('qual', 'new', 'score', 'offer', 'move')"
    )