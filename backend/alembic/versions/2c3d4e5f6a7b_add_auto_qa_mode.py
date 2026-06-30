"""add auto_qa_mode + auto_qa_fixed_text to vacancies (П.2 questions fork)

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f6a
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2c3d4e5f6a7b"
down_revision: str = "1b2c3d4e5f6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL → дефолт 'weak' (по слабым сторонам резюме) — обратная совместимость.
    op.add_column("vacancies", sa.Column("auto_qa_mode", sa.String(length=16), nullable=True))
    op.add_column("vacancies", sa.Column("auto_qa_fixed_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("vacancies", "auto_qa_fixed_text")
    op.drop_column("vacancies", "auto_qa_mode")
