"""Add public link + question snapshot to pulse_surveys

Публичная ссылка на опрос: респондент (сотрудник) проходит опрос по секретной
ссылке без авторизации. Добавляем:
- public_token  — высокоэнтропийный секрет (в URL-хеше у фронта), по нему публичный
  эндпоинт находит опрос. UNIQUE, nullable (старые опросы без токена).
- questions     — снапшот вопросов на момент запуска (JSONB), чтобы публичная страница
  рендерила именно те вопросы, что были отправлены, и правки шаблона их не меняли.

На связь этап↔кандидат, аналитику и существующие данные не влияет.

Revision ID: c0d1e2f3a4b5
Revises: f3a4b5c6d7e8
Create Date: 2026-06-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'c0d1e2f3a4b5'
# Цепляемся от РЕАЛЬНОЙ головы f3a4b5c6d7e8 (add_stage_description).
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'pulse_surveys',
        sa.Column('public_token', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'pulse_surveys',
        sa.Column(
            'questions', JSONB(), nullable=False,
            server_default=sa.text("'[]'::jsonb")
        )
    )
    op.create_index(
        'uq_pulse_surveys_public_token', 'pulse_surveys', ['public_token'], unique=True
    )


def downgrade() -> None:
    op.drop_index('uq_pulse_surveys_public_token', table_name='pulse_surveys')
    op.drop_column('pulse_surveys', 'questions')
    op.drop_column('pulse_surveys', 'public_token')
