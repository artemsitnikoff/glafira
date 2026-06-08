"""fix smart_search_runs created_at/updated_at: add server_default now() + tz

Миграция a5b6c7d8e9f0 создала created_at/updated_at как DateTime() БЕЗ server_default
(и без timezone), хотя TimestampMixin объявляет TIMESTAMP(timezone=True)+server_default=now().
На проде INSERT падал NotNullViolation (ORM не шлёт created_at, дефолта в БД нет).
Тесты не поймали — conftest строит схему через create_all из моделей, не из миграции.

Revision ID: f9a8b7c6d5e4
Revises: cc4b24ebbfee
Create Date: 2026-06-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9a8b7c6d5e4'
down_revision: Union[str, None] = 'cc4b24ebbfee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('smart_search_runs', 'created_at',
                    type_=sa.TIMESTAMP(timezone=True),
                    server_default=sa.text('now()'),
                    existing_nullable=False)
    op.alter_column('smart_search_runs', 'updated_at',
                    type_=sa.TIMESTAMP(timezone=True),
                    server_default=sa.text('now()'),
                    existing_nullable=False)


def downgrade() -> None:
    op.alter_column('smart_search_runs', 'updated_at',
                    type_=sa.DateTime(),
                    server_default=None,
                    existing_nullable=False)
    op.alter_column('smart_search_runs', 'created_at',
                    type_=sa.DateTime(),
                    server_default=None,
                    existing_nullable=False)
