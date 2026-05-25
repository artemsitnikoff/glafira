"""consent number unique per company instead of global

Revision ID: 3f7b59cfb26a
Revises: 867cd6746ab7
Create Date: 2026-05-25 09:09:04.535707

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f7b59cfb26a'
down_revision: Union[str, None] = '867cd6746ab7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_consents_number", table_name="consents")
    op.create_index("ix_consents_number", "consents", ["number"], unique=False)
    op.create_unique_constraint(
        "uq_consents_company_number",
        "consents",
        ["company_id", "number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_consents_company_number", "consents", type_="unique")
    op.drop_index("ix_consents_number", table_name="consents")
    op.create_index("ix_consents_number", "consents", ["number"], unique=True)