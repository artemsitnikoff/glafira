"""unique_idx_applications_ai_evaluations

Revision ID: a9b0c1d2e3f4
Revises: z8a1b2c3d4e5
Create Date: 2026-06-21 00:00:00.000000

FIX #2 — UNIQUE-индексы против дублей Application/AiEvaluation под гонкой.

Этапы:
1. Дедуп существующих дублей (иначе CREATE UNIQUE INDEX упадёт):
   - applications: для каждого из hh_negotiation_id / habr_response_id / avito_application_id
     оставляем запись с минимальным created_at, остальные удаляем через каскад FK.
   - ai_evaluations: для пары (candidate_id, application_id) оставляем
     запись с МАКСИМАЛЬНЫМ created_at (последняя оценка), удаляем старые.
2. Создаём частичные UNIQUE-индексы:
   - applications(company_id, hh_negotiation_id) WHERE hh_negotiation_id IS NOT NULL
   - applications(company_id, habr_response_id)  WHERE habr_response_id IS NOT NULL
   - applications(company_id, avito_application_id) WHERE avito_application_id IS NOT NULL
   - ai_evaluations(candidate_id, application_id) WHERE application_id IS NOT NULL

Downgrade: DROP INDEX (дедуп НЕ откатываем — удаление настоящих дублей норма).
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, None] = 'z8a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # -------------------------------------------------------------------------
    # 1. Дедуп applications по hh_negotiation_id
    #    Оставляем min(ctid) среди дублей, удаляем остальные через каскад.
    #    stage_history FK → applications(id) ON DELETE CASCADE, поэтому достаточно
    #    удалить саму Application; дочерние stage_history уйдут каскадом.
    #    Дублей обычно нет (только при гонке), но дедуп идемпотентен.
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        DELETE FROM applications
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id, hh_negotiation_id
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM applications
                WHERE hh_negotiation_id IS NOT NULL
            ) sub
            WHERE rn > 1
        )
    """))

    # -------------------------------------------------------------------------
    # 2. Дедуп applications по habr_response_id
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        DELETE FROM applications
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id, habr_response_id
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM applications
                WHERE habr_response_id IS NOT NULL
            ) sub
            WHERE rn > 1
        )
    """))

    # -------------------------------------------------------------------------
    # 3. Дедуп applications по avito_application_id
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        DELETE FROM applications
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id, avito_application_id
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM applications
                WHERE avito_application_id IS NOT NULL
            ) sub
            WHERE rn > 1
        )
    """))

    # -------------------------------------------------------------------------
    # 4. Дедуп ai_evaluations по (candidate_id, application_id)
    #    Оставляем максимальный created_at (последнюю оценку).
    #    application_id может быть NULL — NULL-дубли НЕ трогаем (они не нарушают
    #    частичный unique WHERE application_id IS NOT NULL).
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        DELETE FROM ai_evaluations
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY candidate_id, application_id
                           ORDER BY created_at DESC, id DESC
                       ) AS rn
                FROM ai_evaluations
                WHERE application_id IS NOT NULL
            ) sub
            WHERE rn > 1
        )
    """))

    # -------------------------------------------------------------------------
    # 5. Создаём частичные UNIQUE-индексы
    # -------------------------------------------------------------------------
    op.create_index(
        'uix_applications_hh_negotiation_id',
        'applications',
        ['company_id', 'hh_negotiation_id'],
        unique=True,
        postgresql_where=sa.text('hh_negotiation_id IS NOT NULL'),
    )

    op.create_index(
        'uix_applications_habr_response_id',
        'applications',
        ['company_id', 'habr_response_id'],
        unique=True,
        postgresql_where=sa.text('habr_response_id IS NOT NULL'),
    )

    op.create_index(
        'uix_applications_avito_application_id',
        'applications',
        ['company_id', 'avito_application_id'],
        unique=True,
        postgresql_where=sa.text('avito_application_id IS NOT NULL'),
    )

    op.create_index(
        'uix_ai_evaluations_candidate_application',
        'ai_evaluations',
        ['candidate_id', 'application_id'],
        unique=True,
        postgresql_where=sa.text('application_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uix_ai_evaluations_candidate_application', table_name='ai_evaluations')
    op.drop_index('uix_applications_avito_application_id', table_name='applications')
    op.drop_index('uix_applications_habr_response_id', table_name='applications')
    op.drop_index('uix_applications_hh_negotiation_id', table_name='applications')
    # Дедуп НЕ откатываем — удаление настоящих дублей нормально и безвозвратно.
