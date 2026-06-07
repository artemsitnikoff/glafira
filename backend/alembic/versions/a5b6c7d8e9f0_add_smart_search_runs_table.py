"""add_smart_search_runs_table

Revision ID: a5b6c7d8e9f0
Revises: d3b8f2a91c4e
Create Date: 2026-06-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create smart_search_runs table
    op.create_table(
        'smart_search_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vacancy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'running'"), nullable=False),
        sa.Column('stage', sa.String(length=20), server_default=sa.text("'search'"), nullable=False),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('found', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('scanned', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('evaluated', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('invited', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('invited_candidates', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['vacancy_id'], ['vacancies.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for performance
    op.create_index('ix_smart_search_runs_company_id', 'smart_search_runs', ['company_id'])
    op.create_index('ix_smart_search_runs_vacancy_id', 'smart_search_runs', ['vacancy_id'])
    op.create_index('ix_smart_search_runs_created_at', 'smart_search_runs', ['created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_smart_search_runs_created_at', 'smart_search_runs')
    op.drop_index('ix_smart_search_runs_vacancy_id', 'smart_search_runs')
    op.drop_index('ix_smart_search_runs_company_id', 'smart_search_runs')

    # Drop table
    op.drop_table('smart_search_runs')