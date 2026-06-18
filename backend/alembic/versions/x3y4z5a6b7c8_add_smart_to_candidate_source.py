"""add_smart_to_candidate_source

Добавляет 'smart' в список допустимых источников кандидата (CHECK check_candidate_source).
Источник 'smart' используется для кандидатов, взятых в базу через «Умный подбор hh»
(действие «Забрать к себе» — открыть контакт + создать кандидата без negotiation).

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-06-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'x3y4z5a6b7c8'
down_revision: Union[str, None] = 'w2x3y4z5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'potok', 'smart', 'other')"
    )


def downgrade() -> None:
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    # Восстанавливаем без 'smart'
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'potok', 'other')"
    )
