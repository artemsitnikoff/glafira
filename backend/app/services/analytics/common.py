"""Общие утилиты для Analytics"""

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Query
from sqlalchemy.sql.selectable import Select

from ...models import Vacancy


@dataclass
class AnalyticsFilters:
    period: str
    date_from: date | None
    date_to: date | None
    vacancy_ids: list[UUID]
    recruiter_ids: list[UUID]
    compare: bool


def compute_delta_dir(current: float, previous: float | None, *, lower_is_better: bool = False) -> str:
    """Вычисляет направление изменения для KPI с обработкой division by zero"""
    if previous is None:
        return 'flat'

    if previous == 0:
        if current == 0:
            return 'flat'
        elif current > 0:
            return 'up-bad' if lower_is_better else 'up'
        else:
            return 'down-good' if lower_is_better else 'down'

    if current == previous:
        return 'flat'

    is_growing = current > previous

    if lower_is_better:
        return 'up-bad' if is_growing else 'down-good'
    else:
        return 'up' if is_growing else 'down'


def apply_vacancy_filter(query: Select, model_attr: Any, vacancy_ids: list[UUID]) -> Select:
    """Применяет фильтр по vacancy_ids к запросу"""
    if vacancy_ids:
        query = query.where(model_attr.in_(vacancy_ids))
    return query


def apply_recruiter_filter(query: Select, vacancy_alias, recruiter_ids: list[UUID]) -> Select:
    """Применяет фильтр по recruiter_ids через JOIN на vacancies.responsible_user_id"""
    if recruiter_ids:
        query = query.join(vacancy_alias).where(vacancy_alias.responsible_user_id.in_(recruiter_ids))
    return query


def compute_delta(current: float, previous: float | None, *, lower_is_better: bool = False) -> tuple[float | None, str]:
    """Возвращает дельту и направление изменения"""
    if previous is None:
        return None, 'flat'

    if previous == 0:
        if current == 0:
            return 0.0, 'flat'
        else:
            # Division by zero: возвращаем None для delta но указываем направление
            delta_dir = 'up-bad' if (lower_is_better and current > 0) else ('down-good' if (lower_is_better and current < 0) else ('up' if current > 0 else 'down'))
            return None, delta_dir

    delta = current - previous
    delta_dir = compute_delta_dir(current, previous, lower_is_better=lower_is_better)
    return delta, delta_dir