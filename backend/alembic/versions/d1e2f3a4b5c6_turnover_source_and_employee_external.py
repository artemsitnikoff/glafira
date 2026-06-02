"""Add turnover_source to glafira_settings + external source fields to employees

Фича 2: glafira_settings.turnover_source ('none' | 'bitrix24') — источник данных о текучке.
Фича 3a: employees.candidate_id → nullable; + external_source/external_id + unique-констрейнт
         (для идемпотентного импорта сотрудников из внешних систем, напр. Битрикс24).

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-06-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Фича 2: источник данных о текучке ---
    op.add_column(
        'glafira_settings',
        sa.Column('turnover_source', sa.String(20), nullable=False, server_default='none'),
    )
    op.create_check_constraint(
        'check_glafira_turnover_source',
        'glafira_settings',
        "turnover_source IN ('none', 'bitrix24')",
    )

    # --- Фича 3a: внешний источник сотрудников ---
    # candidate_id больше не NOT NULL: Б24-сотрудники без ATS-кандидата.
    op.alter_column(
        'employees',
        'candidate_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        'employees',
        sa.Column('external_source', sa.String(20), nullable=True),
    )
    op.add_column(
        'employees',
        sa.Column('external_id', sa.String(64), nullable=True),
    )
    # Идемпотентность импорта: один внешний юзер = один Employee.
    # В Postgres NULL не конфликтует в UNIQUE — ATS-наймы (external_*=NULL) дубли не образуют.
    op.create_unique_constraint(
        'uq_employee_external',
        'employees',
        ['company_id', 'external_source', 'external_id'],
    )


def downgrade() -> None:
    # --- Фича 3a откат ---
    op.drop_constraint('uq_employee_external', 'employees', type_='unique')
    op.drop_column('employees', 'external_id')
    op.drop_column('employees', 'external_source')
    # ⚠️ Возврат candidate_id → NOT NULL УПАДЁТ, если в таблице есть импортированные
    # Б24-строки (candidate_id IS NULL). Это ожидаемо: перед откатом нужно удалить
    # импортированных сотрудников (external_source IS NOT NULL) вручную.
    op.alter_column(
        'employees',
        'candidate_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # --- Фича 2 откат ---
    op.drop_constraint('check_glafira_turnover_source', 'glafira_settings', type_='check')
    op.drop_column('glafira_settings', 'turnover_source')
