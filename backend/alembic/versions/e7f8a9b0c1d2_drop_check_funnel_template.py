"""drop check_funnel_template (воронки настраиваемые — funnel_template = id кастомного пресета)

Устаревший CHECK разрешал funnel_template только из ('default','mass','technical','sales').
Но форма вакансии шлёт id КАСТОМНОГО пресета воронки (таблица funnel_templates, UUID),
поэтому вставка падала на CheckViolationError → 500 при создании вакансии. Снимаем CHECK.
Этапы при кастомном шаблоне приходят готовыми из формы; get_stages_for_template безопасно
фолбэчит на 'default' для неизвестного значения — вторичных сбоев нет.

Revision ID: e7f8a9b0c1d2
Revises: c3e4f5a6b7c8
Create Date: 2026-09-23
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'c3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF EXISTS — идемпотентно (constraint мог быть уже снят вручную).
    op.execute("ALTER TABLE vacancies DROP CONSTRAINT IF EXISTS check_funnel_template")


def downgrade() -> None:
    # Возврат исходного жёсткого списка (упадёт, если есть вакансии с кастомным
    # funnel_template — это ожидаемо: назад к 4 значениям при живых кастомных нельзя).
    op.create_check_constraint(
        "check_funnel_template",
        "vacancies",
        "funnel_template IN ('default', 'mass', 'technical', 'sales')",
    )
