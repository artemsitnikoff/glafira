"""add_notes_to_employees

Revision ID: 4ee1fd9eed28
Revises: 81c5bf386c1a
Create Date: 2026-05-25 11:36:57.820750

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ee1fd9eed28'
down_revision: Union[str, None] = '81c5bf386c1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notes JSONB field to employees table
    op.add_column(
        "employees",
        sa.Column(
            "notes",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        )
    )


def downgrade() -> None:
    # Remove notes field from employees table
    op.drop_column("employees", "notes")