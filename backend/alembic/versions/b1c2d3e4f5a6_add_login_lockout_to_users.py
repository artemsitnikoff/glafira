"""add_login_lockout_to_users

Добавляет защиту от брутфорса пароля через БД-счётчик неудачных попыток:
- failed_login_attempts INTEGER NOT NULL DEFAULT 0
- locked_until TIMESTAMP WITH TIME ZONE NULL

down_revision: a9b0c1d2e3f4 (unique_idx_applications_ai_evaluations — единственная голова)
ОДНА голова — downgrade симметричен.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: str = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'failed_login_attempts',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'locked_until',
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        )
    )


def downgrade() -> None:
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
