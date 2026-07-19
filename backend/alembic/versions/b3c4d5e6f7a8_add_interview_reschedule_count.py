"""add interview_links.reschedule_count (отмена/перенос встречи кандидатом)

Revision ID: b3c4d5e6f7a8
Revises: c7d8e9f0a1b2
Create Date: 2026-07-19

Счётчик отмен/переносов встречи кандидатом. Отмена возвращает ссылку в 'active'
(кандидат выбирает время заново существующим /book), поэтому нужен явный счётчик —
иначе лимит переносов не отследить. Максимум переносов enforced в коде
(_MAX_RESCHEDULES в app/api/v1/public_schedule.py), CHECK статусов НЕ трогаем.

server_default='0' → существующие строки получают 0 без отдельного UPDATE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interview_links",
        sa.Column(
            "reschedule_count",
            sa.Integer(),
            server_default=sa.text("'0'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_links", "reschedule_count")
