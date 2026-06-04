"""Add description to funnel stages (vacancy / default / template)

Описание/инструкции этапа воронки для команды (что делать на этапе, суть тестового,
чек-лист интервью). Свободный текст, nullable. Добавляется в три таблицы этапов:
vacancy_stages, company_default_stages, funnel_template_stages. На связь по stage_key,
порядок и аналитику не влияет.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('vacancy_stages', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('company_default_stages', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('funnel_template_stages', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('funnel_template_stages', 'description')
    op.drop_column('company_default_stages', 'description')
    op.drop_column('vacancy_stages', 'description')
