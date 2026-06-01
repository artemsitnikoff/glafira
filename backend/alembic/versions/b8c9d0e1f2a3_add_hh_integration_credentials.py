"""Add hh integration credentials

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new credential columns
    op.add_column('hh_integrations', sa.Column('client_id', sa.String(255), nullable=True))
    op.add_column('hh_integrations', sa.Column('client_secret', sa.String, nullable=True))
    op.add_column('hh_integrations', sa.Column('redirect_uri', sa.String(500), nullable=True))

    # Make existing token columns nullable
    op.alter_column('hh_integrations', 'access_token', nullable=True)
    op.alter_column('hh_integrations', 'refresh_token', nullable=True)
    op.alter_column('hh_integrations', 'expires_at', nullable=True)


def downgrade() -> None:
    # Make token columns non-nullable again
    op.alter_column('hh_integrations', 'expires_at', nullable=False)
    op.alter_column('hh_integrations', 'refresh_token', nullable=False)
    op.alter_column('hh_integrations', 'access_token', nullable=False)

    # Drop credential columns
    op.drop_column('hh_integrations', 'redirect_uri')
    op.drop_column('hh_integrations', 'client_secret')
    op.drop_column('hh_integrations', 'client_id')