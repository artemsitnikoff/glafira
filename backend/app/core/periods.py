"""Общие константы для периодов в Home и Analytics доменах"""

from datetime import date, timedelta

HOME_PERIODS = {'week': 7, 'month': 30, 'quarter': 90, 'year': 365, 'all': None}
ANALYTICS_PERIODS = {'week': 7, 'month': 30, 'quarter': 90, 'year': 365}


def parse_home_period(period: str) -> int | None:
    """Парсит строку периода в количество дней или None для 'all'"""
    if period not in HOME_PERIODS:
        from .errors import ValidationError
        raise ValidationError(f"Недопустимый период: {period}")
    return HOME_PERIODS[period]


def resolve_analytics_window(period: str, date_from: date | None = None, date_to: date | None = None) -> tuple[date, date]:
    """Resolves analytics period to date range"""
    from .errors import ValidationError

    today = date.today()

    if period in ANALYTICS_PERIODS:
        days = ANALYTICS_PERIODS[period]
        return today - timedelta(days=days), today

    if period == 'custom':
        if not date_from or not date_to:
            raise ValidationError("period=custom требует date_from и date_to")
        if date_from > date_to:
            raise ValidationError("date_from > date_to")
        return date_from, date_to

    raise ValidationError(f"Недопустимый период: {period}")