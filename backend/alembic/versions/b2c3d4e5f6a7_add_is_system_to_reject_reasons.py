"""add is_system to reject_reasons (защищённые причины отказа)

Revision ID: b2c3d4e5f6a7
Revises: a3b4c5d6e7f8
Create Date: 2026-05-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Системная причина отказа — нельзя удалить (гарантия непустоты: ≥1 на каждую сторону).
    op.add_column(
        'reject_reasons',
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Помечаем канонические причины системными для уже посеянных компаний
    # (по 1 на сторону). Сопоставление по label — мы знаем точные сид-значения.
    op.execute(
        "UPDATE reject_reasons SET is_system = true "
        "WHERE side = 'company' AND label = 'Несоответствие опыта'"
    )
    op.execute(
        "UPDATE reject_reasons SET is_system = true "
        "WHERE side = 'candidate' AND label = 'Не вышел на связь'"
    )


def downgrade() -> None:
    op.drop_column('reject_reasons', 'is_system')
