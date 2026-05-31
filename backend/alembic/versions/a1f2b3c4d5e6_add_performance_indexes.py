"""add performance indexes for applications, stage_history, and candidates

Revision ID: a1f2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-05-31 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1f2b3c4d5e6'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Applications table indexes
    op.create_index('ix_applications_company_id', 'applications', ['company_id'])
    op.create_index('ix_applications_vacancy_id', 'applications', ['vacancy_id'])
    op.create_index('ix_applications_candidate_id', 'applications', ['candidate_id'])
    op.create_index('ix_applications_stage', 'applications', ['stage'])
    op.create_index('ix_applications_created_at', 'applications', ['created_at'])

    # Stage history table indexes
    op.create_index('ix_stage_history_application_id', 'stage_history', ['application_id'])
    op.create_index('ix_stage_history_created_at', 'stage_history', ['created_at'])

    # Candidates table indexes
    op.create_index('ix_candidates_company_id', 'candidates', ['company_id'])
    op.create_index('ix_candidates_created_at', 'candidates', ['created_at'])
    op.create_index('ix_candidates_deleted_at', 'candidates', ['deleted_at'])


def downgrade() -> None:
    # Drop candidates indexes
    op.drop_index('ix_candidates_deleted_at', 'candidates')
    op.drop_index('ix_candidates_created_at', 'candidates')
    op.drop_index('ix_candidates_company_id', 'candidates')

    # Drop stage history indexes
    op.drop_index('ix_stage_history_created_at', 'stage_history')
    op.drop_index('ix_stage_history_application_id', 'stage_history')

    # Drop applications indexes
    op.drop_index('ix_applications_created_at', 'applications')
    op.drop_index('ix_applications_stage', 'applications')
    op.drop_index('ix_applications_candidate_id', 'applications')
    op.drop_index('ix_applications_vacancy_id', 'applications')
    op.drop_index('ix_applications_company_id', 'applications')