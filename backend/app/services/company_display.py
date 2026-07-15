"""Название компании для текстов, которые Глафира пишет КАНДИДАТУ.

Смысл: арендатор (кадровое агентство) ведёт подбор для сотен клиентов-заказчиков.
Кандидату надо называть компанию ВАКАНСИИ (её заказчика), а не «Глафира Рекрутёр».

Приоритет:
  1. Заказчик вакансии (vacancy.client_id → Client.name), company-scoped;
  2. Фолбэк — компания-арендатор (Company.name, Настройки→Общие).

⚠️ АРХИТЕКТУРНОЕ ПРАВИЛО: `Vacancy.client` — relationship БЕЗ eager-загрузки
(`models/vacancy.py`, lazy="select"). Обращение к `vacancy.client` в async-сессии
даёт MissingGreenlet. Поэтому здесь НИКОГДА не трогаем `vacancy.client` —
только явный `select(Client.name)` по `vacancy.client_id`. Это избавляет от
правки `selectinload` по всем вызывающим; цена — один лёгкий запрос.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Client, Company, Vacancy

logger = logging.getLogger(__name__)


async def resolve_company_display_name(
    session: AsyncSession,
    company_id: UUID,
    vacancy: Vacancy | None = None,
) -> str:
    """Название компании для текстов кандидату: заказчик вакансии → фолбэк на арендатора.

    Args:
        session: активная async-сессия.
        company_id: компания-арендатор (мультитенантность — скоуп обязателен).
        vacancy: вакансия, по которой пишем кандидату (может быть None — служебные/
            общие тексты; тогда сразу фолбэк на арендатора).

    Returns:
        Непустую строку с названием компании. При полном отсутствии данных — "".
        НИКОГДА не None (пустых мест в текстах кандидату быть не должно).
    """
    # 1. Заказчик вакансии. client_id читаем с самого объекта (обычная колонка,
    #    НЕ relationship) — lazy-load не триггерится.
    client_id = getattr(vacancy, "client_id", None) if vacancy is not None else None
    if client_id:
        client_name = (await session.execute(
            select(Client.name).where(
                Client.id == client_id,
                # company-scoped: чужой клиент не должен утечь в текст кандидату
                Client.company_id == company_id,
            )
        )).scalar_one_or_none()
        if client_name and client_name.strip():
            return client_name.strip()

    # 2. Фолбэк — компания-арендатор.
    company_name = (await session.execute(
        select(Company.name).where(Company.id == company_id)
    )).scalar_one_or_none()
    if company_name and company_name.strip():
        return company_name.strip()

    logger.warning(
        "[company_display] не удалось определить название компании (company_id=%s)",
        company_id,
    )
    return ""
