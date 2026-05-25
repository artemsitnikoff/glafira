"""add phone to users

Revision ID: b5057cdcc35c
Revises: 4ee1fd9eed28
Create Date: 2026-05-25 17:33:02.388301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5057cdcc35c'
down_revision: Union[str, None] = '4ee1fd9eed28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add phone column to users table
    op.add_column("users", sa.Column("phone", sa.String(20), nullable=True))


def downgrade() -> None:
    # Remove phone column from users table
    op.drop_column("users", "phone")