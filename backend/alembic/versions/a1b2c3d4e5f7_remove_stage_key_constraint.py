"""remove stage_key constraint to allow custom stages

Revision ID: a1b2c3d4e5f7
Revises: d3b8f2a91c4e
Create Date: 2026-05-30 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'd3b8f2a91c4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the check constraint that limits stage_key values
    op.drop_constraint('check_stage_key', 'vacancy_stages', type_='check')


def downgrade() -> None:
    # Restore the original check constraint
    op.create_check_constraint(
        'check_stage_key',
        'vacancy_stages',
        "stage_key IN ('response', 'selected', 'recruiter', 'interview', 'test', 'manager', 'offer', 'hired', 'rejected', 'added')"
    )