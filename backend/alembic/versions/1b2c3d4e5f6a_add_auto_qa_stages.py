"""add auto_qa_stage + auto_qa_target_stage to vacancies (configurable П.2 stages)

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "1b2c3d4e5f6a"
down_revision: str = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL → дефолт: источник 'response', цель 'selected' (обратная совместимость).
    op.add_column("vacancies", sa.Column("auto_qa_stage", sa.String(length=64), nullable=True))
    op.add_column("vacancies", sa.Column("auto_qa_target_stage", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("vacancies", "auto_qa_target_stage")
    op.drop_column("vacancies", "auto_qa_stage")
