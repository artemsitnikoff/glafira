"""add offer_sent_at to applications (per-application таймстамп отправки оффера)

Revision ID: e6f7a8b9c0d1
Revises: c4d5e6f7a8b9
Create Date: 2026-07-24

Момент последней успешной отправки письма-оффера по заявке. Проставляется в
send_offer СТРОГО после send_email (сбой SMTP → NULL, «отправлено» не появляется).
Фронт показывает бейдж «Отправлен ✓ дата» в строке кандидата воронки.

nullable=True без server_default → существующие заявки получают NULL
(= «оффер не отправляли»), отдельный UPDATE не нужен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("offer_sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications", "offer_sent_at")
