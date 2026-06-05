"""add vacancy automation fields

Revision ID: 5aec60adf427
Revises: f2a3b4c5d6e7
Create Date: 2026-06-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5aec60adf427'
# Цепляемся от РЕАЛЬНОЙ головы f2a3b4c5d6e7 (агент ошибочно зацепил d3b8f2a91c4e → две головы).
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add automation fields to vacancies table
    op.add_column('vacancies', sa.Column('auto_move', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('vacancies', sa.Column('auto_move_threshold', sa.Integer(), nullable=False, server_default='80'))
    op.add_column('vacancies', sa.Column('auto_qa', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('vacancies', sa.Column('auto_reject', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('vacancies', sa.Column('rejection_text', sa.Text(), nullable=True))

    # Add default rejection text to glafira_settings table
    op.add_column('glafira_settings', sa.Column('default_rejection_text', sa.Text(), nullable=True))

    # Add automation tracking fields to applications table
    op.add_column('applications', sa.Column('auto_qa_asked_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('applications', sa.Column('auto_reject_suggested_at', sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove automation tracking fields from applications table
    op.drop_column('applications', 'auto_reject_suggested_at')
    op.drop_column('applications', 'auto_qa_asked_at')

    # Remove default rejection text from glafira_settings table
    op.drop_column('glafira_settings', 'default_rejection_text')

    # Remove automation fields from vacancies table
    op.drop_column('vacancies', 'rejection_text')
    op.drop_column('vacancies', 'auto_reject')
    op.drop_column('vacancies', 'auto_qa')
    op.drop_column('vacancies', 'auto_move_threshold')
    op.drop_column('vacancies', 'auto_move')