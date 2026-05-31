"""add funnel_templates + funnel_template_stages (настраиваемые пресеты воронок)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-31 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'funnel_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("'00000000-0000-0000-0000-000000000001'")),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'funnel_template_stages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stage_key', sa.String(length=20), nullable=False),
        sa.Column('label', sa.String(length=60), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('is_terminal', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['template_id'], ['funnel_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_funnel_template_stages_template_id', 'funnel_template_stages', ['template_id'])


def downgrade() -> None:
    op.drop_index('ix_funnel_template_stages_template_id', table_name='funnel_template_stages')
    op.drop_table('funnel_template_stages')
    op.drop_table('funnel_templates')
