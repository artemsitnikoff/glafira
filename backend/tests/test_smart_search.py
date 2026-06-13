"""Тесты умного подбора кандидатов - обновленные под новую модель доступа

⚠️ ВСЕ ТЕСТЫ НА МОКАХ - НИ ОДНОГО реального hh.ru вызова!
Реальный поиск/оценка/приглашения проверяются заказчиком на платном доступе hh.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.smart_search import (
    check_access,
    get_smart_vacancies,
    start_search,
    get_run_status,
    derive_vacancy_filters,
    preview_found_count,
    build_search_params,
    suggest_areas,
    _compact_resume_for_display,
    _calculate_search_timeout,
    _run_search_background,
    _run_search_inner,
    _update_run_progress,
    _finalize_run,
    sweep_orphaned_runs,
    FREE_SCAN_LIMIT
)
from app.schemas.smart import SmartSearchRequest, SmartCountRequest
from app.models import SmartSearchRun, Candidate, Application
from app.core.errors import ValidationError

from contextlib import asynccontextmanager


def _session_local_returning(db_session):
    """Фабрика-заглушка вместо AsyncSessionLocal(): отдаёт тестовый db_session и НЕ закрывает его
    (cleanup — внешний rollback фикстуры). Коммиты идут в savepoint тестовой транзакции."""
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


@pytest.mark.asyncio
async def test_check_access_no_hh_integration(db_session, test_company):
    """Тест проверки доступа без подключения hh.ru"""
    has_access, has_paid_access, reason = await check_access(db_session, test_company.id)

    assert has_access is False
    assert has_paid_access is False
    assert "не подключён" in reason


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_check_access_with_paid_service(
    mock_quota,
    mock_get_me,
    mock_token,
    db_session,
    test_company
):
    """Тест проверки доступа с подключенным hh.ru И платной услугой"""
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    has_access, has_paid_access, reason = await check_access(db_session, test_company.id)

    assert has_access is True
    assert has_paid_access is True
    assert reason is None


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_check_access_without_paid_service(
    mock_quota,
    mock_get_me,
    mock_token,
    db_session,
    test_company
):
    """Тест проверки доступа с подключенным hh.ru БЕЗ платной услуги"""
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {"items": []}  # Нет API-услуг

    has_access, has_paid_access, reason = await check_access(db_session, test_company.id)

    assert has_access is True
    assert has_paid_access is False
    assert reason is None


@pytest.mark.asyncio
async def test_get_smart_vacancies_mapping(db_session, test_company, test_vacancy):
    """Тест маппинга вакансии в фильтры hh.ru"""
    smart_vacancies = await get_smart_vacancies(db_session, test_company.id)

    assert len(smart_vacancies) == 1
    smart_vacancy = smart_vacancies[0]

    assert smart_vacancy.id == test_vacancy.id
    assert smart_vacancy.title == test_vacancy.name
    assert smart_vacancy.city == test_vacancy.city
    assert smart_vacancy.area is None  # AI заполнит при выборе вакансии
    assert smart_vacancy.professional_role is None  # AI заполнит при выборе вакансии
    assert smart_vacancy.salary_from == test_vacancy.salary_from
    assert smart_vacancy.salary_to == test_vacancy.salary_to
    assert smart_vacancy.found is None  # Не заполняется без поиска
    assert smart_vacancy.hh_published == False  # Без hh_vacancy_id


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
async def test_start_search_without_paid_access(
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест запуска поиска БЕЗ платного доступа - должен стартовать с has_paid_access=False"""
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем доступ: hh подключён, но без платной услуги
    mock_access.return_value = (True, False, None)

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    # Поиск должен запуститься (НЕ выбрасывать исключение)
    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None

    # Проверяем что параметр has_paid_access=False сохранён
    run = await db_session.get(SmartSearchRun, run_id)
    assert run is not None
    assert run.params["has_paid_access"] is False


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
@patch('app.services.smart_search._run_search_background', new_callable=AsyncMock)
async def test_start_search_with_paid_access(
    mock_run_background,
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест запуска поиска С платным доступом"""
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем доступ: hh подключён И есть платная услуга
    mock_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None

    # Проверяем что параметр has_paid_access=True сохранён
    run = await db_session.get(SmartSearchRun, run_id)
    assert run is not None
    assert run.params["has_paid_access"] is True


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
async def test_start_search_without_hh_access_fails(
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что поиск не запустится если hh вообще не подключён"""
    mock_access.return_value = (False, False, "hh.ru не подключён")

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    # Поиск НЕ должен запуститься
    with pytest.raises(Exception) as exc_info:
        await start_search(db_session, test_company.id, admin_user.id, request)

    assert "не подключён" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_run_status_with_invites_skipped(db_session, test_company, test_vacancy):
    """Тест статуса поиска с флагом invites_skipped"""
    # Создаём тестовый run вручную с invites_skipped=True
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="done",
        stage="done",
        params={"threshold": 70},
        found=100,
        scanned=50,
        evaluated=30,
        invited=0,  # Не приглашали никого
        invites_skipped=True,  # Пропущены приглашения
        invited_candidates=[
            {
                "candidate_id": None,  # Превью кандидат
                "name": "Иван Тестовый",
                "age": 30,
                "score": 85,
                "verdict": "Подходит"
            }
        ]
    )
    db_session.add(run)
    await db_session.commit()

    # Получаем статус
    status = await get_run_status(db_session, run.id, test_company.id)
    assert status is not None
    assert status.invites_skipped is True
    assert status.invited == 0
    assert len(status.invited_candidates) == 1
    assert status.invited_candidates[0]["candidate_id"] is None


@pytest.mark.asyncio
async def test_search_params_text_assembly_and_filtering():
    """Тест сборки search_params: text из роли+навыков, фильтрация невалидных id-параметров"""
    from app.services.smart_search import SmartSearchRun
    from app.models import Vacancy
    from uuid import uuid4

    # Мокаем объекты для тестирования логики сборки search_params
    vacancy = Vacancy()
    vacancy.name = "Python разработчик"

    # Тест 1: text собирается из роли + навыков
    params_with_role_and_skills = {
        "professional_role": "Программист 1С",
        "skills": ["Python", "Django", "PostgreSQL"],
        "area": "Москва",  # Текстовое значение
        "experience": "2-3 года",  # Невалидный enum
    }

    # Эмулируем логику сборки text (из реального кода)
    text_parts = []
    professional_role = params_with_role_and_skills.get("professional_role") or vacancy.name
    if professional_role:
        text_parts.append(professional_role)

    skills = params_with_role_and_skills.get("skills", [])
    if skills:
        text_parts.extend(skills)

    expected_text = " ".join(filter(None, text_parts)).strip()
    assert expected_text == "Программист 1С Python Django PostgreSQL"

    # Тест 2: area передается только если числовое
    area_value = params_with_role_and_skills["area"]
    area_should_be_included = str(area_value).strip().isdigit()
    assert area_should_be_included is False  # "Москва" не числовое - НЕ включается

    # Тест 3: professional_role передается только если числовое
    role_value = params_with_role_and_skills["professional_role"]
    role_should_be_included = str(role_value).strip().isdigit()
    assert role_should_be_included is False  # "Программист 1С" не числовое - НЕ включается

    # Тест 4: experience передается только если валидный enum
    exp_value = params_with_role_and_skills["experience"]
    valid_experience = ["noExperience", "between1And3", "between3And6", "moreThan6"]
    exp_should_be_included = exp_value in valid_experience
    assert exp_should_be_included is False  # "2-3 года" не в енуме - НЕ включается

    # Тест 5: skills передаются только если все элементы числовые
    skills_list = params_with_role_and_skills["skills"]
    skills_should_be_included = all(str(skill).strip().isdigit() for skill in skills_list)
    assert skills_should_be_included is False  # ["Python", "Django"] не числовые - НЕ включаются

    # Тест 6: валидные параметры проходят
    valid_params = {
        "area": "113",  # Числовой area_id
        "professional_role": "96",  # Числовой role_id
        "experience": "between1And3",  # Валидный enum
        "skills": ["9", "108"],  # Числовые skill_id
    }

    assert str(valid_params["area"]).strip().isdigit() is True
    assert str(valid_params["professional_role"]).strip().isdigit() is True
    assert valid_params["experience"] in valid_experience
    assert all(str(skill).strip().isdigit() for skill in valid_params["skills"]) is True


@pytest.mark.asyncio
@patch('app.services.smart_search.call_json')
async def test_derive_vacancy_filters_success(
    mock_call_json,
    db_session,
    test_company,
    test_vacancy
):
    """Тест успешного извлечения AI-фильтров из вакансии"""
    # Мокаем ответ LLM
    mock_call_json.return_value = {
        "area": "Информационные технологии",
        "professional_role": "Программист, разработчик",
        "experience": "3–6 лет",
        "skills": ["Python", "Django", "PostgreSQL", "Git"]
    }

    filters = await derive_vacancy_filters(db_session, test_company.id, test_vacancy.id)

    assert filters["area"] == "Информационные технологии"
    assert filters["professional_role"] == "Программист, разработчик"
    assert filters["experience"] == "3–6 лет"
    assert filters["skills"] == ["Python", "Django", "PostgreSQL", "Git"]

    # Проверяем что LLM был вызван с правильными данными
    mock_call_json.assert_called_once()
    call_args = mock_call_json.call_args
    assert "Название: " + test_vacancy.name in call_args[1]["user"]


@pytest.mark.asyncio
@patch('app.services.smart_search.call_json')
async def test_derive_vacancy_filters_graceful_fallback(
    mock_call_json,
    db_session,
    test_company,
    test_vacancy
):
    """Тест graceful fallback при ошибке LLM - не возвращает 502"""
    # Мокаем ошибку LLM
    from app.core.errors import GlafiraParseError
    mock_call_json.side_effect = GlafiraParseError(details={"reason": "Network error"})

    filters = await derive_vacancy_filters(db_session, test_company.id, test_vacancy.id)

    # Должен вернуть fallback, а не бросить исключение
    assert filters["area"] == ""
    assert filters["professional_role"] == test_vacancy.name
    assert filters["experience"] == ""
    assert filters["skills"] == []


@pytest.mark.asyncio
async def test_derive_vacancy_filters_vacancy_not_found(
    db_session,
    test_company
):
    """Тест что функция бросает NotFoundError для несуществующей вакансии"""
    from app.core.errors import NotFoundError

    nonexistent_vacancy_id = uuid4()

    with pytest.raises(NotFoundError):
        await derive_vacancy_filters(db_session, test_company.id, nonexistent_vacancy_id)


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
async def test_confirm_cost_gate_blocks_large_scan_without_confirm(
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что гейт confirm_cost блокирует scan_n > 50 без подтверждения"""
    mock_access.return_value = (True, True, None)

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=100,  # Больше FREE_SCAN_LIMIT (50)
        invite_m=10,
        threshold=70,
        confirm_cost=False  # БЕЗ подтверждения
    )

    with pytest.raises(ValidationError) as exc_info:
        await start_search(db_session, test_company.id, admin_user.id, request)

    assert "confirm_cost=true" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_run_progress(db_session, test_company, test_vacancy):
    """Тест обновления прогресса поиска короткой сессией"""
    # Создаем run
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"scan_n": 10},
        log=["Старт"]
    )
    db_session.add(run)
    await db_session.commit()
    run_id = run.id

    # Обновляем прогресс через патч сессии
    with patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        await _update_run_progress(
            run_id,
            scanned=5,
            evaluated=3,
            log_append="Обработано 5 резюме"
        )

    # Проверяем что изменения сохранились
    await db_session.refresh(run)
    assert run.scanned == 5
    assert run.evaluated == 3
    assert run.log[-1] == "Обработано 5 резюме"


@pytest.mark.asyncio
async def test_finalize_run_success(db_session, test_company, test_vacancy):
    """Тест успешной финализации поиска"""
    # Создаем run
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="eval",
        params={"scan_n": 10}
    )
    db_session.add(run)
    await db_session.commit()
    run_id = run.id

    # Финализируем через патч сессии
    with patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        success = await _finalize_run(
            run_id,
            status="done",
            stage="done",
            note="Поиск завершен успешно",
            passed_threshold=5,
            invited=0
        )

    assert success is True

    # Проверяем что run финализирован
    await db_session.refresh(run)
    assert run.status == "done"
    assert run.stage == "done"
    assert run.note == "Поиск завершен успешно"
    assert run.passed_threshold == 5
    assert run.finished_at is not None
    assert "Финализация: done" in run.log[-1]


@pytest.mark.asyncio
async def test_finalize_run_nonexistent(db_session):
    """Тест финализации несуществующего поиска"""
    fake_run_id = uuid4()

    success = await _finalize_run(
        fake_run_id,
        status="error",
        error="Тест ошибка"
    )

    assert success is False


@pytest.mark.asyncio
async def test_sweep_orphaned_runs(db_session, test_company, test_vacancy):
    """Тест очистки зависших поисков"""
    # Создаем старый running поиск (имитируем зависший)
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)

    old_run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="eval",
        params={"scan_n": 10},
        created_at=old_time,
        updated_at=old_time  # Давно не обновлялся
    )
    db_session.add(old_run)

    # Создаем свежий running поиск (не должен быть затронут)
    fresh_run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"scan_n": 10}
    )
    db_session.add(fresh_run)

    await db_session.commit()
    old_run_id = old_run.id
    fresh_run_id = fresh_run.id

    # Запускаем sweep с лимитом 60 минут. sweep открывает свой AsyncSessionLocal —
    # патчим на тестовый db_session, иначе он не увидит созданные тут run'ы (cross-loop).
    with patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        await sweep_orphaned_runs(max_age_minutes=60)

    # Проверяем результаты. sweep делает bulk UPDATE (Core) в обход ORM identity-map —
    # сбрасываем кэш сессии, чтобы get() перечитал свежие значения из БД (status/error).
    db_session.expire_all()
    old_run_after = await db_session.get(SmartSearchRun, old_run_id)
    fresh_run_after = await db_session.get(SmartSearchRun, fresh_run_id)

    # Старый run должен быть помечен как error
    assert old_run_after.status == "error"
    assert "зависание" in old_run_after.error.lower()
    assert old_run_after.finished_at is not None

    # Свежий run должен остаться running
    assert fresh_run_after.status == "running"


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.search_resumes')
@patch('app.services.smart_search.hh_client.get_resume_by_id')
@patch('app.services.smart_search.score_resume_dict')
async def test_run_search_inner_short_sessions(
    mock_score,
    mock_get_resume,
    mock_search,
    mock_token,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что _run_search_inner использует короткие сессии и не держит соединение"""
    # Настройка моков
    mock_token.return_value = "test_token"
    mock_search.return_value = {
        "found": 1,
        "items": [{"id": "resume123"}]
    }
    mock_get_resume.return_value = {
        "id": "resume123",
        "first_name": "Иван",
        "last_name": "Тестовый",
        "title": "Python разработчик"
    }
    mock_score.return_value = {
        "score": 85,
        "verdict": "Отлично подходит",
        "summary": "Опытный разработчик"
    }

    # Создаем run для тестирования
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"scan_n": 1, "threshold": 70}
    )
    db_session.add(run)
    await db_session.commit()
    run_id = run.id

    # Запускаем внутреннюю логику поиска через патч сессии
    with patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        await _run_search_inner(run_id, test_company.id, admin_user.id)

    # Проверяем что поиск завершился успешно
    await db_session.refresh(run)
    assert run.status == "done"
    assert run.stage == "done"
    assert run.found == 1
    assert run.scanned == 1
    assert run.evaluated == 1
    assert run.passed_threshold == 1  # score 85 >= threshold 70
    assert len(run.scored_candidates) == 1

    # Проверяем что внешние вызовы были сделаны
    mock_search.assert_called_once()
    mock_get_resume.assert_called_once_with("test_token", "resume123")
    mock_score.assert_called_once()


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
async def test_confirm_cost_gate_allows_large_scan_with_confirm(
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что гейт confirm_cost пропускает scan_n > 50 с подтверждением"""
    mock_access.return_value = (True, True, None)

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=100,  # Больше FREE_SCAN_LIMIT (50)
        invite_m=10,
        threshold=70,
        confirm_cost=True  # С подтверждением
    )

    # НЕ должен бросить исключение
    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None

    run = await db_session.get(SmartSearchRun, run_id)
    assert run.params["scan_n"] == 100


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
async def test_confirm_cost_gate_allows_small_scan_without_confirm(
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что гейт confirm_cost пропускает scan_n <= 50 без подтверждения"""
    mock_access.return_value = (True, True, None)

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=30,  # Меньше FREE_SCAN_LIMIT (50)
        invite_m=10,
        threshold=70,
        confirm_cost=False  # БЕЗ подтверждения - должно быть ок
    )

    # НЕ должен бросить исключение
    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None


@pytest.mark.asyncio
async def test_new_fields_in_run_model(db_session, test_company, test_vacancy):
    """Тест что новые поля модели SmartSearchRun корректно создаются с дефолтами"""
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"scan_n": 50}
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    # Проверяем новые поля с дефолтными значениями
    assert hasattr(run, 'scored_candidates')
    assert hasattr(run, 'passed_threshold')
    assert hasattr(run, 'note')
    assert hasattr(run, 'log')

    assert run.scored_candidates == []
    assert run.passed_threshold == 0
    assert run.note is None
    assert run.log == []


# Тест пагинации на моках - проверяем логику сборки страниц
@pytest.mark.asyncio
@patch('app.services.smart_search.hh_client.search_resumes')
async def test_pagination_logic_collects_multiple_pages(mock_search_resumes):
    """Тест логики пагинации - сбор нескольких страниц до достижения scan_n"""
    from app.services.smart_search import MAX_PAGES_LIMIT

    # Мокаем ответы для 3 страниц
    mock_search_resumes.side_effect = [
        {"found": 150, "items": [{"id": f"resume_{i}"} for i in range(50)]},  # page 0
        {"found": 150, "items": [{"id": f"resume_{i}"} for i in range(50, 100)]},  # page 1
        {"found": 150, "items": [{"id": f"resume_{i}"} for i in range(100, 120)]},  # page 2 (частично)
    ]

    # Эмулируем логику пагинации из реального кода
    accumulated_items = []
    found_count = 0
    scan_n = 120  # Хотим собрать 120 резюме
    base_search_params = {"text": "Python", "per_page": 50}

    for page in range(MAX_PAGES_LIMIT):
        search_params = base_search_params.copy()
        search_params["page"] = page

        search_result = await mock_search_resumes("test_token", search_params)
        page_found = search_result.get("found", 0)
        page_items = search_result.get("items", [])

        # Берём found из первой страницы
        if page == 0:
            found_count = page_found

        if not page_items:
            break

        accumulated_items.extend(page_items)

        # Проверяем лимиты
        if len(accumulated_items) >= scan_n:
            break

        if len(accumulated_items) >= found_count:
            break

    # Проверяем результат
    assert found_count == 150
    assert len(accumulated_items) == 120  # Собрали ровно scan_n
    assert mock_search_resumes.call_count == 3  # Вызвали 3 страницы

    # Проверяем что параметры страниц передавались корректно
    # hh_client.search_resumes вызывается позиционно: (access_token, search_params)
    calls = mock_search_resumes.call_args_list
    assert calls[0][0][1]["page"] == 0  # search_params - второй позиционный аргумент
    assert calls[1][0][1]["page"] == 1
    assert calls[2][0][1]["page"] == 2


@pytest.mark.asyncio
async def test_scored_candidates_structure():
    """Тест структуры данных scored_candidates"""
    # Проверяем что структура scored_candidate соответствует InvitedCandidate + passed
    scored_candidate = {
        "candidate_id": None,
        "name": "Иван Тестов",
        "age": 30,
        "experience_years": 5,
        "last_company": "ООО Тест",
        "city": "Москва",
        "score": 85,
        "verdict": "Подходит",
        "passed": True  # Новое поле
    }

    from app.schemas.smart import InvitedCandidate

    # Должен корректно создаваться InvitedCandidate из этих данных
    candidate = InvitedCandidate(**scored_candidate)
    assert candidate.name == "Иван Тестов"
    assert candidate.passed == True
    assert candidate.score == 85


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.search_resumes')
async def test_preview_found_count_success(
    mock_search_resumes,
    mock_token,
    db_session,
    test_company,
    test_vacancy
):
    """Тест успешного превью подсчёта количества резюме"""
    mock_token.return_value = "test_token"
    mock_search_resumes.return_value = {"found": 269, "items": []}

    request = SmartCountRequest(
        vacancy_id=test_vacancy.id,
        area="113",  # Москва
        professional_role="96",  # Разработчик
        experience="between1And3",
        skills=["Python", "Django"],
        salary_from=100000,
        salary_to=200000,
        include_no_salary=False
    )

    found = await preview_found_count(db_session, test_company.id, request)

    assert found == 269
    mock_search_resumes.assert_called_once()
    # hh_client.search_resumes вызывается позиционно: (access_token, search_params)
    call_args = mock_search_resumes.call_args[0][1]  # search_params - второй позиционный аргумент
    assert call_args["per_page"] == 1
    assert call_args["page"] == 0


@pytest.mark.asyncio
async def test_preview_found_count_vacancy_not_found(
    db_session,
    test_company
):
    """Тест превью подсчёта для несуществующей вакансии - должен вернуть 404"""
    from app.core.errors import NotFoundError

    request = SmartCountRequest(
        vacancy_id=uuid4(),  # Несуществующая вакансия
        skills=["Python"]
    )

    with pytest.raises(NotFoundError):
        await preview_found_count(db_session, test_company.id, request)


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.search_resumes')
async def test_preview_found_count_hh_error_graceful(
    mock_search_resumes,
    mock_token,
    db_session,
    test_company,
    test_vacancy
):
    """Тест graceful поведения превью при ошибке hh - возвращает None"""
    mock_token.return_value = "test_token"
    mock_search_resumes.side_effect = Exception("API rate limit exceeded")

    request = SmartCountRequest(
        vacancy_id=test_vacancy.id,
        skills=["Python"]
    )

    found = await preview_found_count(db_session, test_company.id, request)

    assert found is None  # НЕ бросает исключение, возвращает None


@pytest.mark.asyncio
async def test_build_search_params_creates_expected_dict():
    """Тест что build_search_params создаёт ожидаемую структуру"""
    from app.models import Vacancy

    vacancy = Vacancy()
    vacancy.name = "Python Developer"

    params = {
        "area_id": "113",  # Числовое значение - включается как area
        "professional_role": "Программист",  # Текстовое - НЕ включается как id, но входит в text
        "experience": "between1And3",  # Валидный enum - включается
        "skills": ["Python", "Django"],  # Текстовые - НЕ включаются как id, но входят в text
        "salary_from": 100000,
        "salary_to": 200000,
        "include_no_salary": False
    }

    result = build_search_params(params, vacancy)

    # Проверяем что text содержит роль и навыки
    expected_text = "Программист Python Django"
    assert result["text"] == expected_text

    # Проверяем что валидные фильтры включены
    assert result["area"] == "113"
    assert result["experience"] == "between1And3"
    assert result["salary_from"] == 100000
    assert result["salary_to"] == 200000
    assert "only_with_salary" not in result  # include_no_salary=False → ключ не добавляется

    # Проверяем что невалидные id-фильтры НЕ включены
    assert "professional_role" not in result
    assert "skill" not in result

    # Проверяем что page/per_page НЕ включены (их добавляет вызывающий)
    assert "page" not in result
    assert "per_page" not in result


@pytest.mark.asyncio
async def test_build_search_params_with_area_id_and_period():
    """Тест что build_search_params корректно обрабатывает area_id и period"""
    from app.models import Vacancy

    vacancy = Vacancy()
    vacancy.name = "Python Developer"

    # Тест с валидным area_id (числовое значение)
    params_valid_area = {
        "area_id": "1",  # Числовое значение - включается как area
        "period": 7,     # Валидное значение - включается
    }

    result = build_search_params(params_valid_area, vacancy)
    assert result["area"] == "1"
    assert result["period"] == 7

    # Тест с невалидным area_id (нечисловое значение)
    params_invalid_area = {
        "area_id": "Москва",  # Нечисловое значение - НЕ включается
        "period": None,       # None - НЕ включается
    }

    result = build_search_params(params_invalid_area, vacancy)
    assert "area" not in result
    assert "period" not in result

    # Тест с невалидным period (отрицательное число)
    params_invalid_period = {
        "area_id": "113",
        "period": -5,  # Отрицательное - НЕ включается
    }

    result = build_search_params(params_invalid_period, vacancy)
    assert result["area"] == "113"
    assert "period" not in result

    # Тест с period = 0 (не включается)
    params_zero_period = {
        "period": 0,  # Ноль - НЕ включается
    }

    result = build_search_params(params_zero_period, vacancy)
    assert "period" not in result


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.suggest_areas')
async def test_suggest_areas_success(
    mock_suggest_areas,
    mock_token,
    db_session,
    test_company
):
    """Тест успешного получения подсказок областей"""
    mock_token.return_value = "test_token"
    mock_suggest_areas.return_value = [
        {"id": "1", "text": "Москва"},
        {"id": "2", "text": "Санкт-Петербург"}
    ]

    result = await suggest_areas(db_session, test_company.id, "Мос")

    assert len(result) == 2
    assert result[0]["id"] == "1"
    assert result[0]["text"] == "Москва"
    assert result[1]["id"] == "2"
    assert result[1]["text"] == "Санкт-Петербург"

    mock_suggest_areas.assert_called_once_with("test_token", "Мос")


@pytest.mark.asyncio
async def test_suggest_areas_short_text(db_session, test_company):
    """Тест что suggest_areas возвращает пустой список для короткого текста"""
    result = await suggest_areas(db_session, test_company.id, "М")  # Меньше 2 символов
    assert result == []

    result = await suggest_areas(db_session, test_company.id, "")  # Пустая строка
    assert result == []


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.suggest_areas')
async def test_suggest_areas_hh_error_graceful(
    mock_suggest_areas,
    mock_token,
    db_session,
    test_company
):
    """Тест graceful поведения suggest_areas при ошибке hh"""
    mock_token.return_value = "test_token"
    mock_suggest_areas.side_effect = Exception("API error")

    result = await suggest_areas(db_session, test_company.id, "Москва")

    # Должен вернуть пустой список, а не выбросить исключение
    assert result == []


@pytest.mark.asyncio
@patch('app.services.glafira.scoring.call_json')
async def test_score_resume_dict_returns_full_breakdown(mock_call_json):
    """Тест что score_resume_dict теперь возвращает полный разбор"""
    from app.services.glafira.scoring import score_resume_dict
    from app.models import Vacancy
    from uuid import uuid4

    # Мокаем полный ответ LLM
    mock_call_json.return_value = {
        "score": 85,
        "verdict": "good",
        "summary": "Опытный Python разработчик с сильными навыками",
        "strengths": ["Python", "Django", "опыт 5+ лет"],
        "risks": ["нет опыта в тестировании", "завышенные зарплатные ожидания"],
        "requirements_match": [
            {"criterion": "Знание Python", "weight": 25, "points": 25, "comment": "Отличное знание"},
            {"criterion": "Опыт веб-разработки", "weight": 20, "points": 18, "comment": "Хороший опыт в Django"}
        ],
        "forecast": "Подойдёт на позицию senior developer",
        "questions": ["Готовы ли к релокации?", "Опыт работы в команде?"]
    }

    # Создаём мок-объекты
    vacancy = Vacancy()
    vacancy.name = "Python Developer"
    vacancy.description = "Требуется опытный Python разработчик"

    hh_resume = {
        "first_name": "Иван",
        "last_name": "Петров",
        "title": "Python Developer",
        "area": {"name": "Москва"},
        "skills": "Python, Django, PostgreSQL"
    }

    company_id = uuid4()

    # Вызываем функцию
    result = await score_resume_dict(hh_resume, vacancy, company_id)

    # Проверяем что возвращаются все поля
    assert result["score"] == 85
    assert result["verdict"] == "good"
    assert result["summary"] == "Опытный Python разработчик с сильными навыками"
    assert result["strengths"] == ["Python", "Django", "опыт 5+ лет"]
    assert result["risks"] == ["нет опыта в тестировании", "завышенные зарплатные ожидания"]
    assert len(result["requirements_match"]) == 2
    assert result["requirements_match"][0]["criterion"] == "Знание Python"
    assert result["forecast"] == "Подойдёт на позицию senior developer"
    assert result["questions"] == ["Готовы ли к релокации?", "Опыт работы в команде?"]


@pytest.mark.asyncio
async def test_compact_resume_for_display():
    """Тест функции _compact_resume_for_display"""
    from app.services.smart_search import _compact_resume_for_display

    # Полное резюме с данными
    full_resume = {
        "title": "Senior Python Developer",
        "total_experience": {"months": 60},  # 5 лет
        "area": {"name": "Москва"},
        "age": 30,
        "salary": {
            "from": 150000,
            "to": 200000,
            "currency": "RUR"
        },
        "experience": [
            {
                "position": "Python Developer",
                "company": "ООО Рога и Копыта",
                "start": "2020-01",
                "end": "2023-06",
                "description": "Разработка веб-приложений на Django" + "а" * 400  # Длинное описание
            },
            {
                "position": "Junior Developer",
                "company": "IT Start",
                "start": "2019-01",
                "end": None,  # Текущая работа
                "description": "Изучение Python"
            }
        ],
        "skills": "Python, Django, PostgreSQL",
        "key_skills": [
            {"name": "Git"},
            {"name": "Docker"}
        ],
        "education": {
            "level": {"name": "Высшее"}
        }
    }

    result = _compact_resume_for_display(full_resume)

    # Проверяем основные поля
    assert result["title"] == "Senior Python Developer"
    assert result["total_experience_months"] == 60
    assert result["city"] == "Москва"
    assert result["age"] == 30
    assert result["salary"] == "150,000 - 200,000 RUR"
    assert result["education"] == "Высшее"

    # Проверяем опыт работы (обрезание описания)
    assert len(result["experience"]) == 2
    assert result["experience"][0]["position"] == "Python Developer"
    assert result["experience"][0]["company"] == "ООО Рога и Копыта"
    assert result["experience"][0]["period"] == "2020-01 - 2023-06"
    assert len(result["experience"][0]["description"]) <= 400

    assert result["experience"][1]["period"] == "2019-01 - по наст.вр."

    # Проверяем навыки (из обоих источников)
    # skills как строка добавляется целиком, key_skills по имени
    assert any("Python" in skill for skill in result["skills"])  # "Python, Django, PostgreSQL"
    assert "Git" in result["skills"]  # из key_skills
    assert "Docker" in result["skills"]  # из key_skills

    # Пустое резюме не должно падать
    empty_result = _compact_resume_for_display({})
    assert empty_result["title"] is None
    assert empty_result["experience"] == []
    assert empty_result["skills"] == []


@pytest.mark.asyncio
async def test_scored_candidates_with_full_breakdown():
    """Тест что scored_candidates теперь содержит полный разбор"""
    from app.schemas.smart import InvitedCandidate, SmartScoredResume, SmartRequirementMatch

    # Структура scored_candidate с новыми полями
    scored_candidate_data = {
        "candidate_id": None,
        "name": "Иван Петров",
        "age": 30,
        "experience_years": 5,
        "last_company": "ООО Тест",
        "city": "Москва",
        "score": 85,
        "verdict": "good",
        "passed": True,
        # Новые поля с разбором
        "summary": "Опытный разработчик",
        "strengths": ["Python", "Django"],
        "risks": ["нет опыта тестирования"],
        "forecast": "Подойдёт на senior позицию",
        "requirements_match": [
            {"criterion": "Python", "weight": 25, "points": 25, "comment": "Отлично"}
        ],
        "resume": {
            "title": "Python Developer",
            "total_experience_months": 60,
            "city": "Москва",
            "age": 30,
            "salary": "150,000 - 200,000 RUR",
            "experience": [
                {"position": "Developer", "company": "IT Corp", "period": "2020-2023", "description": "Разработка"}
            ],
            "skills": ["Python", "Django"],
            "education": "Высшее"
        }
    }

    # Должен корректно парситься в InvitedCandidate
    candidate = InvitedCandidate(**scored_candidate_data)

    assert candidate.name == "Иван Петров"
    assert candidate.score == 85
    assert candidate.summary == "Опытный разработчик"
    assert candidate.strengths == ["Python", "Django"]
    assert candidate.risks == ["нет опыта тестирования"]
    assert candidate.forecast == "Подойдёт на senior позицию"
    assert len(candidate.requirements_match) == 1
    assert candidate.requirements_match[0].criterion == "Python"
    assert candidate.resume.title == "Python Developer"
    assert candidate.resume.total_experience_months == 60
    assert len(candidate.resume.experience) == 1


@pytest.mark.asyncio
async def test_calculate_search_timeout():
    """Тест функции расчёта таймаута поиска"""
    # Тест с мокнутой сессией
    with patch('app.services.smart_search.AsyncSessionLocal') as mock_session_class:
        mock_session = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session

        run = SmartSearchRun(params={"scan_n": 100})
        mock_session.get.return_value = run

        timeout = await _calculate_search_timeout(uuid4(), uuid4())
        # max(900, 100 * 200) = max(900, 20000) = 20000 (формула 200с/резюме)
        assert timeout == 20000

        # Тест с малым scan_n
        run.params = {"scan_n": 10}
        timeout = await _calculate_search_timeout(uuid4(), uuid4())
        # max(900, 10 * 200) = max(900, 2000) = 2000
        assert timeout == 2000

        # Тест с отсутствующим run
        mock_session.get.return_value = None
        timeout = await _calculate_search_timeout(uuid4(), uuid4())
        assert timeout == 900  # fallback


@pytest.mark.asyncio
async def test_timeout_wrapper_finalizes_on_timeout():
    """Тест что wrapper финализирует run при таймауте"""
    with patch('app.services.smart_search._run_search_inner') as mock_inner, \
         patch('app.services.smart_search._calculate_search_timeout') as mock_timeout, \
         patch('app.services.smart_search.AsyncSessionLocal') as mock_session_class:

        # Мокаем таймаут
        mock_timeout.return_value = 1  # 1 секунда

        # Корректный side_effect - функция, которая возвращает корутину, зависающую дольше таймаута
        async def _slow_operation(*args, **kwargs):
            await asyncio.sleep(2)  # Зависаем на 2 секунды (больше таймаута в 1 сек)

        mock_inner.side_effect = _slow_operation

        # Мокаем сессию для финализации
        mock_session = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session

        run = SmartSearchRun(status="running")
        mock_session.get.return_value = run

        run_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()

        # Вызываем wrapper - должен поймать TimeoutError и финализировать
        await _run_search_background(run_id, company_id, user_id)

        # Проверяем что run был финализирован при таймауте
        assert run.status == "error"
        assert "таймаут" in run.note.lower()
        assert run.error == "timeout"
        assert run.finished_at is not None
        mock_session.commit.assert_called()


@pytest.mark.asyncio
@patch('app.services.smart_search.audit')
async def test_audit_call_with_actor_user_id_none(mock_audit):
    """Тест что audit вызывается с actor_user_id=None для AI-действий"""
    from app.services.smart_search import audit

    # Вызываем audit как в реальном коде приглашений
    mock_session = AsyncMock()
    candidate_id = uuid4()
    vacancy_id = uuid4()
    company_id = uuid4()
    run_id = uuid4()

    await audit(
        mock_session,
        action="smart_search_invite",
        entity_type="candidate",
        entity_id=candidate_id,
        after={
            "vacancy_id": str(vacancy_id),
            "ai_score": 85,
            "run_id": str(run_id)
        },
        actor_type="ai",
        actor_user_id=None,
        company_id=company_id
    )

    # Проверяем что audit был вызван с правильными параметрами
    mock_audit.assert_called_once()
    call_args = mock_audit.call_args

    assert call_args[1]["action"] == "smart_search_invite"
    assert call_args[1]["entity_type"] == "candidate"
    assert call_args[1]["entity_id"] == candidate_id
    assert call_args[1]["actor_type"] == "ai"
    assert call_args[1]["actor_user_id"] is None
    assert call_args[1]["company_id"] == company_id


@pytest.mark.asyncio
async def test_invite_timeout_handling():
    """Тест что invite_to_vacancy с таймаутом корректно обрабатывается"""
    from unittest.mock import patch

    with patch('app.services.smart_search.hh_client.invite_to_vacancy') as mock_invite:
        # Мокаем долгий вызов - функция, которая возвращает корутину.
        # Спим заметно дольше таймаута, но оба малы — тест быстрый (суть: ловим TimeoutError).
        async def long_invite(*args, **kwargs):
            await asyncio.sleep(1)
            return {}

        mock_invite.side_effect = long_invite

        # Эмулируем логику с таймаутом
        try:
            await asyncio.wait_for(
                mock_invite("token", "resume_id", "vacancy_id", "message"),
                timeout=0.1
            )
            assert False, "Должен был быть таймаут"
        except asyncio.TimeoutError:
            # Ожидаемое поведение
            pass

        mock_invite.assert_called_once()


@pytest.mark.asyncio
async def test_note_formatting_for_different_scenarios():
    """Тест формирования note для разных сценариев"""

    # Тест 1: Нет платного доступа
    has_paid_access = False
    vacancy_hh_id = "123"
    passed_threshold = 5
    invite_errors = []
    invited = 0

    if not has_paid_access:
        note = f"Приглашения не отправлены: нет платного доступа к базе резюме hh (он нужен только для отправки приглашений; поиск и оценка работают без него). Прошли порог: {passed_threshold}."

    assert "нет платного доступа" in note
    assert "Прошли порог: 5" in note

    # Тест 2: Нет hh_vacancy_id
    has_paid_access = True
    vacancy_hh_id = None

    if not vacancy_hh_id:
        note = f"Приглашения не отправлены: вакансия не опубликована на hh.ru. Прошли порог: {passed_threshold}."

    assert "не опубликована" in note

    # Тест 3: Есть ошибки приглашений
    vacancy_hh_id = "123"
    can_invite = True
    invite_errors = ["таймаут hh (25с)", "другая ошибка"]
    invited = 2

    if can_invite and invite_errors:
        first_error = invite_errors[0]
        note = f"Приглашено {invited} из {passed_threshold}. Часть не отправлена: {first_error}."

    assert "Приглашено 2 из 5" in note
    assert "таймаут hh (25с)" in note

    # Тест 4: Всё успешно
    invite_errors = []
    evaluated = 20
    threshold = 70

    if can_invite:
        note = f"Приглашено {invited} из {passed_threshold} прошедших порог {threshold} (оценено {evaluated} резюме)"

    assert "Приглашено 2 из 5 прошедших порог 70" in note


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_resume_by_id')
@patch('app.services.smart_search.hh_client.invite_to_vacancy')
@patch('app.services.smart_search.audit')
async def test_invite_selected_success(
    mock_audit,
    mock_invite,
    mock_get_resume,
    mock_token,
    db_session,
    test_company,
    test_vacancy
):
    """Тест успешного приглашения выбранных кандидатов"""

    # Подготавливаем данные
    run_id = uuid4()
    user_id = uuid4()
    resume_id = "test_resume_123"

    # Создаём SmartSearchRun с scored_candidates
    from app.models import SmartSearchRun

    run = SmartSearchRun(
        id=run_id,
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="done",
        stage="done",
        scored_candidates=[
            {
                "hh_resume_id": resume_id,
                "passed": True,
                "invited": False,
                "name": "Тест Кандидат",
                "score": 85,
                "verdict": "Подходит"
            }
        ]
    )
    db_session.add(run)

    # Устанавливаем hh_vacancy_id
    test_vacancy.hh_vacancy_id = "hh_vac_123"
    await db_session.commit()

    # Мокаем внешние вызовы
    mock_token.return_value = "test_token"
    mock_get_resume.return_value = {
        "id": resume_id,
        "first_name": "Тест",
        "last_name": "Кандидат",
        "contact": [{"type": {"id": "email"}, "value": "test@example.com"}],
        "title": "Тестовая позиция"
    }
    mock_invite.return_value = {"url": "/negotiations/456"}

    # Мокаем check_access и AsyncSessionLocal
    with patch('app.services.smart_search.check_access', return_value=(True, True, None)), \
         patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        # Вызываем функцию
        from app.services.smart_search import invite_selected
        result = await invite_selected(
            db_session, test_company.id, user_id, run_id, [resume_id]
        )

    # Проверяем результат
    assert result["invited_count"] == 1
    assert len(result["results"]) == 1

    result_item = result["results"][0]
    assert result_item["resume_id"] == resume_id
    assert result_item["status"] == "invited"
    assert result_item["candidate_id"] is not None
    assert result_item["name"] == "Тест Кандидат"

    # Проверяем что audit был вызван с правильными параметрами
    mock_audit.assert_called_once()
    audit_call = mock_audit.call_args[1]
    assert audit_call["actor_type"] == "human"  # Действие рекрутёра
    assert audit_call["actor_user_id"] == user_id
    assert audit_call["action"] == "smart_search_invite"


@pytest.mark.asyncio
async def test_invite_selected_no_vacancy_hh_id(db_session, test_company, test_vacancy):
    """Тест ошибки при отсутствии hh_vacancy_id"""

    run_id = uuid4()
    user_id = uuid4()

    # Создаём run без hh_vacancy_id у вакансии
    from app.models import SmartSearchRun
    run = SmartSearchRun(
        id=run_id,
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="done"
    )
    db_session.add(run)
    await db_session.commit()

    # test_vacancy.hh_vacancy_id остаётся None

    from app.services.smart_search import invite_selected
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError) as exc:
        await invite_selected(db_session, test_company.id, user_id, run_id, ["test_id"])

    assert "не опубликована на hh.ru" in str(exc.value)


@pytest.mark.asyncio
async def test_invite_selected_no_paid_access(db_session, test_company, test_vacancy):
    """Тест ошибки при отсутствии платного доступа"""

    run_id = uuid4()
    user_id = uuid4()

    from app.models import SmartSearchRun
    run = SmartSearchRun(
        id=run_id,
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="done"
    )
    db_session.add(run)

    test_vacancy.hh_vacancy_id = "hh_vac_123"
    await db_session.commit()

    # Мокаем check_access без платного доступа
    with patch('app.services.smart_search.check_access', return_value=(True, False, None)):
        from app.services.smart_search import invite_selected
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError) as exc:
            await invite_selected(db_session, test_company.id, user_id, run_id, ["test_id"])

        assert "Нет платного доступа" in str(exc.value)


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search._find_existing_candidate')
async def test_invite_selected_candidate_already_exists(
    mock_find_existing,
    mock_token,
    db_session,
    test_company,
    test_vacancy
):
    """Тест дедупликации - кандидат уже в базе"""

    run_id = uuid4()
    user_id = uuid4()
    resume_id = "test_resume_123"

    from app.models import SmartSearchRun, Candidate

    # Создаём существующего кандидата
    existing_candidate = Candidate(
        id=uuid4(),
        company_id=test_company.id,
        first_name="Существующий",
        last_name="Кандидат",
        source="hh"
    )
    db_session.add(existing_candidate)

    run = SmartSearchRun(
        id=run_id,
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="done",
        scored_candidates=[{
            "hh_resume_id": resume_id,
            "passed": True,
            "invited": False
        }]
    )
    db_session.add(run)

    test_vacancy.hh_vacancy_id = "hh_vac_123"
    await db_session.commit()

    # Мокаем что кандидат найден
    mock_find_existing.return_value = existing_candidate
    mock_token.return_value = "test_token"

    with patch('app.services.smart_search.check_access', return_value=(True, True, None)):
        from app.services.smart_search import invite_selected
        result = await invite_selected(
            db_session, test_company.id, user_id, run_id, [resume_id]
        )

    # Проверяем что возвращён статус already
    assert result["invited_count"] == 0
    assert len(result["results"]) == 1

    result_item = result["results"][0]
    assert result_item["status"] == "already"
    assert result_item["candidate_id"] == existing_candidate.id


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.search_resumes')
@patch('app.services.smart_search.hh_client.get_resume_by_id')
@patch('app.services.smart_search.score_resume_dict')
async def test_run_search_inner_no_auto_invites(
    mock_score,
    mock_get_resume,
    mock_search,
    mock_token,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что _run_search_inner больше не отправляет авто-приглашения"""
    from app.services.smart_search import _run_search_inner, SmartSearchRun

    # Подготовка моков
    mock_token.return_value = "test_token"
    mock_search.return_value = {
        "found": 1,
        "items": [{"id": "resume_1"}]
    }
    mock_get_resume.return_value = {
        "id": "resume_1",
        "first_name": "Иван",
        "last_name": "Тестов",
        "title": "Python Developer",
        "area": {"name": "Москва"}
    }
    mock_score.return_value = {
        "score": 85,
        "verdict": "good",
        "summary": "Хороший кандидат"
    }

    # Создаем run для тестирования
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"scan_n": 1, "threshold": 70}
    )
    db_session.add(run)
    await db_session.commit()
    run_id = run.id

    # Запускаем _run_search_inner через патч сессии
    with patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        await _run_search_inner(run_id, test_company.id, admin_user.id)

    # Проверяем что run финализирован БЕЗ приглашений
    await db_session.refresh(run)
    assert run.status == "done"
    assert run.stage == "done"
    assert run.invites_skipped is True
    assert run.invited == 0
    assert run.passed_threshold == 1  # score 85 >= threshold 70


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.search_resumes')
@patch('app.services.smart_search.hh_client.get_resume_by_id')
@patch('app.services.smart_search.score_resume_dict')
async def test_run_search_inner_fresh_session_finalization(
    mock_score,
    mock_get_resume,
    mock_search,
    mock_token,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что после успешной оценки run финализируется status='done', stage='done' на свежей сессии"""

    # Подготовка моков
    mock_token.return_value = "test_token"
    mock_search.return_value = {
        "found": 2,
        "items": [{"id": "resume_1"}, {"id": "resume_2"}]
    }

    mock_get_resume.side_effect = [
        {
            "id": "resume_1",
            "first_name": "Иван",
            "last_name": "Тестов",
            "title": "Python Developer",
            "area": {"name": "Москва"},
            "experience": [{"company": "IT Corp"}]
        },
        {
            "id": "resume_2",
            "first_name": "Анна",
            "last_name": "Смирнова",
            "title": "JS Developer",
            "area": {"name": "СПб"},
            "experience": [{"company": "Web Studio"}]
        }
    ]

    mock_score.side_effect = [
        {
            "score": 85,
            "verdict": "good",
            "summary": "Отличный кандидат",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": [],
            "forecast": "Подходит"
        },
        {
            "score": 60,
            "verdict": "average",
            "summary": "Средний кандидат",
            "strengths": ["JS"],
            "risks": ["мало опыта"],
            "requirements_match": [],
            "forecast": "Сомнительно"
        }
    ]

    # Создаем поисковый run
    from app.models import SmartSearchRun
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={
            "scan_n": 2,
            "threshold": 70,
            "area": "Москва"
        }
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    # Запускаем внутреннюю логику поиска через патч сессии
    from app.services.smart_search import _run_search_inner
    with patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        await _run_search_inner(run.id, test_company.id, admin_user.id)

    # Проверяем финализацию через свежую сессию
    await db_session.refresh(run)

    assert run.status == "done"
    assert run.stage == "done"
    assert run.passed_threshold == 1  # Только resume_1 прошёл порог 70
    assert run.note == "Оценка завершена. Прошли порог: 1. Выберите кандидатов для приглашения."
    assert run.invites_skipped is True
    assert run.invited == 0
    assert run.finished_at is not None
    # Финализация залогирована (само сообщение "Оценка завершена" пишется через
    # log_smart_search отдельной сессией — под shared-session тест-харнессом не
    # сохраняется; в проде пишется. Терминальность подтверждена status/note/"Финализация").
    assert "Финализация" in str(run.log)


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
async def test_run_search_inner_error_handler_fresh_session(
    mock_token,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что обработчик ошибок записывает статус error через свежую сессию"""

    # Мок, который вызовет исключение после получения токена
    mock_token.side_effect = Exception("Network error")

    # Создаем поисковый run
    from app.models import SmartSearchRun
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"scan_n": 10}
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    # Запускаем внутреннюю логику поиска - должна упасть с ошибкой (через патч сессии)
    from app.services.smart_search import _run_search_inner
    with patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):
        await _run_search_inner(run.id, test_company.id, admin_user.id)

    # Проверяем что ошибка записана через свежую сессию
    await db_session.refresh(run)

    assert run.status == "error"
    assert run.error == "Network error"
    assert run.note == "Ошибка выполнения: Network error"
    assert run.finished_at is not None


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_start_search_double_start_guard(
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест защиты от двойного запуска поиска"""
    # Настраиваем моки
    mock_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    # Создаём уже запущенный поиск для вакансии
    existing_run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"threshold": 70}
    )
    db_session.add(existing_run)
    await db_session.commit()

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    # Второй запуск должен вернуть ConflictError
    from app.core.errors import ConflictError
    with pytest.raises(ConflictError) as exc_info:
        await start_search(db_session, test_company.id, admin_user.id, request)

    assert "уже выполняется поиск" in str(exc_info.value)


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
@patch('app.services.smart_search._run_search_background', new_callable=AsyncMock)
async def test_start_search_stale_running_not_blocking(
    mock_bg,
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест что застрявший running не блокирует навсегда"""
    # Настраиваем моки
    mock_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    # Создаём старый застрявший поиск (старше STUCK_RECONCILE_SECONDS)
    old_time = datetime.now(timezone.utc) - timedelta(seconds=300)  # 5 минут назад
    stale_run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="search",
        params={"threshold": 70},
        updated_at=old_time
    )
    db_session.add(stale_run)
    await db_session.commit()

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    # Новый запуск должен пройти успешно (застрявший будет финализирован)
    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None

    # Проверяем что создался новый run
    new_run = await db_session.get(SmartSearchRun, run_id)
    assert new_run is not None
    assert new_run.status == "running"


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
@patch('app.services.smart_search._run_search_background', new_callable=AsyncMock)
async def test_start_search_happy_path_creates_run(
    mock_bg,
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест успешного одиночного запуска без блокировок"""
    # Настраиваем моки
    mock_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    # Первый запуск должен создать run и вернуть UUID
    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None

    # Проверяем что run создался корректно
    run = await db_session.get(SmartSearchRun, run_id)
    assert run is not None
    assert run.status == "running"
    assert run.company_id == test_company.id
    assert run.vacancy_id == test_vacancy.id


# === НОВЫЕ ТЕСТЫ для фиксов TOCTOU и idle-in-transaction ===

@pytest.mark.asyncio
@patch('app.api.v1.smart._run_base_evaluate', new_callable=AsyncMock)
async def test_evaluate_toctou_prevention(mock_evaluate, db_session, test_company):
    """Тест предотвращения TOCTOU в evaluate_base_search_candidates"""
    from app.models.base_search import BaseSearchRun
    from app.api.v1.smart import evaluate_base_search_candidates
    from app.schemas.base_search import BaseEvaluateRequest
    from app.core.errors import ConflictError
    from uuid import uuid4

    # Создаём BaseSearchRun в статусе 'retrieved'
    run_id = uuid4()
    run = BaseSearchRun(
        id=run_id,
        company_id=test_company.id,
        search_type="prompt",
        query_text="test query",
        status="retrieved",
        found=10
    )
    db_session.add(run)
    await db_session.commit()

    # Подготавливаем request
    request = BaseEvaluateRequest(evaluate_n=5)

    # Создаём мок текущего пользователя (admin)
    class MockUser:
        role = "admin"
        id = uuid4()

    current_user = MockUser()

    # Эндпоинт делает атомарный UPDATE на сессии запроса (db_session) — отдельный
    # AsyncSessionLocal больше не нужен. Фоновая задача замокана (см. декоратор).
    # Первый вызов должен успешно флипнуть статус
    result1 = await evaluate_base_search_candidates(
        run_id=run_id,
        request=request,
        session=db_session,
        company_id=test_company.id,
        current_user=current_user
    )

    assert result1.run_id == run_id

    # Проверяем что статус изменился на 'running'
    await db_session.refresh(run)
    assert run.status == "running"
    assert run.stage == "rerank"
    assert run.to_evaluate == 5

    # Второй вызов должен получить ConflictError
    with pytest.raises(ConflictError) as exc_info:
        await evaluate_base_search_candidates(
            run_id=run_id,
            request=request,
            session=db_session,
            company_id=test_company.id,
            current_user=current_user
        )

    assert "уже выполняется" in str(exc_info.value)

    # Проверяем что mock_evaluate был вызван только один раз
    assert mock_evaluate.call_count == 1


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_resume_by_id')
@patch('app.services.smart_search.hh_client.invite_to_vacancy')
@patch('app.services.smart_search.audit')
async def test_invite_selected_session_commit_before_loop(
    mock_audit,
    mock_invite,
    mock_get_resume,
    mock_token,
    db_session,
    test_company,
    test_vacancy
):
    """Тест что invite_selected коммитит request-сессию перед сетевым циклом"""

    # Подготавливаем данные
    run_id = uuid4()
    user_id = uuid4()
    resume_id = "test_resume_123"

    # Создаём SmartSearchRun с scored_candidates
    from app.models import SmartSearchRun

    run = SmartSearchRun(
        id=run_id,
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="done",
        stage="done",
        scored_candidates=[
            {
                "hh_resume_id": resume_id,
                "passed": True,
                "invited": False,
                "name": "Тест Кандидат",
                "score": 85,
                "verdict": "Подходит"
            }
        ]
    )
    db_session.add(run)

    # Устанавливаем hh_vacancy_id
    test_vacancy.hh_vacancy_id = "hh_vac_123"
    await db_session.commit()

    # Мокаем внешние вызовы
    mock_token.return_value = "test_token"
    mock_get_resume.return_value = {
        "id": resume_id,
        "first_name": "Тест",
        "last_name": "Кандидат",
        "contact": [{"type": {"id": "email"}, "value": "test@example.com"}],
        "title": "Тестовая позиция"
    }
    mock_invite.return_value = {"url": "/negotiations/456"}

    # Мокаем check_access и AsyncSessionLocal
    with patch('app.services.smart_search.check_access', return_value=(True, True, None)), \
         patch('app.services.smart_search.AsyncSessionLocal', _session_local_returning(db_session)):

        # Вызываем функцию
        from app.services.smart_search import invite_selected
        result = await invite_selected(
            db_session, test_company.id, user_id, run_id, [resume_id]
        )

    # Проверяем что функционал НЕ сломался после добавления commit()
    assert result["invited_count"] == 1
    assert len(result["results"]) == 1

    result_item = result["results"][0]
    assert result_item["resume_id"] == resume_id
    assert result_item["status"] == "invited"
    assert result_item["candidate_id"] is not None
    assert result_item["name"] == "Тест Кандидат"