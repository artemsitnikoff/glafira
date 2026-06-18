"""phones_digits_no_plus

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-06-18

Меняет формат хранения телефонов на ЦИФРЫ БЕЗ '+': 79991234567
(по требованию заказчика). До этого была ревизия v1w2x3y4z5a6 → E.164 (+79991234567).
Теперь снимаем '+' и до-нормализуем (8→7, 10-значный → 7+номер).

Алгоритм (зеркалит normalize_phone / _normalize_contact):
  digits := regexp_replace(phone, '\\D', '', 'g')
  если digits пусто → ОСТАВИТЬ как есть (мусор без цифр не трогаем)
  len=11 и начинается с '8' → '7' || substr(digits, 2)
  len=10                    → '7' || digits
  иначе                     → digits   (просто цифры, без '+')

Идемпотентна: повторный прогон не меняет уже нормализованные номера.
Пример: '79991234567' → digits len=11 не '8' → else → '79991234567' (без изменений).
        '+79991234567' → digits='79991234567' → else → '79991234567' ('+' снят).

Downgrade: no-op (формат не откатываем).
"""

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'w2x3y4z5a6b7'
down_revision: str = 'v1w2x3y4z5a6'
branch_labels = None
depends_on = None

_NORMALIZE_SQL = """
UPDATE {table}
SET {col} = CASE
    WHEN regexp_replace({col}, '\\D', '', 'g') = '' THEN {col}
    WHEN length(regexp_replace({col}, '\\D', '', 'g')) = 11
         AND left(regexp_replace({col}, '\\D', '', 'g'), 1) = '8'
         THEN '7' || substr(regexp_replace({col}, '\\D', '', 'g'), 2)
    WHEN length(regexp_replace({col}, '\\D', '', 'g')) = 10
         THEN '7' || regexp_replace({col}, '\\D', '', 'g')
    ELSE regexp_replace({col}, '\\D', '', 'g')
END
WHERE {col} IS NOT NULL;
"""


def upgrade() -> None:
    op.execute(_NORMALIZE_SQL.format(table="candidates", col="phone"))
    op.execute(_NORMALIZE_SQL.format(table="users", col="phone"))


def downgrade() -> None:
    # Формат не откатывается (исходный разнобой не восстановим без бэкапа). no-op.
    pass
