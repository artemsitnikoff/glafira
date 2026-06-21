"""partial-unique active call_sync_job per company (RACE-01)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Дедуп существующих дублей running (оставляем самый свежий на компанию),
    # иначе создание уникального индекса упадёт.
    op.execute("""
        UPDATE call_sync_jobs SET status='error'
        WHERE status='running' AND id NOT IN (
            SELECT DISTINCT ON (company_id) id FROM call_sync_jobs
            WHERE status='running' ORDER BY company_id, created_at DESC
        )
    """)
    op.create_index(
        "uq_call_sync_job_active",
        "call_sync_jobs",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_call_sync_job_active", table_name="call_sync_jobs")
