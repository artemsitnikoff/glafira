"""add consent online signing columns (token/expires_at/signed_ip/signed_by/consent_text)

Онлайн-подписание согласия ПдН кандидатом (v1.9.0). Публичная ссылка /consent/{token},
снимок подписанного текста, IP и «кто подписал» — доказательства согласия по 152-ФЗ.

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2 (единственная голова на момент создания)
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('consents', sa.Column('token', sa.String(length=64), nullable=True))
    op.add_column('consents', sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('consents', sa.Column('signed_ip', sa.String(length=64), nullable=True))
    op.add_column('consents', sa.Column('signed_by', sa.String(length=20), nullable=True))
    op.add_column('consents', sa.Column('consent_text', sa.Text(), nullable=True))
    # Partial unique index: токен уникален глобально, но записи без токена (NULL) не
    # конфликтуют между собой (offline-подтверждение «ПдН подписан» токена не имеет).
    op.create_index(
        'uq_consents_token',
        'consents',
        ['token'],
        unique=True,
        postgresql_where=sa.text('token IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_consents_token', table_name='consents')
    op.drop_column('consents', 'consent_text')
    op.drop_column('consents', 'signed_by')
    op.drop_column('consents', 'signed_ip')
    op.drop_column('consents', 'expires_at')
    op.drop_column('consents', 'token')
