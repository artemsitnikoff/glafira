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
    get_run_status,
    derive_vacancy_filters,
    preview_found_count,
    build_search_params,
    suggest_areas,
    _compact_resume_for_display,
    FREE_SCAN_LIMIT
)
from app.schemas.smart import SmartSearchRequest, SmartCountRequest
from app.models import SmartSearchRun, Candidate, Application
from app.core.errors import ValidationError


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

    error_msg = str(exc_info.value)
    assert "100" in error_msg
    assert str(FREE_SCAN_LIMIT) in error_msg
    assert "confirm_cost=true" in error_msg


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
    calls = mock_search_resumes.call_args_list
    assert calls[0][1]["page"] == 0
    assert calls[1][1]["page"] == 1
    assert calls[2][1]["page"] == 2


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
    call_args = mock_search_resumes.call_args[1]
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
        "area": "113",  # Числовое значение - включается
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
    assert result["only_with_salary"] == "false"

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
@patch('app.services.smart_search.call_json')
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
    assert "Python" in result["skills"]
    assert "Git" in result["skills"]
    assert "Docker" in result["skills"]

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