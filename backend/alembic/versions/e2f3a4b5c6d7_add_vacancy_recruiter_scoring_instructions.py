"""Add recruiter_scoring_instructions to vacancies

Рекрутёрские инструкции для AI-скоринга вакансии: свободный текст с
приоритетными требованиями рекрутёра под конкретную вакансию. Подставляется
в системный промпт скоринга (scoring_system.md, плейсхолдер {recruiter_instructions}).
Не влияет на выходной JSON-формат скоринга / модель AiEvaluation.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'vacancies',
        sa.Column('recruiter_scoring_instructions', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('vacancies', 'recruiter_scoring_instructions')
