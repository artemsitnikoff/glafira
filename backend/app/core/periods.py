"""Общие константы для периодов в Home домене"""

HOME_PERIODS = {'week': 7, 'month': 30, 'quarter': 90, 'year': 365, 'all': None}


def parse_home_period(period: str) -> int | None:
    """Парсит строку периода в количество дней или None для 'all'"""
    if period not in HOME_PERIODS:
        from .errors import ValidationError
        raise ValidationError(f"Недопустимый период: {period}")
    return HOME_PERIODS[period]