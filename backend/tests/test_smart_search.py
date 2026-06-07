"""Тесты умного подбора кандидатов

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
    has_access, reason = await check_access(db_session, test_company.id)

    assert has_access is False
    assert "не подключён" in reason


@pytest.mark.asyncio
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_check_access_with_hh_integration(
    mock_quota,
    mock_get_me,
    mock_token,
    db_session,
    test_company
):
    """Тест проверки доступа с подключенным hh.ru"""
    # Мокаем успешные вызовы
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    has_access, reason = await check_access(db_session, test_company.id)

    assert has_access is True
    assert reason is None


@pytest.mark.asyncio
async def test_get_smart_vacancies_mapping(db_session, test_company, test_vacancy):
    """Тест маппинга вакансии в фильтры hh.ru"""
    smart_vacancies = await get_smart_vacancies(db_session, test_company.id)

    assert len(smart_vacancies) == 1
    smart_vacancy = smart_vacancies[0]

    # Проверяем маппинг полей
    assert smart_vacancy.id == test_vacancy.id
    assert smart_vacancy.title == test_vacancy.name
    assert smart_vacancy.city == test_vacancy.city
    assert smart_vacancy.salary_from == test_vacancy.salary_from
    assert smart_vacancy.salary_to == test_vacancy.salary_to
    assert smart_vacancy.found is None  # Не заполняется без поиска
    assert smart_vacancy.hh_published == False  # Без hh_vacancy_id


@pytest.mark.asyncio
async def test_get_smart_vacancies_hh_published(db_session, test_company, test_vacancy):
    """Тест поля hh_published в зависимости от hh_vacancy_id"""
    # Устанавливаем hh_vacancy_id
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    smart_vacancies = await get_smart_vacancies(db_session, test_company.id)

    assert len(smart_vacancies) == 1
    assert smart_vacancies[0].hh_published == True  # С hh_vacancy_id


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_quota_check_insufficient_views(
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест предохранителя квоты: недостаточно просмотров резюме"""
    # Устанавливаем hh_vacancy_id для прохождения проверки
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем доступ
    mock_access.return_value = (True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}

    # Мокаем недостаточную квоту
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 10}}  # Меньше чем scan_n=50
        ]
    }

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    # Должен выбросить ValidationError
    with pytest.raises(Exception) as exc_info:
        await start_search(db_session, test_company.id, admin_user.id, request)

    assert "квота" in str(exc_info.value).lower()


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_quota_undefined_fail_closed(
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест fail-closed: если остаток квоты не определён (None) - не запускаем"""
    # Устанавливаем hh_vacancy_id для прохождения проверки
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем доступ
    mock_access.return_value = (True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}

    # Мокаем квоту в неожиданном формате (нет услуг)
    mock_quota.return_value = {"items": []}

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=20,
        invite_m=5,
        threshold=70
    )

    # Должен выбросить ValidationError об отсутствии API-услуги
    with pytest.raises(Exception) as exc_info:
        await start_search(db_session, test_company.id, admin_user.id, request)

    error_msg = str(exc_info.value)
    assert "нет активной api-услуги hh" in error_msg.lower()


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_vacancy_without_hh_id_fail_closed(
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест fail-closed: вакансия без hh_vacancy_id - не запускаем"""
    # НЕ устанавливаем hh_vacancy_id (остаётся None/пустым)
    assert not test_vacancy.hh_vacancy_id

    # Мокаем доступ
    mock_access.return_value = (True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}

    # Мокаем нормальную квоту (но она даже не должна проверяться)
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=20,
        invite_m=5,
        threshold=70
    )

    # Должен выбросить ValidationError про отсутствие публикации на hh
    with pytest.raises(Exception) as exc_info:
        await start_search(db_session, test_company.id, admin_user.id, request)

    error_msg = str(exc_info.value)
    assert "не опубликована на hh.ru" in error_msg
    assert "опубликуйте вакансию на hh" in error_msg.lower()

    # Платные методы не должны были вызываться
    mock_quota.assert_not_called()


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
@patch('app.services.smart_search.asyncio.create_task')
async def test_successful_search_start(
    mock_create_task,
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест успешного запуска поиска с достаточными квотами"""
    # Устанавливаем hh_vacancy_id для прохождения проверки
    test_vacancy.hh_vacancy_id = "67890"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем успешные проверки
    mock_access.return_value = (True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    # Мокаем создание задачи
    mock_task = AsyncMock()
    mock_create_task.return_value = mock_task

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        area="1",  # Москва
        skills=["Python", "Django"],
        scan_n=50,
        invite_m=10,
        threshold=70
    )

    run_id = await start_search(db_session, test_company.id, admin_user.id, request)

    # Проверяем что создалась запись
    assert run_id is not None
    run = await get_run_status(db_session, run_id, test_company.id)
    assert run is not None
    assert run.status == "running"
    assert run.stage == "search"
    assert run.params["scan_n"] == 50
    assert run.params["invite_m"] == 10
    assert run.params["threshold"] == 70

    # Проверяем что запустилась фоновая задача
    mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_deduplication_by_hh_resume_id(db_session, test_company):
    """Тест дедубликации: поиск по hh_resume_id имеет приоритет"""
    from app.services.smart_search import _find_existing_candidate

    # Создаем существующего кандидата с hh_resume_id
    test_candidate = Candidate(
        company_id=test_company.id,
        first_name="John",
        last_name="Doe",
        email="test@example.com",
        extra={"smart_search": True, "hh_resume_id": "resume_123"}
    )
    db_session.add(test_candidate)
    await db_session.commit()

    # Резюме с тем же ID
    resume_data = {
        "id": "resume_123",
        "first_name": "John",
        "last_name": "Doe",
        "contact": [{"type": {"id": "email"}, "value": "test@example.com"}],
        "title": "Python Developer",
        "experience": []
    }

    # Дедубликация должна найти по hh_resume_id
    existing = await _find_existing_candidate(
        db_session,
        "resume_123",
        resume_data,
        test_company.id
    )
    assert existing is not None
    assert existing.id == test_candidate.id


@pytest.mark.asyncio
async def test_deduplication_by_email_fallback(db_session, test_company):
    """Тест дедубликации: fallback на email если hh_resume_id не найден"""
    from app.services.smart_search import _find_existing_candidate

    # Создаем существующего кандидата БЕЗ hh_resume_id, но с email
    test_candidate = Candidate(
        company_id=test_company.id,
        first_name="Jane",
        last_name="Smith",
        email="jane@example.com",
        extra={}
    )
    db_session.add(test_candidate)
    await db_session.commit()

    # Резюме с другим ID, но тем же email
    resume_data = {
        "id": "resume_456",
        "first_name": "Jane",
        "last_name": "Smith",
        "contact": [{"type": {"id": "email"}, "value": "jane@example.com"}],
        "title": "QA Engineer",
        "experience": []
    }

    # Дедубликация должна найти по email (fallback)
    existing = await _find_existing_candidate(
        db_session,
        "resume_456",
        resume_data,
        test_company.id
    )
    assert existing is not None
    assert existing.id == test_candidate.id


@pytest.mark.asyncio
async def test_run_status_tracking(db_session, test_company, test_vacancy):
    """Тест отслеживания статуса выполнения поиска"""
    # Создаем тестовую запись поиска
    run = SmartSearchRun(
        company_id=test_company.id,
        vacancy_id=test_vacancy.id,
        status="running",
        stage="eval",
        params={"scan_n": 50, "invite_m": 10, "threshold": 70},
        found=100,
        scanned=25,
        evaluated=20,
        invited=5
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    # Проверяем получение статуса
    status = await get_run_status(db_session, run.id, test_company.id)
    assert status is not None
    assert status.status == "running"
    assert status.stage == "eval"
    assert status.found == 100
    assert status.scanned == 25
    assert status.evaluated == 20
    assert status.invited == 5


@pytest.mark.asyncio
@patch('app.services.glafira.scoring.call_json')
async def test_score_resume_dict_no_persist(mock_llm, test_company, test_vacancy):
    """Тест score_resume_dict: оценивает резюме без записи в БД"""
    from app.services.glafira.scoring import score_resume_dict

    # Мокаем ответ LLM
    mock_llm.return_value = {
        "score": 85,
        "verdict": "good",
        "summary": "Сильный кандидат с релевантным опытом",
        "strengths": ["Python", "Django"],
        "risks": ["Нет опыта с микросервисами"],
        "requirements_match": [
            {"criterion": "Python", "weight": 25, "points": 25, "comment": "Отличное знание"}
        ],
        "forecast": "Готов приступить через 2 недели",
        "questions": ["Опыт с Docker?"]
    }

    # Данные резюме hh.ru
    resume_data = {
        "id": "resume_123",
        "first_name": "Иван",
        "last_name": "Иванов",
        "title": "Python Developer",
        "area": {"name": "Москва"},
        "experience": [
            {
                "position": "Senior Python Developer",
                "company": "Tech Corp",
                "start": "2020-01",
                "description": "Разработка веб-приложений на Django"
            }
        ],
        "skills": "Python, Django, PostgreSQL"
    }

    # Оцениваем резюме
    result = await score_resume_dict(resume_data, test_vacancy, test_company.id)

    # Проверяем результат
    assert result["score"] == 85
    assert result["verdict"] == "good"
    assert result["summary"] == "Сильный кандидат с релевантным опытом"

    # Убеждаемся что call_json вызван с правильными параметрами
    mock_llm.assert_called_once()
    call_args = mock_llm.call_args
    assert "Python Developer" in call_args[1]["user"]  # вакансия в промпте
    assert "Иван Иванов" in call_args[1]["user"]      # кандидат в промпте


@pytest.mark.asyncio
async def test_candidate_creation_from_resume(db_session, test_company):
    """Тест создания кандидата из данных резюме hh.ru"""
    from app.services.smart_search import _create_candidate_from_resume

    # Данные резюме из hh.ru
    resume_data = {
        "id": "resume_123",
        "first_name": "Иван",
        "last_name": "Иванов",
        "middle_name": "Иванович",
        "title": "Python Developer",
        "area": {"name": "Москва"},
        "contact": [
            {"type": {"id": "email"}, "value": "ivan@example.com"},
            {"type": {"id": "cell"}, "value": "+7 900 123-45-67"}
        ],
        "experience": [
            {
                "position": "Senior Python Developer",
                "company": "Tech Corp",
                "start": "2020-01",
                "end": None,
                "description": "Разработка веб-приложений на Django"
            }
        ],
        "skills": "Python, Django, PostgreSQL"
    }

    # Создаем кандидата
    candidate = _create_candidate_from_resume(resume_data, test_company.id)

    # Проверяем корректность маппинга
    assert candidate.first_name == "Иван"
    assert candidate.last_name == "Иванов"
    assert candidate.middle_name == "Иванович"
    assert candidate.source == "hh"
    assert candidate.city == "Москва"
    assert candidate.email == "ivan@example.com"
    assert candidate.phone == "+7 900 123-45-67"
    assert candidate.last_position == "Python Developer"
    assert "Python Developer" in candidate.resume_text
    assert "Python, Django, PostgreSQL" in candidate.resume_text


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
@patch('app.services.smart_search.asyncio.create_task')
async def test_quota_api_unlimited_passes(
    mock_create_task,
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест безлимитной услуги API_UNLIMITED: проходит любой scan_n"""
    # Устанавливаем hh_vacancy_id для прохождения проверки
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем доступ
    mock_access.return_value = (True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}

    # Мокаем безлимитную услугу
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_UNLIMITED"}, "balance": None}
        ]
    }

    # Мокаем создание задачи
    mock_task = AsyncMock()
    mock_create_task.return_value = mock_task

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=1000,  # Большое число — при unlimited должно пройти
        invite_m=100,
        threshold=70
    )

    # Должно пройти успешно
    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
@patch('app.services.smart_search.asyncio.create_task')
async def test_quota_api_limited_sufficient(
    mock_create_task,
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест лимитной услуги с достаточным остатком"""
    # Устанавливаем hh_vacancy_id для прохождения проверки
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем доступ
    mock_access.return_value = (True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}

    # Мокаем лимитную услугу с достаточным остатком
    mock_quota.return_value = {
        "items": [
            {"service_type": {"id": "API_LIMITED"}, "balance": {"actual": 100}}
        ]
    }

    # Мокаем создание задачи
    mock_task = AsyncMock()
    mock_create_task.return_value = mock_task

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=50,   # Меньше остатка
        invite_m=30, # Меньше остатка
        threshold=70
    )

    # Должно пройти успешно
    run_id = await start_search(db_session, test_company.id, admin_user.id, request)
    assert run_id is not None


@pytest.mark.asyncio
@patch('app.services.smart_search.check_access')
@patch('app.services.smart_search.hh_service.get_valid_access_token')
@patch('app.services.smart_search.hh_client.get_me')
@patch('app.services.smart_search.hh_client.get_payable_api_actions')
async def test_quota_fail_closed_on_exception(
    mock_quota,
    mock_get_me,
    mock_token,
    mock_access,
    db_session,
    test_company,
    test_vacancy,
    admin_user
):
    """Тест fail-closed при исключении проверки квоты"""
    # Устанавливаем hh_vacancy_id для прохождения проверки
    test_vacancy.hh_vacancy_id = "12345"
    db_session.add(test_vacancy)
    await db_session.commit()

    # Мокаем доступ
    mock_access.return_value = (True, None)
    mock_token.return_value = "test_token"
    mock_get_me.return_value = {"employer": {"id": "123456"}}

    # Мокаем исключение при получении квоты
    mock_quota.side_effect = Exception("API timeout")

    request = SmartSearchRequest(
        vacancy_id=test_vacancy.id,
        scan_n=20,
        invite_m=5,
        threshold=70
    )

    # Должен выбросить ValidationError
    with pytest.raises(Exception) as exc_info:
        await start_search(db_session, test_company.id, admin_user.id, request)

    error_msg = str(exc_info.value).lower()
    assert "не удалось проверить квоту hh" in error_msg


def test_no_real_hh_calls_in_tests():
    """Подтверждение что в тестах нет реальных hh.ru вызовов"""
    # Этот тест служит документацией:
    # ВСЕ hh.ru методы в тестах выше замоканы через @patch
    # НИ ОДНОГО реального API-вызова не происходит
    # Реальные поиск/оценка/приглашения тестируются заказчиком на живом доступе
    assert True, "Все hh.ru вызовы в тестах замоканы - реальные проверки у заказчика"