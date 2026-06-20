"""add habr_contacts_opened_at to candidates

Revision ID: y7z8a1b2c3d4
Revises: x1y2z3a4b5c6
Create Date: 2026-06-20

Добавляет:
  - candidates.habr_contacts_opened_at (TIMESTAMP WITH TIME ZONE, nullable)
    — момент первого платного открытия контактов Хабра для кандидата.
    NULL = контакты ещё не открыты (кнопка «Открыть контакты» доступна).
    NOT NULL = контакты открыты ранее (идемпотентный эндпоинт не списывает лимит повторно).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'y7z8a1b2c3d4'
down_revision: str = 'x1y2z3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'candidates',
        sa.Column(
            'habr_contacts_opened_at',
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('candidates', 'habr_contacts_opened_at')
