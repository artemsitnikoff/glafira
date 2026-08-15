"""add_talantix_integration

Импорт кандидатов + история комментариев из ATS Talantix (talantix.ru). Добавляет:
- Таблицу talantix_integrations (пара токенов per-company, Fernet-шифрование).
- 'talantix' в CHECK check_candidate_source (источник кандидата).
- 'talantix' в CHECK check_comment_source (комментарии из истории Talantix, read-only).
- Partial unique index дедупа Talantix-комментариев по external_id (company-scoped).
- Колонку candidates.talantix_person_id (идемпотентность повторного импорта) + индекс.
- Колонку candidate_import_jobs.comments_imported (счётчик импортированных комментариев).

down_revision: a1c2e3f4b5d6 (единственная голова на момент создания).
ОДНА голова — downgrade симметричен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3e4f5a6b7c8'
down_revision: Union[str, None] = 'a1c2e3f4b5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Таблица talantix_integrations (Fernet-токены per-company) ---
    op.create_table(
        "talantix_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                  nullable=False,
                  server_default=sa.text("'00000000-0000-0000-0000-000000000001'")),
        sa.Column("access_token", sa.String, nullable=True),
        sa.Column("refresh_token", sa.String, nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("connected_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_talantix_integrations_company_id"),
    )

    # --- candidates.talantix_person_id + индекс ---
    op.add_column(
        "candidates",
        sa.Column("talantix_person_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_candidates_talantix_person_id",
        "candidates",
        ["company_id", "talantix_person_id"],
    )

    # --- candidate_import_jobs.comments_imported ---
    op.add_column(
        "candidate_import_jobs",
        sa.Column("comments_imported", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
    )

    # --- candidate.source: + 'talantix' ---
    op.drop_constraint("check_candidate_source", "candidates", type_="check")
    op.create_check_constraint(
        "check_candidate_source",
        "candidates",
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', "
        "'import', 'manual', 'linkedin', 'potok', 'smart', 'habr', 'talantix', 'other')",
    )

    # --- comment.source: + 'talantix' ---
    op.drop_constraint("check_comment_source", "comments", type_="check")
    op.create_check_constraint(
        "check_comment_source",
        "comments",
        "source IN ('manual', 'hh', 'talantix')",
    )

    # --- Дедуп Talantix-комментариев на уровне БД (company + candidate + external_id) ---
    # candidate_id в ключе: id события истории Talantix может быть уникален только в
    # пределах персоны — без него комментарий одного кандидата молча отбросил бы
    # комментарий другого с тем же event-id (потеря комментариев при миграции базы).
    op.create_index(
        "uq_comment_talantix_external",
        "comments",
        ["company_id", "candidate_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("source = 'talantix'"),
    )


def downgrade() -> None:
    op.drop_index("uq_comment_talantix_external", table_name="comments")

    # Импортированные Talantix-комментарии/кандидаты нарушат откат CHECK — чистим их.
    op.execute("DELETE FROM comments WHERE source = 'talantix'")
    op.drop_constraint("check_comment_source", "comments", type_="check")
    op.create_check_constraint(
        "check_comment_source",
        "comments",
        "source IN ('manual', 'hh')",
    )

    op.execute("DELETE FROM candidates WHERE source = 'talantix'")
    op.drop_constraint("check_candidate_source", "candidates", type_="check")
    op.create_check_constraint(
        "check_candidate_source",
        "candidates",
        "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', "
        "'import', 'manual', 'linkedin', 'potok', 'smart', 'habr', 'other')",
    )

    op.drop_column("candidate_import_jobs", "comments_imported")
    op.drop_index("ix_candidates_talantix_person_id", table_name="candidates")
    op.drop_column("candidates", "talantix_person_id")
    op.drop_table("talantix_integrations")
