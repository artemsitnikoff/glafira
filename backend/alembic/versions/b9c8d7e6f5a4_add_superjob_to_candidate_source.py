"""add_superjob_to_candidate_source

Revision ID: b9c8d7e6f5a4
Revises: a1b2c3d4e5f7
Create Date: 2026-05-30 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9c8d7e6f5a4'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing constraint
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')

    # Create new constraint with 'superjob' added
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'other')"
    )


def downgrade() -> None:
    # Drop extended constraint
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')

    # Restore previous constraint (without 'superjob')
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'other')"
    )