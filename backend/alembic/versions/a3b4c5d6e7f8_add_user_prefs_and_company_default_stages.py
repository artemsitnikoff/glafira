"""add user prefs and company default stages

Revision ID: a3b4c5d6e7f8
Revises: c8d9e0f1a2b3
Create Date: 2026-05-31 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add language and date_format columns to users table
    op.add_column('users', sa.Column('language', sa.String(length=10), nullable=False, server_default="'ru'"))
    op.add_column('users', sa.Column('date_format', sa.String(length=20), nullable=False, server_default="'DD.MM.YYYY'"))

    # Create company_default_stages table
    op.create_table('company_default_stages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("'00000000-0000-0000-0000-000000000001'")),
        sa.Column('stage_key', sa.String(length=20), nullable=False),
        sa.Column('label', sa.String(length=60), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('is_terminal', sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop company_default_stages table
    op.drop_table('company_default_stages')

    # Remove language and date_format columns from users table
    op.drop_column('users', 'date_format')
    op.drop_column('users', 'language')