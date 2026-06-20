"""add_avito_integration

Добавляет:
- Таблицу avito_integrations (client_credentials per-company, Fernet-шифрование).
- Колонку vacancies.avito_vacancy_id (String(40) nullable, зеркало habr_vacancy_id).
- Колонку applications.avito_application_id (String(64) nullable, + индекс, зеркало habr_response_id).

down_revision: y7z8a1b2c3d4 (текущая голова, add_habr_contacts_opened_at)
ОДНА голова — downgrade симметричен.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'z8a1b2c3d4e5'
down_revision: str = 'y7z8a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Таблица avito_integrations ---
    op.create_table(
        "avito_integrations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                  nullable=False,
                  server_default=sa.text("'00000000-0000-0000-0000-000000000001'")),
        # Credentials (Fernet-шифрование, per-company)
        sa.Column("client_id", sa.String, nullable=True),
        sa.Column("client_secret", sa.String, nullable=True),
        # Кэш client_credentials токена
        sa.Column("access_token", sa.String, nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # Опциональный X-Employee-Of
        sa.Column("avito_user_id", sa.String(64), nullable=True),
        sa.Column("connected_by_user_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        # TimestampMixin
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        # PK + UniqueConstraint
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_avito_integrations_company_id"),
    )

    # --- vacancies.avito_vacancy_id ---
    op.add_column(
        "vacancies",
        sa.Column("avito_vacancy_id", sa.String(40), nullable=True),
    )

    # --- applications.avito_application_id ---
    op.add_column(
        "applications",
        sa.Column("avito_application_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_applications_avito_application_id",
        "applications",
        ["avito_application_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_applications_avito_application_id", table_name="applications")
    op.drop_column("applications", "avito_application_id")
    op.drop_column("vacancies", "avito_vacancy_id")
    op.drop_table("avito_integrations")
