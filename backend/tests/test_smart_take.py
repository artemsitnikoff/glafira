"""Тесты функции take_selected («Забрать к себе») — умный подбор hh, без negotiation.

⚠️ ВСЕ ТЕСТЫ НА МОКАХ — ни одного реального hh.ru вызова!
Реальный «забор» (открытие контакта = платная операция) проверяет заказчик.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from sqlalchemy import select

from app.services.smart_search import take_selected
from app.models import SmartSearchRun, Candidate, Application
from app.core.errors import ValidationError, NotFoundError

from contextlib import asynccontextmanager


# ---------------------------------------------------------------------------
# Вспомогательные утилиты
# ---------------------------------------------------------------------------

def _session_local_returning(db_session):
    """Фабрика-заглушка вместо AsyncSessionLocal(): отдаёт тестовый db_session."""
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


def _make_fake_resume(
    resume_id: str = "abc123",
    first_name: str = "Иван",
    last_name: str = "Иванов",
    phone_formatted: str = "89991234567",
    email: str = "ivan@example.com",
) -> dict:
    """Минимальное резюме в формате hh.ru get_resume_by_id."""
    return {
        "id": resume_id,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": None,
        "title": "Python-разработчик",
        "area": {"id": "1", "name": "Москва"},
        "contact": [
            {
                "type": {"id": "cell"},
                "value": {"formatted": phone_formatted, "number": phone_formatted},
            },
            {
                "type": {"id": "email"},
                "value": email,
            },
        ],
        "skills": "Python, FastAPI",
        "experience": [],
    }


async def _create_run(db_session, company_id, vacancy_id) -> SmartSearchRun:
    """Создаёт и коммитит SmartSearchRun в тестовой сессии."""
    run = SmartSearchRun(
        company_id=company_id,
        vacancy_id=vacancy_id,
        status="done",
        stage="done",
        params={"scan_n": 10},
        scored_candidates=[
            {"hh_resume_id": "abc123", "name": "Иван Иванов", "score": 80, "passed": True}
        ],
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Тест 1: happy path — кандидат создан с source='smart', БЕЗ negotiation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.services.smart_search.hh_client.invite_to_vacancy")
@patch("app.services.smart_search.hh_client.get_resume_by_id")
@patch("app.services.smart_search.hh_service.get_valid_access_token")
@patch("app.services.smart_search.check_access")
@patch("app.services.smart_search.AsyncSessionLocal")
async def test_take_selected_creates_smart_candidate(
    mock_session_local,
    mock_check_access,
    mock_token,
    mock_get_resume,
    mock_invite,
    db_session,
    test_company,
    test_vacancy,
    admin_user,
):
    """Забрать → Candidate source='smart', extra.smart_search=True,
    Application(stage='added', hh_negotiation_id is None).
    invite_to_vacancy НЕ вызывается."""

    mock_session_local.side_effect = _session_local_returning(db_session)
    mock_check_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"

    resume_id = "abc123"
    mock_get_resume.return_value = _make_fake_resume(resume_id=resume_id)

    run = await _create_run(db_session, test_company.id, test_vacancy.id)

    result = await take_selected(
        db_session,
        test_company.id,
        admin_user.id,
        run.id,
        [resume_id],
    )

    # Результат
    assert result["taken_count"] == 1
    assert len(result["results"]) == 1
    item = result["results"][0]
    assert item["resume_id"] == resume_id
    assert item["status"] == "taken"
    assert item["candidate_id"] is not None

    # invite_to_vacancy НЕ вызван
    mock_invite.assert_not_called()

    # Кандидат в БД
    candidate = await db_session.get(Candidate, item["candidate_id"])
    assert candidate is not None
    assert candidate.source == "smart"
    assert candidate.extra.get("smart_search") is True
    assert candidate.extra.get("hh_resume_id") == resume_id
    assert candidate.company_id == test_company.id

    # Application без negotiation, stage='added'
    app_result = await db_session.execute(
        select(Application).where(
            Application.candidate_id == candidate.id,
            Application.vacancy_id == test_vacancy.id,
        )
    )
    application = app_result.scalar_one_or_none()
    assert application is not None
    assert application.stage == "added"
    assert application.hh_negotiation_id is None


# ---------------------------------------------------------------------------
# Тест 2: телефон нормализуется в E.164 (цифры без '+')
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.services.smart_search.hh_client.invite_to_vacancy")
@patch("app.services.smart_search.hh_client.get_resume_by_id")
@patch("app.services.smart_search.hh_service.get_valid_access_token")
@patch("app.services.smart_search.check_access")
@patch("app.services.smart_search.AsyncSessionLocal")
async def test_take_phone_normalized_e164(
    mock_session_local,
    mock_check_access,
    mock_token,
    mock_get_resume,
    mock_invite,
    db_session,
    test_company,
    test_vacancy,
    admin_user,
):
    """Телефон '89991234567' должен стать '79991234567' (E.164, цифры без '+')."""

    mock_session_local.side_effect = _session_local_returning(db_session)
    mock_check_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"

    resume_id = "phone_test"
    # Имитируем hh, который отдаёт телефон в формате 8999...
    mock_get_resume.return_value = _make_fake_resume(
        resume_id=resume_id,
        first_name="Телефон",
        last_name="Тестов",
        phone_formatted="89991234567",
        email="phone_test@example.com",
    )

    run = await _create_run(db_session, test_company.id, test_vacancy.id)
    # Добавляем резюме в scored_candidates для этого run
    run.scored_candidates = [
        {"hh_resume_id": resume_id, "name": "Телефон Тестов", "score": 75, "passed": True}
    ]
    await db_session.commit()

    result = await take_selected(
        db_session, test_company.id, admin_user.id, run.id, [resume_id]
    )

    assert result["taken_count"] == 1
    candidate_id = result["results"][0]["candidate_id"]
    candidate = await db_session.get(Candidate, candidate_id)
    # 8999... → 7999... (нормализация: 8→7)
    assert candidate.phone == "79991234567"


# ---------------------------------------------------------------------------
# Тест 3: дедуп — существующий кандидат привязывается к воронке, дубль не создаётся
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.services.smart_search.hh_client.invite_to_vacancy")
@patch("app.services.smart_search.hh_client.get_resume_by_id")
@patch("app.services.smart_search.hh_service.get_valid_access_token")
@patch("app.services.smart_search.check_access")
@patch("app.services.smart_search.AsyncSessionLocal")
async def test_take_dedup_existing_candidate_assigned(
    mock_session_local,
    mock_check_access,
    mock_token,
    mock_get_resume,
    mock_invite,
    db_session,
    test_company,
    test_vacancy,
    admin_user,
):
    """Существующий кандидат → status='already', кандидат привязан к воронке,
    второй Candidate НЕ создан."""

    mock_session_local.side_effect = _session_local_returning(db_session)
    mock_check_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"

    resume_id = "dedup_resume"

    # Создаём кандидата, который уже в базе с hh_resume_id в extra
    existing_candidate = Candidate(
        company_id=test_company.id,
        first_name="Существующий",
        last_name="Кандидат",
        source="hh",
        extra={"hh_resume_id": resume_id},
    )
    db_session.add(existing_candidate)
    await db_session.commit()
    await db_session.refresh(existing_candidate)

    run = await _create_run(db_session, test_company.id, test_vacancy.id)
    run.scored_candidates = [
        {"hh_resume_id": resume_id, "name": "Существующий Кандидат", "score": 80, "passed": True}
    ]
    await db_session.commit()

    result = await take_selected(
        db_session, test_company.id, admin_user.id, run.id, [resume_id]
    )

    # Результат: already, candidate_id совпадает с existing
    assert result["taken_count"] == 0
    assert len(result["results"]) == 1
    item = result["results"][0]
    assert item["status"] == "already"
    assert item["candidate_id"] == existing_candidate.id

    # get_resume_by_id НЕ вызывался (дедуп до сетевого вызова)
    mock_get_resume.assert_not_called()
    # invite_to_vacancy тоже не вызывался
    mock_invite.assert_not_called()

    # Дубликат НЕ создан — в БД ровно один кандидат с этим hh_resume_id
    dup_result = await db_session.execute(
        select(Candidate).where(
            Candidate.company_id == test_company.id,
            Candidate.extra["hh_resume_id"].astext == resume_id,
            Candidate.deleted_at.is_(None),
        )
    )
    all_matching = dup_result.scalars().all()
    assert len(all_matching) == 1

    # Кандидат привязан к воронке вакансии
    app_result = await db_session.execute(
        select(Application).where(
            Application.candidate_id == existing_candidate.id,
            Application.vacancy_id == test_vacancy.id,
        )
    )
    application = app_result.scalar_one_or_none()
    assert application is not None


# ---------------------------------------------------------------------------
# Тест 4: нет платного доступа → ValidationError fail-closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.services.smart_search.hh_service.get_valid_access_token")
@patch("app.services.smart_search.check_access")
async def test_take_no_paid_access_raises(
    mock_check_access,
    mock_token,
    db_session,
    test_company,
    test_vacancy,
    admin_user,
):
    """has_paid_access=False → ValidationError (контакт платный, fail-closed)."""

    mock_check_access.return_value = (True, False, "Нет платного доступа")
    mock_token.return_value = "test_token"

    run = await _create_run(db_session, test_company.id, test_vacancy.id)

    with pytest.raises(ValidationError) as exc_info:
        await take_selected(
            db_session, test_company.id, admin_user.id, run.id, ["abc123"]
        )

    assert "платного доступа" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Тест 5: company-изоляция — run другой компании → NotFoundError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.services.smart_search.check_access")
async def test_take_company_isolation(
    mock_check_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user,
    other_company,
):
    """run принадлежит другой компании → NotFoundError."""

    mock_check_access.return_value = (True, True, None)

    # Создаём run на другую компанию
    other_run = SmartSearchRun(
        company_id=other_company.id,
        vacancy_id=test_vacancy.id,
        status="done",
        stage="done",
        params={"scan_n": 5},
    )
    db_session.add(other_run)
    await db_session.commit()
    await db_session.refresh(other_run)

    with pytest.raises(NotFoundError):
        await take_selected(
            db_session,
            test_company.id,  # не совпадает с run.company_id
            admin_user.id,
            other_run.id,
            ["abc123"],
        )


# ---------------------------------------------------------------------------
# Тест 6: bulk — один ок, один с ошибкой получения резюме → частичный успех
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.services.smart_search.hh_client.invite_to_vacancy")
@patch("app.services.smart_search.hh_client.get_resume_by_id")
@patch("app.services.smart_search.hh_service.get_valid_access_token")
@patch("app.services.smart_search.check_access")
@patch("app.services.smart_search.AsyncSessionLocal")
async def test_take_bulk_partial_success(
    mock_session_local,
    mock_check_access,
    mock_token,
    mock_get_resume,
    mock_invite,
    db_session,
    test_company,
    test_vacancy,
    admin_user,
):
    """Два resume_id: первый ок, второй — ошибка get_resume_by_id.
    Возвращается taken_count=1, results содержат обе записи."""

    mock_session_local.side_effect = _session_local_returning(db_session)
    mock_check_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"

    resume_ok = "ok_resume"
    resume_err = "err_resume"

    # AsyncMock side_effect: sync-функция возвращает DICT напрямую (await вернёт его);
    # для err-ветки raise → await пробросит. НЕ оборачивать в корутину (двойная обёртка
    # → full_resume станет coroutine → .get() упадёт).
    def _get_resume_side_effect(token, resume_id):
        if resume_id == resume_ok:
            return _make_fake_resume(
                resume_id=resume_ok,
                first_name="Ок",
                last_name="Кандидат",
                phone_formatted="79001234567",
                email="ok@example.com",
            )
        else:
            raise Exception("hh api error")

    mock_get_resume.side_effect = _get_resume_side_effect

    run = await _create_run(db_session, test_company.id, test_vacancy.id)
    run.scored_candidates = [
        {"hh_resume_id": resume_ok, "name": "Ок Кандидат", "score": 80, "passed": True},
        {"hh_resume_id": resume_err, "name": "Err Кандидат", "score": 75, "passed": True},
    ]
    await db_session.commit()

    result = await take_selected(
        db_session, test_company.id, admin_user.id, run.id, [resume_ok, resume_err]
    )

    assert result["taken_count"] == 1
    assert len(result["results"]) == 2

    statuses = {r["resume_id"]: r["status"] for r in result["results"]}
    assert statuses[resume_ok] == "taken"
    assert statuses[resume_err] == "error"

    # invite_to_vacancy НЕ вызывался в обоих случаях
    mock_invite.assert_not_called()
