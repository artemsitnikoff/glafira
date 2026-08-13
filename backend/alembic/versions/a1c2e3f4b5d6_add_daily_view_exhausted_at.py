"""add daily_view_exhausted_at to user_hh_integrations

Каскад квоты просмотров резюме hh: когда ЛИЧНАЯ суточная квота рекрутёра (500/сут)
исчерпана, помечаем момент — до конца суток (UTC) его интерактивные просмотры
добираются из ОБЩЕГО компанийного токена (см. hh_service.view_resume_with_cascade).
Nullable, без server_default — существующие строки = квота не исчерпана.

Revision ID: a1c2e3f4b5d6
Revises: f0a1b2c3d4e5
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1c2e3f4b5d6'
down_revision: Union[str, None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_hh_integrations',
        sa.Column('daily_view_exhausted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_hh_integrations', 'daily_view_exhausted_at')
