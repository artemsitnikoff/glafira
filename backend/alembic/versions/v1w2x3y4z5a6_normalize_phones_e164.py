"""normalize_phones_e164

Revision ID: v1w2x3y4z5a6
Revises: u2v3w4x5y6z7
Create Date: 2026-06-18

Нормализует candidates.phone и users.phone к формату E.164 (+79991234567).

Алгоритм (зеркалит _clean_phone из candidate_dedup.py):
  digits := regexp_replace(phone, '\\D', '', 'g')
  если digits пусто → ОСТАВИТЬ как есть (нет цифр = мусор, не трогаем)
  len=11 и начинается с '8' → '+7' || substr(digits, 2)
  len=10                    → '+7' || digits
  иначе                     → '+' || digits

Идемпотентность: повторный прогон не меняет уже нормализованные номера.
Пример: '+79991234567' → digits='79991234567' len11 не '8' → else → '+79991234567' ✓

Downgrade: no-op. Формат не откатываем (данные не теряются, просто E.164 останется).
"""

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'v1w2x3y4z5a6'
down_revision: str = 'u2v3w4x5y6z7'
branch_labels = None
depends_on = None

# SQL для нормализации одной колонки (подставить имя таблицы и колонки)
_NORMALIZE_SQL = """
UPDATE {table}
SET {col} = CASE
    WHEN regexp_replace({col}, '\\D', '', 'g') = '' THEN {col}
    WHEN length(regexp_replace({col}, '\\D', '', 'g')) = 11
         AND left(regexp_replace({col}, '\\D', '', 'g'), 1) = '8'
         THEN '+7' || substr(regexp_replace({col}, '\\D', '', 'g'), 2)
    WHEN length(regexp_replace({col}, '\\D', '', 'g')) = 10
         THEN '+7' || regexp_replace({col}, '\\D', '', 'g')
    ELSE '+' || regexp_replace({col}, '\\D', '', 'g')
END
WHERE {col} IS NOT NULL;
"""


def upgrade() -> None:
    op.execute(_NORMALIZE_SQL.format(table="candidates", col="phone"))
    op.execute(_NORMALIZE_SQL.format(table="users", col="phone"))


def downgrade() -> None:
    # Формат E.164 не откатывается — исходный разнобой не восстановим без бэкапа.
    # no-op намеренно.
    pass
