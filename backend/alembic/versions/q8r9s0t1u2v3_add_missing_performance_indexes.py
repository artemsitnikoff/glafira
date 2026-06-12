"""add_missing_performance_indexes

Добавляет недостающие индексы для оптимизации производительности горячих путей:
- Лента событий (поллится каждые 15сек)
- Дедупликация кандидатов (каждый создание + импорт)
- Фильтры воронки и поиска по базе
- FK без индексов для batch-подгрузки

Индексы создаются идемпотентно. ВНИМАНИЕ: на больших таблицах может блокировать
запись во время создания. Текущие размеры таблиц приемлемы для обычного CREATE INDEX.

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-06-12 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q8r9s0t1u2v3'
down_revision: str = 'p7q8r9s0t1u2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаём расширение pg_trgm для trigram индексов (идемпотентно)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # events: лента событий поллится каждые 15 сек
    op.execute("CREATE INDEX IF NOT EXISTS ix_events_company_created ON events (company_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_events_candidate_created ON events (candidate_id, created_at)")

    # audit_log: пишется на каждое действие
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_log_company_created ON audit_log (company_id, created_at)")

    # consents: коррелированный EXISTS has_pdn в списках пула/воронки
    op.execute("CREATE INDEX IF NOT EXISTS ix_consents_candidate_status ON consents (candidate_id, status)")

    # candidates: дедупликация на каждом create/импорте
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_company_phone ON candidates (company_id, phone)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_company_lower_email ON candidates (company_id, lower(email))")

    # candidates: trigram индексы для leading-wildcard ILIKE в base_search
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_last_position_trgm ON candidates USING gin (last_position gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_city_trgm ON candidates USING gin (city gin_trgm_ops)")

    # FK без индексов: batch-подгрузка связанных данных
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_skills_candidate_id ON candidate_skills (candidate_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_experience_candidate_id ON candidate_experience (candidate_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_education_candidate_id ON candidate_education (candidate_id)")

    # candidate_tags: FK + EXISTS по тегам в фильтрах
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_tags_candidate_id ON candidate_tags (candidate_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidate_tags_tag_id ON candidate_tags (tag_id)")

    # vacancies: список/сайдбар/JOIN
    op.execute("CREATE INDEX IF NOT EXISTS ix_vacancies_company_id ON vacancies (company_id)")


def downgrade() -> None:
    # Удаляем индексы в обратном порядке
    op.execute("DROP INDEX IF EXISTS ix_vacancies_company_id")
    op.execute("DROP INDEX IF EXISTS ix_candidate_tags_tag_id")
    op.execute("DROP INDEX IF EXISTS ix_candidate_tags_candidate_id")
    op.execute("DROP INDEX IF EXISTS ix_candidate_education_candidate_id")
    op.execute("DROP INDEX IF EXISTS ix_candidate_experience_candidate_id")
    op.execute("DROP INDEX IF EXISTS ix_candidate_skills_candidate_id")
    op.execute("DROP INDEX IF EXISTS ix_candidates_city_trgm")
    op.execute("DROP INDEX IF EXISTS ix_candidates_last_position_trgm")
    op.execute("DROP INDEX IF EXISTS ix_candidates_company_lower_email")
    op.execute("DROP INDEX IF EXISTS ix_candidates_company_phone")
    op.execute("DROP INDEX IF EXISTS ix_consents_candidate_status")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_company_created")
    op.execute("DROP INDEX IF EXISTS ix_events_candidate_created")
    op.execute("DROP INDEX IF EXISTS ix_events_company_created")

    # Примечание: pg_trgm расширение НЕ удаляем, может использоваться другими индексами