"""add work_format to vacancies

Формат занятости вакансии: 'office' | 'remote' | 'hybrid' (nullable, v1.10.0).
Влияет на AI-скоринг (веса по локации кандидата / готовности к переезду).
⚠️ БЕЗ CheckConstraint на значения — валидация в Pydantic (Literal → 422). Жёсткий CHECK
на enum-поле уже ронял создание вакансии 500 (урок check_funnel_template).

Revision ID: a2c4e6f8b0d1
Revises: f1a2b3c4d5e6
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2c4e6f8b0d1'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('vacancies', sa.Column('work_format', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('vacancies', 'work_format')
