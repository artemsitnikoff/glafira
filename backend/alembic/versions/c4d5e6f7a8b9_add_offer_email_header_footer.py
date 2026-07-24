"""add offer_email_header/footer to glafira_settings (письмо-оффер: верх/низ)

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-24

Приветствие (header) и подпись (footer), обрамляющие тело оффера при отправке
кандидату. Обычный текст, БЕЗ плейсхолдеров. NULL/пусто → дефолт из кода
(app/services/offer.py::DEFAULT_OFFER_HEADER/FOOTER) — очистка поля возвращает дефолт.

Обе колонки nullable=True без server_default → существующие строки получают NULL
(= дефолт из кода), отдельный UPDATE не нужен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "glafira_settings",
        sa.Column("offer_email_header", sa.Text(), nullable=True),
    )
    op.add_column(
        "glafira_settings",
        sa.Column("offer_email_footer", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("glafira_settings", "offer_email_footer")
    op.drop_column("glafira_settings", "offer_email_header")
