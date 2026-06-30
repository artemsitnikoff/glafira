"""add auto_move_stage to vacancies (configurable auto-advance target stage)

Revision ID: 0a1b2c3d4e5f
Revises: e4f5a6b7c8d9
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0a1b2c3d4e5f"
down_revision: str = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL → дефолтное поведение (перевод в 'selected'); конкретный stage_key →
    # перевод в выбранный (не защищённый) этап воронки вакансии.
    op.add_column(
        "vacancies",
        sa.Column("auto_move_stage", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vacancies", "auto_move_stage")
