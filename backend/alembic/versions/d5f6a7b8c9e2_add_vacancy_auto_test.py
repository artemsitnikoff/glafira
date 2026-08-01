"""add vacancies.auto_test / auto_test_id / auto_test_stage (автоназначение теста)

Revision ID: d5f6a7b8c9e2
Revises: b4c5d6e7f8a9
Create Date: 2026-08-01

Фаза 2Б модуля «Тесты» (назначение тестов + автоматизация воронки). Опциональная
авто-отправка ссылки на тест при переходе заявки на указанный этап вакансии
(дефолт OFF, opt-in) — три новые колонки в `vacancies`, синхронные с моделью
Vacancy (auto_test / auto_test_id → tests.id ON DELETE SET NULL / auto_test_stage).

⚠️ down_revision = b4c5d6e7f8a9 — РЕАЛЬНАЯ голова (add_test_event_type), пересчитана
по графу ревизий (единственная голова). Только add/drop колонок — данные не трогаются.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d5f6a7b8c9e2"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vacancies",
        sa.Column(
            "auto_test",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "vacancies",
        sa.Column(
            "auto_test_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "vacancies",
        sa.Column("auto_test_stage", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vacancies", "auto_test_stage")
    op.drop_column("vacancies", "auto_test_id")
    op.drop_column("vacancies", "auto_test")
