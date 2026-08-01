"""add 'test' to events.type CHECK (публичный экзамен-API модуля «Тесты»)

Revision ID: b4c5d6e7f8a9
Revises: a2b3c4d5e6f7
Create Date: 2026-08-01

Фаза 2 модуля «Тесты» (публичный экзамен-флоу). Завершение прохождения теста пишет
Event(type='test', actor_type='system') — чтобы факт был виден в ленте «Все действия»
карточки кандидата (§2.2). Расширяем CHECK events.type значением 'test'.

⚠️ down_revision = a2b3c4d5e6f7 — НАСТОЯЩАЯ голова после фазы 1 (add_tests_module),
пересчитана по графу ревизий (единственная голова). Меняется ТОЛЬКО констрейнт
events.type; данные не трогаются.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Текущий (до этой ревизии) список значений events.type — из c7d8e9f0a1b2 (+'request').
_TYPES_BEFORE = (
    "'qual', 'new', 'score', 'offer', 'move', 'verify', 'comment', 'document', "
    "'interview', 'request'"
)
# После — добавляем 'test'.
_TYPES_AFTER = _TYPES_BEFORE + ", 'test'"


def upgrade() -> None:
    op.drop_constraint("check_event_type", "events", type_="check")
    op.create_check_constraint(
        "check_event_type", "events",
        f"type IN ({_TYPES_AFTER})",
    )


def downgrade() -> None:
    op.drop_constraint("check_event_type", "events", type_="check")
    op.create_check_constraint(
        "check_event_type", "events",
        f"type IN ({_TYPES_BEFORE})",
    )
