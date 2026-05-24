"""add test stage_key to vacancy_stages check

Revision ID: 867cd6746ab7
Revises: 824a6e6b9004
Create Date: 2026-05-25 00:48:43.930728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '867cd6746ab7'
down_revision: Union[str, None] = '824a6e6b9004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALLOWED_WITH_TEST = "'response', 'selected', 'recruiter', 'interview', 'test', 'manager', 'offer', 'hired', 'rejected', 'added'"
ALLOWED_WITHOUT_TEST = "'response', 'selected', 'recruiter', 'interview', 'manager', 'offer', 'hired', 'rejected', 'added'"


def upgrade() -> None:
    op.drop_constraint("check_stage_key", "vacancy_stages", type_="check")
    op.create_check_constraint(
        "check_stage_key",
        "vacancy_stages",
        f"stage_key IN ({ALLOWED_WITH_TEST})",
    )


def downgrade() -> None:
    op.drop_constraint("check_stage_key", "vacancy_stages", type_="check")
    op.create_check_constraint(
        "check_stage_key",
        "vacancy_stages",
        f"stage_key IN ({ALLOWED_WITHOUT_TEST})",
    )