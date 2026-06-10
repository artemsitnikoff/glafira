"""add_candidate_embeddings

Добавляет таблицу candidate_embeddings для семантического поиска кандидатов с pgvector.

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-06-11 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'l3m4n5o6p7q8'
down_revision: Union[str, None] = 'k2l3m4n5o6p7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем расширение pgvector (ПЕРВОЙ строкой upgrade)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Создаём таблицу эмбеддингов
    op.create_table('candidate_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('source_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_id', name='uq_candidate_embedding_candidate_id')
    )

    # Создаём индексы
    op.create_index('idx_candidate_embeddings_company_id', 'candidate_embeddings', ['company_id'])
    # HNSW индекс для векторного поиска по cosine distance
    op.execute('CREATE INDEX idx_candidate_embeddings_embedding_cosine ON candidate_embeddings USING hnsw (embedding vector_cosine_ops)')


def downgrade() -> None:
    # Удаляем таблицу (индексы удалятся автоматически)
    op.drop_table('candidate_embeddings')
    # Расширение не трогаем при downgrade