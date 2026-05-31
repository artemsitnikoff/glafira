"""add hh integration tables and columns

Revision ID: a7b8c9d0e1f2
Revises: f3e4d5c6b7a8
Create Date: 2026-06-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f3e4d5c6b7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create hh_integrations table
    op.create_table('hh_integrations',
    sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('company_id', postgresql.UUID(as_uuid=True), server_default=sa.text("'00000000-0000-0000-0000-000000000001'"), nullable=False),
    sa.Column('access_token', sa.String(), nullable=False),
    sa.Column('refresh_token', sa.String(), nullable=False),
    sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('hh_employer_id', sa.String(length=40), nullable=True),
    sa.Column('connected_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['connected_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id', name='uq_hh_integrations_company_id')
    )

    # Create hh_oauth_states table
    op.create_table('hh_oauth_states',
    sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('state', sa.String(), nullable=False),
    sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('state')
    )

    # Add hh_vacancy_id column to vacancies
    op.add_column('vacancies', sa.Column('hh_vacancy_id', sa.String(length=40), nullable=True))

    # Add hh_negotiation_id column to applications
    op.add_column('applications', sa.Column('hh_negotiation_id', sa.String(length=40), nullable=True))


def downgrade() -> None:
    # Drop columns
    op.drop_column('applications', 'hh_negotiation_id')
    op.drop_column('vacancies', 'hh_vacancy_id')

    # Drop tables
    op.drop_table('hh_oauth_states')
    op.drop_table('hh_integrations')