"""add_user_hh_integrations

Персональные hh-токены рекрутёров + дискриминатор kind в OAuth-state.

- user_hh_integrations — персональный OAuth-токен рекрутёра (per-user, зеркалит
  hh_integrations по схеме хранения: access/refresh зашифрованы Fernet, expires_at,
  hh_employer_id + hh_manager_id). UNIQUE(user_id) — один токен на пользователя.
  FK company_id → companies (RESTRICT, мультитенант), user_id → users (CASCADE).
- hh_oauth_states.kind — 'company' | 'personal': callback (complete_oauth) по нему
  маршрутизирует, куда писать токен. Дефолт 'company' → старый company-флоу цел.
  (Колонка user_id в hh_oauth_states УЖЕ существует с миграции a7b8c9d0e1f2 — не трогаем.)

Revision ID: f0a1b2c3d4e5
Revises: b9c0d1e2f3a4
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # user_hh_integrations — один персональный токен на пользователя (UNIQUE user_id)
    op.create_table(
        'user_hh_integrations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False,
                  server_default=sa.text("'00000000-0000-0000-0000-000000000001'")),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('access_token', sa.String(), nullable=True),
        sa.Column('refresh_token', sa.String(), nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('hh_employer_id', sa.String(40), nullable=True),
        sa.Column('hh_manager_id', sa.String(40), nullable=True),
        sa.Column('connected_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_hh_integrations_user_id'),
    )
    op.create_index(
        'ix_user_hh_integrations_company_user',
        'user_hh_integrations',
        ['company_id', 'user_id'],
    )

    # hh_oauth_states.kind — дискриминатор флоу (company/personal). server_default
    # 'company' проставит значение и существующим строкам, и будущим без явного kind.
    op.add_column(
        'hh_oauth_states',
        sa.Column('kind', sa.String(20), nullable=False, server_default=sa.text("'company'")),
    )


def downgrade() -> None:
    op.drop_column('hh_oauth_states', 'kind')
    op.drop_index('ix_user_hh_integrations_company_user', table_name='user_hh_integrations')
    op.drop_table('user_hh_integrations')
