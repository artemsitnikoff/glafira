"""remove application stage check constraint to allow custom stages

Revision ID: c8d9e0f1a2b3
Revises: b9c8d7e6f5a4
Create Date: 2026-05-30 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, None] = 'b9c8d7e6f5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the check constraint that limits stage values
    op.drop_constraint('check_application_stage', 'applications', type_='check')


def downgrade() -> None:
    # Restore the original check constraint (as it was in initial migration 824a6e6b9004)
    op.create_check_constraint(
        'check_application_stage',
        'applications',
        "stage IN ('response', 'added', 'selected', 'recruiter', 'interview', 'manager', 'offer', 'hired', 'rejected')"
    )