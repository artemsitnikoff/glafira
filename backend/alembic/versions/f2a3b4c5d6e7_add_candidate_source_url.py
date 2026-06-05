"""add candidate source_url

Ссылка на резюме/профиль кандидата у источника (страница резюме на hh.ru и т.п.).
Заполняется вручную в форме или автоматически при импорте с hh (alternate_url).

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-05 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('source_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('candidates', 'source_url')
