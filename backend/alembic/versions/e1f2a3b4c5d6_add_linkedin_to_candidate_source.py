"""add_linkedin_to_candidate_source

Добавляет 'linkedin' в список допустимых источников кандидата (CHECK check_candidate_source).

Revision ID: e1f2a3b4c5d6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
# Реальная голова на момент создания — c0d1e2f3a4b5 (pulse public link).
down_revision: Union[str, None] = 'c0d1e2f3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'other')"
    )


def downgrade() -> None:
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    # Восстанавливаем без 'linkedin'
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'other')"
    )
