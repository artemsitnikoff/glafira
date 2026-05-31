"""backfill applications.selected_at = created_at where null («Дата отбора» для старых заявок)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-31 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # У ранее созданных вручную заявок «Дата отбора» (selected_at) пуста — проставляем
    # дату привязки к вакансии (created_at). Дальше новые заявки получают selected_at в коде.
    op.execute("UPDATE applications SET selected_at = created_at WHERE selected_at IS NULL")


def downgrade() -> None:
    # Бэкфилл необратим (не знаем, какие значения были NULL).
    pass
