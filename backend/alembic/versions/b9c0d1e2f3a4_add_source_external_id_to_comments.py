"""add source/external_id/author_name_ext to comments (импорт комментариев с hh)

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-11

Комментарии-заметки работодателя к резюме на hh импортируются в наш блок
«Комментарии» кандидата с пометкой источника «hh». Для этого таблице comments
нужны:
  - source ('manual' | 'hh') — источник записи; server_default 'manual' покрывает
    ВСЕ существующие строки (это ручные комментарии рекрутёра, автор — наш юзер);
  - external_id — id заметки на hh (дедуп при повторном синке);
  - author_name_ext — имя автора-заметки с hh (у него нет пользователя Глафиры);
  - author_user_id → NULLABLE (у импортированного с hh комментария нашего автора нет;
    у существующих строк author_user_id заполнен, поэтому DROP NOT NULL безопасен).

Дедуп на уровне БД: partial unique index (company_id, external_id) WHERE source='hh'
(company-scoped; ручные комментарии external_id=NULL под условие не попадают).

⚠️ down_revision = a8b9c0d1e2f3 (add_last_login_at_to_users) — РЕАЛЬНАЯ и
ЕДИНСТВЕННАЯ голова, пересчитана по графу ревизий (один корень 824a6e6b9004,
81 ревизия, без висячих down_revision, без дублей revision id).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "comments",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "comments",
        sa.Column("external_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "comments",
        sa.Column("author_name_ext", sa.Text(), nullable=True),
    )
    # У hh-комментария нет автора-пользователя Глафиры → колонка становится nullable.
    op.alter_column(
        "comments",
        "author_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_check_constraint(
        "check_comment_source",
        "comments",
        "source IN ('manual', 'hh')",
    )
    # Дедуп hh-комментариев (повторный синк не плодит дубли) на уровне БД, company-scoped.
    op.create_index(
        "uq_comment_hh_external",
        "comments",
        ["company_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("source = 'hh'"),
    )


def downgrade() -> None:
    op.drop_index("uq_comment_hh_external", table_name="comments")
    op.drop_constraint("check_comment_source", "comments", type_="check")
    # Импортированные с hh комментарии (author_user_id IS NULL) мешают вернуть NOT NULL —
    # удаляем их перед откатом (это записи, созданные ровно этой фичей).
    op.execute("DELETE FROM comments WHERE source = 'hh'")
    op.alter_column(
        "comments",
        "author_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("comments", "author_name_ext")
    op.drop_column("comments", "external_id")
    op.drop_column("comments", "source")
