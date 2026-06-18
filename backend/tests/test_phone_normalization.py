"""Тесты единого нормализатора телефонов (формат хранения: цифры без '+', 79991234567).

Охватывает:
1. normalize_phone — все входные форматы, edge-cases, идемпотентность.
2. Дедуп: кандидат с хранимым 79XXX ловится по 8XXX и другим форматам.
3. Mango-матчинг: find_duplicate_candidates с любым форматом входящего номера.
4. create_candidate сохраняет цифры без '+' (передать '8999…' → в БД '7999…').
5. update_candidate: phone нормализуется при реальном обновлении; без поля — не трогает.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.phone import normalize_phone
from app.services.candidate_dedup import find_duplicate_candidates, _normalize_contact
from app.schemas.candidate import CandidateCreate, CandidateUpdate
from app.services.candidate import create_candidate, update_candidate


# ---------------------------------------------------------------------------
# 1. Юнит-тесты normalize_phone (формат хранения: цифры без '+')
# ---------------------------------------------------------------------------

class TestNormalizePhone:
    """normalize_phone без БД — чистая функция. Возвращает цифры без '+'."""

    def test_8_prefix_11_digits(self):
        assert normalize_phone("89991234567") == "79991234567"

    def test_7_prefix_11_digits(self):
        assert normalize_phone("79991234567") == "79991234567"

    def test_10_digits(self):
        assert normalize_phone("9991234567") == "79991234567"

    def test_plus7_with_spaces_dashes(self):
        assert normalize_phone("+7 999 123-45-67") == "79991234567"

    def test_plus7_with_parens(self):
        assert normalize_phone("+7(999)123-45-67") == "79991234567"

    def test_already_stored_idempotent(self):
        result = normalize_phone("79991234567")
        assert result == "79991234567"
        # Второй прогон — без изменений
        assert normalize_phone(result) == "79991234567"

    def test_plus_form_stripped(self):
        assert normalize_phone("+79991234567") == "79991234567"

    def test_none_returns_none(self):
        assert normalize_phone(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_phone("") is None

    def test_dash_no_digits_returns_none(self):
        assert normalize_phone("—") is None

    def test_text_no_digits_returns_none(self):
        assert normalize_phone("нет") is None

    def test_na_no_digits_returns_none(self):
        assert normalize_phone("n/a") is None

    def test_spaces_only_returns_none(self):
        assert normalize_phone("   ") is None

    def test_8_with_formatting(self):
        """8 (999) 123-45-67 → 79991234567"""
        assert normalize_phone("8 (999) 123-45-67") == "79991234567"

    def test_international_format_no_plus(self):
        """Нероссийский номер: +38XXXXXXXXXX → '380...' (цифры без '+')"""
        result = normalize_phone("+380991234567")
        assert result == "380991234567"
        assert not result.startswith("+")


# ---------------------------------------------------------------------------
# 2. _normalize_contact не сломан при хранении без '+'
# ---------------------------------------------------------------------------

class TestNormalizeContactBackwardCompat:
    """Дедуп-нормализатор (_normalize_contact) даёт одинаковые digits для
    хранения без '+' (79991234567) и для любого входного формата."""

    def test_stored_matches_8_input(self):
        stored = _normalize_contact("79991234567")     # из БД (без '+')
        input_8 = _normalize_contact("89991234567")    # как вводит пользователь
        assert stored == input_8

    def test_stored_matches_plus_input(self):
        stored = _normalize_contact("79991234567")
        input_plus = _normalize_contact("+79991234567")
        assert stored == input_plus

    def test_stored_matches_10digit_input(self):
        stored = _normalize_contact("79991234567")
        input_10 = _normalize_contact("9991234567")
        assert stored == input_10

    def test_stored_matches_formatted_input(self):
        stored = _normalize_contact("79991234567")
        input_fmt = _normalize_contact("+7 (999) 123-45-67")
        assert stored == input_fmt


# ---------------------------------------------------------------------------
# 3. Интеграционные тесты с БД
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dedup_finds_candidate_by_8_format(db_session, test_company, admin_user):
    """Кандидат сохранён без '+' (79…), дедуп находит его по 8…-вводу."""
    data = CandidateCreate(
        last_name="Дедупов",
        first_name="Дедуп",
        source="manual",
        phone="89881112233",
        email=None,
    )
    await create_candidate(db_session, data, test_company.id, admin_user.id)
    await db_session.commit()

    # Кандидат должен быть сохранён без '+'
    from sqlalchemy import select
    from app.models import Candidate
    cands = (await db_session.execute(
        select(Candidate).where(Candidate.company_id == test_company.id, Candidate.last_name == "Дедупов")
    )).scalars().all()
    assert len(cands) == 1
    assert cands[0].phone == "79881112233"

    # Поиск дублей по разным форматам — все находят того же кандидата
    dups_8 = await find_duplicate_candidates(db_session, test_company.id, "89881112233", None)
    dups_plus = await find_duplicate_candidates(db_session, test_company.id, "+79881112233", None)
    dups_7 = await find_duplicate_candidates(db_session, test_company.id, "79881112233", None)
    dups_10 = await find_duplicate_candidates(db_session, test_company.id, "9881112233", None)
    dups_fmt = await find_duplicate_candidates(db_session, test_company.id, "+7 (988) 111-22-33", None)

    assert len(dups_8) == 1
    assert len(dups_plus) == 1
    assert len(dups_7) == 1
    assert len(dups_10) == 1
    assert len(dups_fmt) == 1
    assert dups_8[0].id == dups_plus[0].id == dups_7[0].id == dups_10[0].id == dups_fmt[0].id


@pytest.mark.asyncio
async def test_create_candidate_stores_digits_no_plus(db_session, test_company, admin_user):
    """create_candidate принимает '8999…' и сохраняет '7999…' (без '+')."""
    data = CandidateCreate(
        last_name="Фонов",
        first_name="Формат",
        source="manual",
        phone="84951234567",
        email=None,
    )
    detail = await create_candidate(db_session, data, test_company.id, admin_user.id)
    await db_session.commit()

    assert detail.phone == "74951234567"


@pytest.mark.asyncio
async def test_create_candidate_none_phone_stays_none(db_session, test_company, admin_user):
    """create_candidate без телефона — phone остаётся None."""
    data = CandidateCreate(
        last_name="Безтелов",
        first_name="Борис",
        source="manual",
        phone=None,
        email="beztelov@example.com",
    )
    detail = await create_candidate(db_session, data, test_company.id, admin_user.id)
    await db_session.commit()

    assert detail.phone is None


@pytest.mark.asyncio
async def test_update_candidate_normalizes_phone(db_session, test_company, admin_user):
    """update_candidate: передать '8999…' → в БД '7999…' (без '+')."""
    create_data = CandidateCreate(
        last_name="Обновляев",
        first_name="Обновлён",
        source="manual",
        phone=None,
        email="update_phone@example.com",
    )
    created = await create_candidate(db_session, create_data, test_company.id, admin_user.id)
    await db_session.commit()

    update_data = CandidateUpdate(phone="89161112233")
    updated = await update_candidate(db_session, created.id, update_data, test_company.id, admin_user.id)
    await db_session.commit()

    assert updated.phone == "79161112233"


@pytest.mark.asyncio
async def test_update_candidate_without_phone_field_preserves_existing(db_session, test_company, admin_user):
    """update_candidate без поля phone не трогает существующий номер."""
    create_data = CandidateCreate(
        last_name="Сохранёнов",
        first_name="Сохранён",
        source="manual",
        phone="89162223344",
        email=None,
    )
    created = await create_candidate(db_session, create_data, test_company.id, admin_user.id)
    await db_session.commit()

    # Обновляем только city — phone не передаём
    update_data = CandidateUpdate(city="Москва")
    updated = await update_candidate(db_session, created.id, update_data, test_company.id, admin_user.id)
    await db_session.commit()

    # Телефон должен остаться без изменений
    assert updated.phone == "79162223344"


@pytest.mark.asyncio
async def test_dedup_conflict_on_different_format(db_session, test_company, admin_user):
    """Повторное создание с другим форматом того же номера → ConflictError."""
    from app.core.errors import ConflictError

    data1 = CandidateCreate(
        last_name="Дублеев",
        first_name="Дубль",
        source="manual",
        phone="+79031234567",
        email=None,
    )
    await create_candidate(db_session, data1, test_company.id, admin_user.id)
    await db_session.commit()

    data2 = CandidateCreate(
        last_name="Дублеев",
        first_name="Дубль",
        source="manual",
        phone="8 903 123-45-67",  # другой формат, тот же номер
        email=None,
    )
    with pytest.raises(ConflictError):
        await create_candidate(db_session, data2, test_company.id, admin_user.id)


@pytest.mark.asyncio
async def test_mango_find_duplicate_by_incoming_number(db_session, test_company, admin_user):
    """Mango-матчинг: find_duplicate_candidates находит кандидата по входящему номеру
    независимо от формата хранения в БД."""
    data = CandidateCreate(
        last_name="Звонков",
        first_name="Звонок",
        source="manual",
        phone="89771234567",
        email=None,
    )
    created = await create_candidate(db_session, data, test_company.id, admin_user.id)
    await db_session.commit()

    # Убедились: в БД цифры без '+'
    assert created.phone == "79771234567"

    # Mango получает входящий номер в разных форматах
    for incoming in ("89771234567", "79771234567", "+79771234567", "9771234567"):
        dups = await find_duplicate_candidates(db_session, test_company.id, incoming, None)
        assert len(dups) == 1, f"Не найден кандидат по номеру {incoming!r}"
        assert dups[0].id == created.id
