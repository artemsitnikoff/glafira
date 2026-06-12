"""Дедупликация кандидатов - общие функции для импорта и создания"""

import re
from uuid import UUID
from typing import Literal

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Candidate


def _clean_phone(value: str) -> str:
    """Очистка и нормализация телефона"""
    if not value:
        return ""

    # Только цифры
    digits = re.sub(r'\D', '', str(value))

    if not digits:
        return str(value)[:20]  # Возвращаем как есть, обрезанное

    # Нормализация
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    elif len(digits) == 10:
        digits = '7' + digits

    return '+' + digits


def _normalize_contact(value: str) -> str:
    """Нормализация контакта для дедупликации"""
    if not value:
        return ""

    if '@' in value:  # email
        return value.lower().strip()
    else:  # phone
        return _clean_phone(value).replace('+', '').replace(' ', '')


def _phone_query_variants(norm_digits: str) -> list[str]:
    """Возможные форматы хранения телефона в БД для нормализованных цифр (телефоны в базе
    приходят в разном виде: '+7…' из импорта/формы, '8…'/'7…' из других источников).
    Нужно для дедуп-матча: ключ дедупа нормализуется через _normalize_contact одинаково
    с обеих сторон, но SQL-запрос должен ВЕРНУТЬ кандидата по любому из форматов."""
    if not norm_digits:
        return []
    out = {norm_digits, "+" + norm_digits}
    if len(norm_digits) == 11 and norm_digits.startswith("7"):
        rest = norm_digits[1:]
        out.update({"8" + rest, "+7" + rest, "7" + rest})
    return list(out)


async def _get_existing_candidates(session: AsyncSession, company_id: UUID,
                                 phones: list[str], emails: list[str]) -> list[Candidate]:
    """Получение существующих кандидатов для дедупликации (СТРОГО в рамках company)."""
    if not phones and not emails:
        return []

    conditions = []
    if phones:
        variants = set()
        for p in phones:
            variants.update(_phone_query_variants(p))
        if variants:
            conditions.append(Candidate.phone.in_(list(variants)))
    if emails:
        conditions.append(func.lower(Candidate.email).in_([e.lower() for e in emails]))

    if not conditions:
        return []

    result = await session.execute(
        select(Candidate).where(
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
            or_(*conditions)
        )
    )
    return result.scalars().all()


async def find_duplicate_candidates(session: AsyncSession, company_id: UUID,
                                  phone: str | None, email: str | None) -> list[Candidate]:
    """Найти дубликаты кандидата по телефону и/или email в рамках компании.

    Returns:
        Список найденных кандидатов (может быть пустым)
    """
    if not phone and not email:
        return []

    phones = []
    emails = []

    if phone:
        normalized_phone = _normalize_contact(phone)
        if normalized_phone:
            phones.append(normalized_phone)

    if email:
        normalized_email = _normalize_contact(email)
        if normalized_email:
            emails.append(normalized_email)

    return await _get_existing_candidates(session, company_id, phones, emails)


def _fio_match_level(provided_last: str | None, provided_first: str | None,
                     provided_middle: str | None, cand: Candidate) -> Literal['exact', 'possible']:
    """Определение уровня совпадения ФИО.

    Args:
        provided_last: Фамилия из запроса
        provided_first: Имя из запроса
        provided_middle: Отчество из запроса (опционально)
        cand: Кандидат для сравнения

    Returns:
        'exact' если provided_core ⊆ cand_words (нечувствительно к регистру)
        'possible' в остальных случаях (включая когда ФИО не передано)
    """
    # Собираем непустые части ФИО из запроса
    provided_parts = []
    if provided_last and provided_last.strip():
        provided_parts.append(provided_last.lower().strip())
    if provided_first and provided_first.strip():
        provided_parts.append(provided_first.lower().strip())
    if provided_middle and provided_middle.strip():
        provided_parts.append(provided_middle.lower().strip())

    provided_core = set(provided_parts)

    # Если ФИО не передано или пустое - подтвердить нельзя
    if not provided_core:
        return 'possible'

    # Собираем слова из ФИО кандидата
    cand_words = set()
    if cand.last_name:
        cand_words.add(cand.last_name.lower().strip())
    if cand.first_name:
        cand_words.add(cand.first_name.lower().strip())
    if cand.middle_name:
        cand_words.add(cand.middle_name.lower().strip())

    # Точное совпадение: все переданные части есть в ФИО кандидата
    if provided_core and provided_core.issubset(cand_words):
        return 'exact'

    return 'possible'