"""add candidate_import_jobs table

Revision ID: h5i6j7k8l9m0
Revises: g0h1j2k3l4m5
Create Date: 2026-06-10 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP


# revision identifiers, used by Alembic.
revision: str = 'h5i6j7k8l9m0'
down_revision: Union[str, None] = 'g0h1j2k3l4m5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create candidate_import_jobs table
    op.create_table('candidate_import_jobs',
        sa.Column('id', UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column('company_id', UUID(as_uuid=True), nullable=False, server_default=sa.text("'00000000-0000-0000-0000-000000000001'")),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'running'")),
        sa.Column('total', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('processed', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('created', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('updated', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('skipped', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('errors', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('finished_at', TIMESTAMP(timezone=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT')
    )

    # Create index on company_id
    op.create_index('ix_candidate_import_jobs_company_id', 'candidate_import_jobs', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_candidate_import_jobs_company_id', table_name='candidate_import_jobs')
    op.drop_table('candidate_import_jobs')