"""Чистые форматтеры данных кандидата (возраст, ФИО).

Вынесены отдельным модулем БЕЗ зависимостей от других сервисов, чтобы разорвать
циклический импорт: candidate.py (триггерит переиндексацию) → base_search.py
(семантический поиск) → … . Раньше base_search импортировал эти хелперы из candidate,
из-за чего candidate не мог импортировать base_search на верхнем уровне.
"""

from datetime import date


def _compute_age(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _compute_full_name(last_name: str, first_name: str, middle_name: str | None) -> str:
    return " ".join(part for part in (last_name, first_name, middle_name) if part)
