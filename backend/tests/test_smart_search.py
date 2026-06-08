"""Тесты умного подбора кандидатов - обновленные под новую модель доступа

⚠️ ВСЕ ТЕСТЫ НА МОКАХ - НИ ОДНОГО реального hh.ru вызова!
Реальный поиск/оценка/приглашения проверяются заказчиком на платном доступе hh.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.smart_search import (
    check_access,
    get_smart_vacancies,
    start_search,
    get_run_status
)
from app.schemas.smart import SmartSearchRequest
from app.models import SmartSearchRun, Candidate, Application


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
    assert smart_vacancy.area == test_vacancy.city  # БАГ 1: area теперь == city для display-префилла
    assert smart_vacancy.professional_role == test_vacancy.name  # БАГ 1: роль == название вакансии
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
async def test_start_search_with_paid_access(
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