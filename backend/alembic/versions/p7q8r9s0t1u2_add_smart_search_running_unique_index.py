"""add_smart_search_running_unique_index

Добавляет частичный уникальный индекс для предотвращения двойного запуска
умного поиска по одной вакансии в рамках компании.

Revision ID: p7q8r9s0t1u2
Revises: o6p7q8r9s0t1
Create Date: 2026-06-12 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p7q8r9s0t1u2'
down_revision: str = 'o6p7q8r9s0t1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаём частичный уникальный индекс для предотвращения дублей running-поиска
    # по одной вакансии в рамках компании
    op.create_index(
        'uq_smart_search_run_active',
        'smart_search_runs',
        ['company_id', 'vacancy_id'],
        unique=True,
        postgresql_where=sa.text("status = 'running'")
    )


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index('uq_smart_search_run_active', table_name='smart_search_runs')