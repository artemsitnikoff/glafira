"""add_potok_to_candidate_source

Добавляет 'potok' в список допустимых источников кандидата (CHECK check_candidate_source).

Revision ID: j1k2l3m4n5o6
Revises: h5i6j7k8l9m0
Create Date: 2026-06-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, None] = 'h5i6j7k8l9m0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'potok', 'other')"
    )


def downgrade() -> None:
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    # Восстанавливаем без 'potok'
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'other')"
    )