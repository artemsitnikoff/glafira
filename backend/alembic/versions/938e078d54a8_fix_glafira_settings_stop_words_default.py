"""fix glafira settings stop_words default

Revision ID: 938e078d54a8
Revises: b5057cdcc35c
Create Date: 2026-05-25 17:50:50.612570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '938e078d54a8'
down_revision: Union[str, None] = 'b5057cdcc35c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update stop_words default from [] to {}
    op.alter_column('glafira_settings', 'stop_words',
                   server_default=sa.text("'{}'::jsonb"))

def downgrade() -> None:
    # Revert stop_words default to []
    op.alter_column('glafira_settings', 'stop_words',
                   server_default=sa.text("'[]'::jsonb"))