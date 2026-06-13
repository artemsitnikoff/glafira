"""Тесты дедупликации кандидатов (сервисный уровень).

Фикстуры — из conftest: db_session, admin_user (создаёт компанию), test_company
(= компания admin_user). Пароль/HTTP здесь не нужны — дёргаем сервисы напрямую.
"""

import pytest
from uuid import uuid4

from app.schemas.candidate import CandidateCreate
from app.services.candidate import create_candidate, check_candidate_duplicates
from app.services.candidate_dedup import find_duplicate_candidates
from app.core.errors import ConflictError


@pytest.mark.asyncio
async def test_phone_normalization_finds_same_candidate(db_session, test_company, admin_user):
    """Телефон 8XXX / +7XXX / 7XXX находят одного и того же кандидата"""
    candidate_data = CandidateCreate(
        last_name="Петров",
        first_name="Пётр",
        source="manual",
        phone="+79001234567",
        email="petrov@example.com"
    )
    await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    await db_session.commit()

    # Ищем тем же телефоном в разных форматах
    duplicates_1 = await find_duplicate_candidates(db_session, test_company.id, "89001234567", None)
    duplicates_2 = await find_duplicate_candidates(db_session, test_company.id, "79001234567", None)
    duplicates_3 = await find_duplicate_candidates(db_session, test_company.id, "+79001234567", None)

    assert len(duplicates_1) == 1
    assert len(duplicates_2) == 1
    assert len(duplicates_3) == 1
    assert duplicates_1[0].id == duplicates_2[0].id == duplicates_3[0].id


@pytest.mark.asyncio
async def test_email_case_insensitive_finds_candidate(db_session, test_company, admin_user):
    """Email разного регистра находит одного кандидата"""
    candidate_data = CandidateCreate(
        last_name="Сидоров",
        first_name="Сидор",
        source="manual",
        phone=None,
        email="sidorov@EXAMPLE.COM"
    )
    await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    await db_session.commit()

    duplicates_1 = await find_duplicate_candidates(db_session, test_company.id, None, "sidorov@example.com")
    duplicates_2 = await find_duplicate_candidates(db_session, test_company.id, None, "SIDOROV@example.com")
    duplicates_3 = await find_duplicate_candidates(db_session, test_company.id, None, "sidorov@EXAMPLE.COM")

    assert len(duplicates_1) == 1
    assert len(duplicates_2) == 1
    assert len(duplicates_3) == 1
    assert duplicates_1[0].id == duplicates_2[0].id == duplicates_3[0].id


@pytest.mark.asyncio
async def test_company_isolation(db_session, test_company, admin_user):
    """Кандидат с тем же телефоном в ДРУГОЙ компании НЕ найден (изоляция, КРИТИЧНО).

    Создаём кандидата в нашей компании; ищем дубль от лица другой company_id —
    телефон в БД есть, но фильтр company_id обязан его отсечь (иначе утечка PII
    между арендаторами).
    """
    candidate_data = CandidateCreate(
        last_name="Изолированный",
        first_name="Тест",
        source="manual",
        phone="+79111111111"
    )
    await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    await db_session.commit()

    # Наша компания — находит
    own = await find_duplicate_candidates(db_session, test_company.id, "+79111111111", None)
    assert len(own) == 1

    # Другая компания — НЕ находит (тот же телефон в БД, но чужой company_id)
    other_company_id = uuid4()
    duplicates = await find_duplicate_candidates(db_session, other_company_id, "+79111111111", None)
    assert len(duplicates) == 0


@pytest.mark.asyncio
async def test_fio_match_level_exact(db_session, test_company, admin_user):
    """ФИО совпало → match_level='exact'"""
    candidate_data = CandidateCreate(
        last_name="Точнов",
        first_name="Точный",
        middle_name="Точнович",
        source="manual",
        phone="+79222222222"
    )
    await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    await db_session.commit()

    response = await check_candidate_duplicates(
        db_session, test_company.id,
        phone="+79222222222",
        email=None,
        first_name="Точный",
        last_name="Точнов",
        middle_name="Точнович"
    )

    assert response.found is True
    assert response.match_count == 1
    assert len(response.matches) == 1
    assert response.matches[0].match_level == "exact"
    assert response.matches[0].matched_by == "phone"


@pytest.mark.asyncio
async def test_fio_match_level_possible(db_session, test_company, admin_user):
    """ФИО отличается → match_level='possible'"""
    candidate_data = CandidateCreate(
        last_name="Другов",
        first_name="Другой",
        source="manual",
        phone="+79333333333"
    )
    await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    await db_session.commit()

    response = await check_candidate_duplicates(
        db_session, test_company.id,
        phone="+79333333333",
        email=None,
        first_name="НеТот",
        last_name="НеТакой"
    )

    assert response.found is True
    assert response.matches[0].match_level == "possible"


@pytest.mark.asyncio
async def test_fio_match_level_possible_when_no_fio(db_session, test_company, admin_user):
    """Без ФИО в запросе → match_level='possible'"""
    candidate_data = CandidateCreate(
        last_name="Безымянов",
        first_name="Безымян",
        source="manual",
        phone="+79444444444"
    )
    await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    await db_session.commit()

    response = await check_candidate_duplicates(
        db_session, test_company.id,
        phone="+79444444444"
    )

    assert response.found is True
    assert response.matches[0].match_level == "possible"


@pytest.mark.asyncio
async def test_multiple_matches_limited_to_3(db_session, test_company, admin_user):
    """Несколько совпавших → match_count>3, matches≤3"""
    for i in range(5):
        candidate_data = CandidateCreate(
            last_name=f"Множеств{i}",
            first_name=f"Мног{i}",
            source="manual",
            email="many@example.com",
            force_duplicate=True,  # сами создаём дубли намеренно, не через UI
        )
        await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)

    await db_session.commit()

    response = await check_candidate_duplicates(
        db_session, test_company.id,
        email="many@example.com"
    )

    assert response.found is True
    assert response.match_count == 5  # Всего найдено 5
    assert len(response.matches) == 3  # Но возвращено только 3


@pytest.mark.asyncio
async def test_create_without_force_raises_409(db_session, test_company, admin_user):
    """create без force при существующем телефоне → 409 DUPLICATE_CANDIDATE"""
    candidate_data_1 = CandidateCreate(
        last_name="Первый",
        first_name="Кандидат",
        source="manual",
        phone="+79555555555"
    )
    await create_candidate(db_session, candidate_data_1, test_company.id, admin_user.id)
    await db_session.commit()

    candidate_data_2 = CandidateCreate(
        last_name="Второй",
        first_name="Дубль",
        source="manual",
        phone="+79555555555"
    )

    with pytest.raises(ConflictError) as exc_info:
        await create_candidate(db_session, candidate_data_2, test_company.id, admin_user.id)

    assert exc_info.value.code == "DUPLICATE_CANDIDATE"
    assert exc_info.value.status_code == 409
    assert exc_info.value.details is not None
    assert "match_count" in exc_info.value.details
    assert "matches" in exc_info.value.details
    assert exc_info.value.details["matches"][0]["matched_by"] == "phone"


@pytest.mark.asyncio
async def test_create_with_force_duplicate_true_succeeds(db_session, test_company, admin_user):
    """create с force_duplicate=True → создаётся, audit.after.duplicate_of непустой"""
    candidate_data_1 = CandidateCreate(
        last_name="Оригинал",
        first_name="Первый",
        source="manual",
        phone="+79666666666"
    )
    original = await create_candidate(db_session, candidate_data_1, test_company.id, admin_user.id)
    await db_session.commit()

    candidate_data_2 = CandidateCreate(
        last_name="Дубль",
        first_name="Второй",
        source="manual",
        phone="+79666666666",
        force_duplicate=True
    )
    duplicate = await create_candidate(db_session, candidate_data_2, test_company.id, admin_user.id)
    await db_session.commit()

    assert duplicate.id != original.id
    assert duplicate.full_name == "Дубль Второй"

    from app.models import AuditLog
    from sqlalchemy import select

    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == duplicate.id,
            AuditLog.action == "create"
        )
    )
    audit_record = audit_result.scalar_one()

    # AuditLog хранит до/после в JSONB-колонке `changes` (changes["after"]), нет атрибута .after
    assert audit_record.changes is not None
    assert "duplicate_of" in audit_record.changes["after"]
    assert str(original.id) in audit_record.changes["after"]["duplicate_of"]


@pytest.mark.asyncio
async def test_create_with_force_when_no_duplicate_normal_creation(db_session, test_company, admin_user):
    """create с force при отсутствии дубля → обычное создание (без duplicate_of)"""
    candidate_data = CandidateCreate(
        last_name="Уникальный",
        first_name="Единственный",
        source="manual",
        phone="+79777777777",
        force_duplicate=True  # force=True, но дубля нет
    )

    result = await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    await db_session.commit()

    assert result.full_name == "Уникальный Единственный"

    from app.models import AuditLog
    from sqlalchemy import select

    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == result.id,
            AuditLog.action == "create"
        )
    )
    audit_record = audit_result.scalar_one()

    assert audit_record.changes is not None
    assert "duplicate_of" not in audit_record.changes["after"]


@pytest.mark.asyncio
async def test_existing_import_functions_still_work(db_session, test_company):
    """Функции импорта НЕ сломаны: резолвятся из нового модуля candidate_dedup"""
    from app.services.candidate_import import (
        _clean_phone, _normalize_contact, _phone_query_variants, _get_existing_candidates
    )

    assert _clean_phone("8(900)123-45-67") == "+79001234567"
    assert _normalize_contact("Test@EXAMPLE.com") == "test@example.com"
    assert _normalize_contact("+79001234567") == "79001234567"

    variants = _phone_query_variants("79001234567")
    assert "+79001234567" in variants
    assert "89001234567" in variants
    assert "79001234567" in variants

    candidates = await _get_existing_candidates(
        db_session, test_company.id, ["79001234567"], ["test@example.com"]
    )
    assert len(candidates) == 0


def test_fio_match_level_unit():
    """Тест _fio_match_level вне БД (set-based, регистронезависимо)"""
    from app.services.candidate_dedup import _fio_match_level

    class MockCandidate:
        def __init__(self, last_name, first_name, middle_name=None):
            self.last_name = last_name
            self.first_name = first_name
            self.middle_name = middle_name

    candidate = MockCandidate("Иванов", "Иван", "Иванович")

    # Exact — все поля совпали
    assert _fio_match_level("Иванов", "Иван", "Иванович", candidate) == "exact"
    # Exact — без отчества, но фамилия+имя совпали
    assert _fio_match_level("Иванов", "Иван", None, candidate) == "exact"
    # Exact — регистр не важен
    assert _fio_match_level("ИВАНОВ", "иван", None, candidate) == "exact"
    # Possible — отличается имя
    assert _fio_match_level("Иванов", "Пётр", None, candidate) == "possible"
    # Possible — отличается фамилия
    assert _fio_match_level("Петров", "Иван", None, candidate) == "possible"
    # Possible — ФИО не переданы
    assert _fio_match_level(None, None, None, candidate) == "possible"
    assert _fio_match_level("", "", "", candidate) == "possible"
