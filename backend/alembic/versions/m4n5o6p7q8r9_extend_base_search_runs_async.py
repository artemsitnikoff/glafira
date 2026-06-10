"""extend_base_search_runs_async

Расширяет base_search_runs для асинхронного поиска: status, stage, to_evaluate, evaluated, results, criteria, query_echo, vacancy_title, error, finished_at

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-06-11 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'm4n5o6p7q8r9'
down_revision: Union[str, None] = 'l3m4n5o6p7q8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем новые колонки с server_default для совместимости со старыми записями
    op.add_column('base_search_runs', sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'running'")))
    op.add_column('base_search_runs', sa.Column('stage', sa.String(20), nullable=True))
    op.add_column('base_search_runs', sa.Column('to_evaluate', sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column('base_search_runs', sa.Column('evaluated', sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column('base_search_runs', sa.Column('results', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column('base_search_runs', sa.Column('criteria', postgresql.JSONB(), nullable=True))
    op.add_column('base_search_runs', sa.Column('query_echo', sa.Text(), nullable=True))
    op.add_column('base_search_runs', sa.Column('vacancy_title', sa.Text(), nullable=True))
    op.add_column('base_search_runs', sa.Column('error', sa.Text(), nullable=True))
    op.add_column('base_search_runs', sa.Column('finished_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Удаляем добавленные колонки
    op.drop_column('base_search_runs', 'finished_at')
    op.drop_column('base_search_runs', 'error')
    op.drop_column('base_search_runs', 'vacancy_title')
    op.drop_column('base_search_runs', 'query_echo')
    op.drop_column('base_search_runs', 'criteria')
    op.drop_column('base_search_runs', 'results')
    op.drop_column('base_search_runs', 'evaluated')
    op.drop_column('base_search_runs', 'to_evaluate')
    op.drop_column('base_search_runs', 'stage')
    op.drop_column('base_search_runs', 'status')