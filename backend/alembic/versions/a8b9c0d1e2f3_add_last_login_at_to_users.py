"""add last_login_at to users (реальный трекинг последнего входа)

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-10

Колонка «Последний вход» в списке пользователей раньше показывала created_at
(дата создания, не менялась). Заводим реальный last_login_at, который сервис
логина и эндпоинт refresh обновляют на КАЖДОМ успешном входе/обновлении токена.

⚠️ down_revision = f7a8b9c0d1e2 (add_message_reads) — РЕАЛЬНАЯ и ЕДИНСТВЕННАЯ
голова, пересчитана по графу ревизий (один корень 824a6e6b9004, без висячих
down_revision). Колонка nullable БЕЗ бэкфилла: у существующих пользователей
остаётся NULL до первого входа после деплоя (честно «не входил», не фейк-дата).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
