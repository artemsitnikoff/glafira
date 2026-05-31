"""employee application_id unique (prevent double-hire race)

Revision ID: f3e4d5c6b7a8
Revises: a1f2b3c4d5e6
Create Date: 2026-05-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f3e4d5c6b7a8'
down_revision: Union[str, None] = 'a1f2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # UNIQUE на employees.application_id — DB-бэкстоп к app-level идемпотентности
    # (SELECT-then-INSERT в create_employee_from_hire) против гонки двойного найма
    # из одной и той же заявки. application_id nullable → несколько NULL допускаются
    # Postgres (NULL'ы различны), но реальный найм всегда проставляет application_id.
    # ВНИМАНИЕ: если в employees уже есть дубли application_id (не должно — найм
    # идемпотентен, application_id уникален на найм), миграция упадёт — разобрать
    # вручную, НЕ удалять записи сотрудников автоматически.
    op.create_unique_constraint(
        "uq_employees_application_id",
        "employees",
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_employees_application_id", "employees", type_="unique")
