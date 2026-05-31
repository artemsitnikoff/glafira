"""add vacancy_id to reject_reasons (причины, привязанные к вакансии)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-31 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL = дефолт компании (шаблон из Настроек). Заполнен = причина, привязанная к вакансии.
    op.add_column(
        'reject_reasons',
        sa.Column('vacancy_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_reject_reasons_vacancy_id',
        'reject_reasons', 'vacancies',
        ['vacancy_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_index(
        'ix_reject_reasons_vacancy_id',
        'reject_reasons', ['vacancy_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_reject_reasons_vacancy_id', table_name='reject_reasons')
    op.drop_constraint('fk_reject_reasons_vacancy_id', 'reject_reasons', type_='foreignkey')
    op.drop_column('reject_reasons', 'vacancy_id')
