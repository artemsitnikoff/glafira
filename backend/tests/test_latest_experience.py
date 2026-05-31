"""Unit tests for pick_latest_experience (мета карточки = самая свежая запись опыта)."""

from app.services.candidate import pick_latest_experience


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
