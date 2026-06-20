"""add_habr_integration

Создаёт таблицы для OAuth-интеграции Хабр Карьера:
- habr_integrations — per-company токены (access/refresh, Fernet)
- habr_oauth_states — временные state OAuth-флоу (TTL 10 минут)

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-06-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z5a6b7c8d9e0'
down_revision: Union[str, None] = 'y4z5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # habr_integrations — одна запись per-company (UniqueConstraint company_id)
    op.create_table(
        'habr_integrations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False, server_default=sa.text("'00000000-0000-0000-0000-000000000001'")),
        sa.Column('access_token', sa.String(), nullable=True),
        sa.Column('refresh_token', sa.String(), nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('habr_login', sa.String(255), nullable=True),
        sa.Column('connected_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', name='uq_habr_integrations_company_id'),
    )
    op.create_index('ix_habr_integrations_company_id', 'habr_integrations', ['company_id'])

    # habr_oauth_states — временные state для OAuth-флоу
    op.create_table(
        'habr_oauth_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('state', name='uq_habr_oauth_states_state'),
    )
    op.create_index('ix_habr_oauth_states_state', 'habr_oauth_states', ['state'])
    op.create_index('ix_habr_oauth_states_expires_at', 'habr_oauth_states', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_habr_oauth_states_expires_at', table_name='habr_oauth_states')
    op.drop_index('ix_habr_oauth_states_state', table_name='habr_oauth_states')
    op.drop_table('habr_oauth_states')

    op.drop_index('ix_habr_integrations_company_id', table_name='habr_integrations')
    op.drop_table('habr_integrations')
