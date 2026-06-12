"""add_salary_from_to_candidates

Добавляет поля salary_from и salary_to в таблицу candidates для создания зарплатной вилки.
Сохраняет salary_expectation для обратной совместимости фильтров.

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-06-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'o6p7q8r9s0t1'
down_revision: Union[str, None] = 'n5o6p7q8r9s0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем новые поля для зарплатной вилки
    op.add_column('candidates', sa.Column('salary_from', sa.Integer(), nullable=True))
    op.add_column('candidates', sa.Column('salary_to', sa.Integer(), nullable=True))

    # Бэкфилл: копируем существующие значения salary_expectation в salary_from и salary_to
    # HR-правило: одиночное значение → обе границы равны
    op.execute("""
        UPDATE candidates
        SET salary_from = salary_expectation, salary_to = salary_expectation
        WHERE salary_expectation IS NOT NULL
    """)


def downgrade() -> None:
    # Удаляем добавленные поля
    op.drop_column('candidates', 'salary_to')
    op.drop_column('candidates', 'salary_from')