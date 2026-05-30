"""Коэрция значений парсера резюме к типам/длине колонок candidate.

Регресс: LLM по промпту возвращал зарплату строкой ('180 000 ₽ на руки'), код писал её
в INTEGER-колонку → asyncpg DataError → откат транзакции → 500 на всей загрузке файла.
"""

from app.services.glafira.resume_parse import _to_int, _to_str


def test_to_int_salary_string_with_currency():
    # Главный кейс из прод-краша
    assert _to_int("180 000 ₽ на руки") == 180000


def test_to_int_various_forms():
    assert _to_int("180000") == 180000
    assert _to_int(180000) == 180000
    assert _to_int(180000.0) == 180000
    assert _to_int("от 150 000 до 200 000 руб") == 150000  # берём первое число


def test_to_int_invalid_returns_none():
    assert _to_int(None) is None
    assert _to_int("") is None
    assert _to_int("не указана") is None
    assert _to_int(True) is None          # bool не считаем числом
    assert _to_int("99999999999") is None  # > PG INTEGER max → отбросить


def test_to_str_trims_and_limits():
    assert _to_str("Backend-разработчик", 255) == "Backend-разработчик"
    assert _to_str(None, 255) is None
    assert _to_str("   ", 255) is None
    assert len(_to_str("x" * 300, 120)) == 120  # обрезка под лимит колонки
    assert _to_str(123, 20) == "123"
