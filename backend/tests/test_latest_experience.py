"""Unit tests for pick_latest_experience (мета карточки = самая свежая запись опыта)."""

from app.services.candidate import (
    pick_latest_experience,
    format_duration,
    _period_to_months,
    total_experience,
    _exp_recency_key,
)


class _Exp:
    def __init__(self, company, period):
        self.company = company
        self.position = "Dev"
        self.period = period


def test_picks_ongoing_job():
    """Текущая работа («Наст. время») выигрывает, даже если в списке не первая/не последняя."""
    exps = [
        _Exp("Surf", "Июл 2018 — Авг 2019"),
        _Exp("Авито", "Март 2023 — Наст. время"),
        _Exp("Lamoda", "Июн 2021 — Фев 2023"),
        _Exp("Ростелеком", "Сен 2019 — Май 2021"),
    ]
    assert pick_latest_experience(exps).company == "Авито"


def test_picks_latest_end_year_when_no_ongoing():
    exps = [
        _Exp("Стартап", "2020-2022"),
        _Exp("Mail.ru", "2022-2024"),
        _Exp("Веб-студия", "2019-2021"),
    ]
    assert pick_latest_experience(exps).company == "Mail.ru"


def test_empty_returns_none():
    assert pick_latest_experience([]) is None
    assert pick_latest_experience(None) is None


def test_format_duration():
    assert format_duration(0) is None
    assert format_duration(11) == "11 мес"
    assert format_duration(12) == "1 год"
    assert format_duration(13) == "1 год 1 мес"
    assert format_duration(24) == "2 года"
    assert format_duration(38) == "3 года 2 мес"
    assert format_duration(60) == "5 лет"
    assert format_duration(91) == "7 лет 7 мес"


def test_period_to_months_year_range():
    assert _period_to_months("2020-2022") == 24       # «2020-2022» = 2 года
    assert _period_to_months("Июл 2018 — Авг 2019") == 13
    assert _period_to_months("Июн 2021 — Фев 2023") == 20
    assert _period_to_months(None) == 0
    assert _period_to_months("кривая строка") == 0


def test_total_experience_sums():
    exps = [_Exp("A", "2018-2019"), _Exp("B", "2020-2022"), _Exp("C", "2022-2024")]
    # 12 + 24 + 24 = 60 мес = 5 лет
    assert total_experience(exps) == "5 лет"


def test_period_to_months_hh_yyyy_mm():
    assert _period_to_months("2005-04 — 2005-10") == 6
    assert _period_to_months("2020-01 — 2021-07") == 18
    assert _period_to_months("2003-07 — 2005-03") == 20


def test_period_to_months_present_hh():
    from datetime import date
    months = _period_to_months("2024-01 — по наст. время")
    assert months == (date.today().year - 2024) * 12 + (date.today().month - 1)


def test_recency_key_month_granularity():
    # обе заканчиваются в 2018 — новее та, что позже по месяцу
    assert _exp_recency_key("2018-07 — 2018-08") > _exp_recency_key("2018-03 — 2018-06")


def test_pick_latest_present_hh_wins():
    exps = [_Exp("Old", "2005-04 — 2005-10"), _Exp("Cur", "2025-03 — по наст. время")]
    assert pick_latest_experience(exps).company == "Cur"
