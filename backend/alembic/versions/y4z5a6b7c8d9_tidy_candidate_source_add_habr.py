"""tidy_candidate_source_add_habr

Добавляет 'habr' (Хабр Карьера) в CHECK check_candidate_source.
Удаляет мёртвую колонку applications.source (никогда не записывалась и не читалась).

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-06-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'y4z5a6b7c8d9'
down_revision: Union[str, None] = 'x3y4z5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Расширяем CHECK check_candidate_source — добавляем 'habr' перед 'other'
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'potok', 'smart', 'habr', 'other')"
    )

    # 2. Удаляем мёртвую колонку applications.source (всегда NULL, нет ни писателей, ни читателей)
    op.drop_column('applications', 'source')


def downgrade() -> None:
    # 2. Возвращаем колонку applications.source (nullable — данных не было)
    op.add_column('applications', sa.Column('source', sa.String(length=40), nullable=True))

    # 1. Возвращаем CHECK без 'habr' (список как в x3y4z5a6b7c8)
    op.drop_constraint('check_candidate_source', 'candidates', type_='check')
    op.create_check_constraint(
        'check_candidate_source',
        'candidates',
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'potok', 'smart', 'other')"
    )
