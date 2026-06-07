"""add vacancy auto_reject_message flag

Revision ID: b7c8d9e0f1a2
Revises: 5aec60adf427
Create Date: 2026-06-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
# Цепляемся от РЕАЛЬНОЙ головы 5aec60adf427 (см. [[alembic-find-true-head]]).
down_revision: Union[str, None] = '5aec60adf427'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Флаг: слать ли вежливое сообщение кандидату при переводе в отказ (вежливость на hh).
    # Дефолт false — существующие вакансии не шлют авто-сообщение, пока флаг не включат.
    op.add_column('vacancies', sa.Column('auto_reject_message', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('vacancies', 'auto_reject_message')
