"""add habr_vacancy_id to vacancies and habr_response_id to applications

Revision ID: x1y2z3a4b5c6
Revises: z5a6b7c8d9e0
Create Date: 2026-06-20

Добавляет:
  - vacancies.habr_vacancy_id  (String(64), nullable) — связь вакансии Глафиры ↔ вакансии Хабра
  - applications.habr_response_id (String(64), nullable) — дедуп откликов Хабра (зеркало hh_negotiation_id)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'x1y2z3a4b5c6'
down_revision: str = 'z5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'vacancies',
        sa.Column('habr_vacancy_id', sa.String(64), nullable=True),
    )
    op.add_column(
        'applications',
        sa.Column('habr_response_id', sa.String(64), nullable=True),
    )
    # Индекс для быстрого дедупа (аналогично hh_negotiation_id)
    op.create_index(
        'ix_applications_habr_response_id',
        'applications',
        ['habr_response_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_applications_habr_response_id', table_name='applications')
    op.drop_column('applications', 'habr_response_id')
    op.drop_column('vacancies', 'habr_vacancy_id')
