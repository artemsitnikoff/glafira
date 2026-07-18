"""Тесты генерации рубрикатора критериев оценки (POST /vacancies/generate-rubric + сервис)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.security import create_access_token


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _manager_headers(manager_user) -> dict:
    token = create_access_token({"sub": str(manager_user.id)})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Сервис: generate_scoring_rubric
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_scoring_rubric_returns_text():
    """Мок call_json → {criteria, summary} → вернул читаемый текст с весами."""
    from app.services.glafira.scoring_rubric import generate_scoring_rubric

    mock_response = {
        "criteria": [
            {
                "criterion": "Опыт Python-разработки",
                "weight": 40,
                "must_have": True,
                "signals": "3+ года коммерческой разработки на Python",
            },
            {
                "criterion": "FastAPI / Django / Flask",
                "weight": 30,
                "must_have": False,
                "signals": "упоминание фреймворка в опыте, проекты на нём",
            },
            {
                "criterion": "PostgreSQL",
                "weight": 20,
                "must_have": False,
                "signals": "SQLAlchemy, запросы, миграции",
            },
            {
                "criterion": "Навыки командной работы",
                "weight": 10,
                "must_have": False,
                "signals": "работа в команде, code review",
            },
        ],
        "summary": "Ключевой приоритет — глубокий Python-опыт и знание веб-фреймворков.",
    }

    with patch(
        "app.services.glafira.scoring_rubric.call_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await generate_scoring_rubric(
            vacancy_fields={
                "name": "Python Backend Developer",
                "description": "Разработка REST API на FastAPI, PostgreSQL, pytest.",
                "city": "Москва",
                "department": None,
                "employment_type": "full",
                "salary_from": 200000,
                "salary_to": 350000,
            },
            api_key="test-key",
        )

    assert result is not None
    # Содержит заголовок
    assert "Критерии оценки (сумма весов = 100)" in result
    # Первый must-have критерий помечен «обязательно»
    assert "обязательно" in result
    # Вес присутствует
    assert "вес 40" in result
    # Сигнал присутствует
    assert "3+" in result
    # Summary присутствует
    assert "Главное:" in result
    assert "Python" in result


@pytest.mark.asyncio
async def test_generate_scoring_rubric_empty_description_returns_none():
    """Если description пуст — сразу None, call_json не вызывается."""
    from app.services.glafira.scoring_rubric import generate_scoring_rubric

    with patch(
        "app.services.glafira.scoring_rubric.call_json",
        new_callable=AsyncMock,
    ) as mock_call:
        result = await generate_scoring_rubric(
            vacancy_fields={"name": "Разработчик", "description": ""},
            api_key="test-key",
        )

    assert result is None
    mock_call.assert_not_called()


@pytest.mark.asyncio
async def test_generate_scoring_rubric_none_description_returns_none():
    """Если description = None — тоже None, без вызова LLM."""
    from app.services.glafira.scoring_rubric import generate_scoring_rubric

    with patch(
        "app.services.glafira.scoring_rubric.call_json",
        new_callable=AsyncMock,
    ) as mock_call:
        result = await generate_scoring_rubric(
            vacancy_fields={"description": None},
            api_key="test-key",
        )

    assert result is None
    mock_call.assert_not_called()


@pytest.mark.asyncio
async def test_generate_scoring_rubric_llm_error_returns_none():
    """Если call_json бросает исключение — возвращается None (best-effort), без 500."""
    from app.services.glafira.scoring_rubric import generate_scoring_rubric

    with patch(
        "app.services.glafira.scoring_rubric.call_json",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM timeout"),
    ):
        result = await generate_scoring_rubric(
            vacancy_fields={"description": "Требования: Python, FastAPI."},
            api_key="test-key",
        )

    assert result is None


@pytest.mark.asyncio
async def test_generate_scoring_rubric_must_have_label():
    """must_have=true → метка «обязательно»; must_have=false → без метки."""
    from app.services.glafira.scoring_rubric import generate_scoring_rubric

    mock_response = {
        "criteria": [
            {"criterion": "Обязательный навык", "weight": 60, "must_have": True, "signals": "сигнал А"},
            {"criterion": "Желательный навык", "weight": 40, "must_have": False, "signals": "сигнал Б"},
        ],
        "summary": "Два критерия.",
    }

    with patch(
        "app.services.glafira.scoring_rubric.call_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await generate_scoring_rubric(
            vacancy_fields={"description": "Требования к кандидату: знание Python."},
            api_key="test-key",
        )

    assert result is not None
    # Обязательный помечен
    lines = result.splitlines()
    must_have_line = next(l for l in lines if "Обязательный навык" in l)
    assert "обязательно" in must_have_line
    # Желательный НЕ помечен
    optional_line = next(l for l in lines if "Желательный навык" in l)
    assert "обязательно" not in optional_line


# ---------------------------------------------------------------------------
# Эндпоинт: POST /vacancies/generate-rubric
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_rubric_endpoint_happy_path(async_client, auth_headers):
    """Успешная генерация: generated=true, rubric непустой."""
    mock_response = {
        "criteria": [
            {"criterion": "Ключевой навык", "weight": 100, "must_have": True, "signals": "тест"},
        ],
        "summary": "Главное — ключевой навык.",
    }

    with patch(
        "app.api.v1.vacancies.generate_scoring_rubric",
        new_callable=AsyncMock,
        return_value="Критерии оценки (сумма весов = 100):\n• [вес 100, обязательно] Ключевой навык — тест\n\nГлавное: Главное — ключевой навык.",
    ):
        response = await async_client.post(
            "/api/v1/vacancies/generate-rubric",
            json={
                "name": "Разработчик",
                "description": "Требования: опыт Python 3+.",
                "city": "Москва",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["generated"] is True
    assert body["reason"] is None
    assert body["rubric"] is not None
    assert len(body["rubric"]) > 0


@pytest.mark.asyncio
async def test_generate_rubric_endpoint_empty_description(async_client, auth_headers):
    """Пустое description → generated=false, reason с текстом."""
    response = await async_client.post(
        "/api/v1/vacancies/generate-rubric",
        json={"name": "Разработчик", "description": ""},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["generated"] is False
    assert body["reason"] == "Заполните описание вакансии"
    assert body["rubric"] is None


@pytest.mark.asyncio
async def test_generate_rubric_endpoint_no_description(async_client, auth_headers):
    """Отсутствующее description → generated=false."""
    response = await async_client.post(
        "/api/v1/vacancies/generate-rubric",
        json={"name": "Разработчик"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["generated"] is False
    assert body["reason"] == "Заполните описание вакансии"


@pytest.mark.asyncio
async def test_generate_rubric_endpoint_manager_forbidden(async_client, manager_user):
    """Менеджер → 403."""
    response = await async_client.post(
        "/api/v1/vacancies/generate-rubric",
        json={"description": "Требования: опыт."},
        headers=_manager_headers(manager_user),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.real_openrouter_key
async def test_generate_rubric_endpoint_no_openrouter_key(async_client, auth_headers):
    """Нет ключа OpenRouter → 400 OPENROUTER_NOT_CONFIGURED."""
    from app.core.errors import OpenRouterNotConfiguredError

    with patch(
        "app.api.v1.vacancies.get_company_openrouter_key",
        new_callable=AsyncMock,
        side_effect=OpenRouterNotConfiguredError(),
    ):
        response = await async_client.post(
            "/api/v1/vacancies/generate-rubric",
            json={"description": "Требования: опыт Python."},
            headers=auth_headers,
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "OPENROUTER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_generate_rubric_endpoint_llm_returns_none(async_client, auth_headers):
    """generate_scoring_rubric вернул None (LLM-ошибка) → generated=false."""
    with patch(
        "app.api.v1.vacancies.generate_scoring_rubric",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await async_client.post(
            "/api/v1/vacancies/generate-rubric",
            json={"description": "Требования: опыт Python."},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["generated"] is False
    assert body["rubric"] is None


# ---------------------------------------------------------------------------
# Авто-заполнение в create_vacancy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_vacancy_auto_rubric_generated(async_client, auth_headers, default_client):
    """При создании без recruiter_scoring_instructions + есть description → рубрикатор проставлен."""
    rubric_text = "Критерии оценки (сумма весов = 100):\n• [вес 100, обязательно] Python — опыт."

    with patch(
        "app.services.vacancy.generate_scoring_rubric",
        new_callable=AsyncMock,
        return_value=rubric_text,
    ):
        response = await async_client.post(
            "/api/v1/vacancies",
            json={
                "name": "Python Backend",
                "description": "<p>Требования: опыт Python от 3 лет.</p>",
                "client_id": default_client,
            },
            headers=auth_headers,
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recruiter_scoring_instructions"] == rubric_text


@pytest.mark.asyncio
async def test_create_vacancy_existing_instructions_not_overwritten(async_client, auth_headers, default_client):
    """Если recruiter_scoring_instructions уже заполнено — НЕ перезаписывать."""
    existing = "Мои ручные критерии оценки."

    with patch(
        "app.services.vacancy.generate_scoring_rubric",
        new_callable=AsyncMock,
        return_value="авто-рубрикатор",
    ) as mock_gen:
        response = await async_client.post(
            "/api/v1/vacancies",
            json={
                "name": "Python Backend",
                "description": "Требования: опыт Python.",
                "recruiter_scoring_instructions": existing,
                "client_id": default_client,
            },
            headers=auth_headers,
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recruiter_scoring_instructions"] == existing
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_create_vacancy_no_description_skips_rubric(async_client, auth_headers, default_client):
    """Нет description → авто-генерация не вызывается, вакансия создаётся нормально."""
    with patch(
        "app.services.vacancy.generate_scoring_rubric",
        new_callable=AsyncMock,
        return_value="авто-рубрикатор",
    ) as mock_gen:
        response = await async_client.post(
            "/api/v1/vacancies",
            json={"name": "Менеджер", "client_id": default_client},
            headers=auth_headers,
        )

    assert response.status_code == 201, response.text
    body = response.json()
    # Рубрикатор не проставлен — описания не было
    assert body["recruiter_scoring_instructions"] is None
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_create_vacancy_rubric_error_still_creates(async_client, auth_headers, default_client):
    """generate_scoring_rubric кидает исключение → вакансия всё равно создаётся, instructions=None."""
    with patch(
        "app.services.vacancy.generate_scoring_rubric",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM timeout"),
    ):
        response = await async_client.post(
            "/api/v1/vacancies",
            json={
                "name": "Java Developer",
                "description": "Требования: Java 11+, Spring Boot.",
                "client_id": default_client,
            },
            headers=auth_headers,
        )

    assert response.status_code == 201, response.text
    body = response.json()
    # Инструкции пусты, но вакансия создана
    assert body["recruiter_scoring_instructions"] is None
    assert body["name"] == "Java Developer"


@pytest.mark.asyncio
async def test_create_vacancy_no_openrouter_key_still_creates(async_client, auth_headers, default_client):
    """OpenRouterNotConfiguredError → пропускаем, вакансия создаётся без рубрикатора."""
    from app.core.errors import OpenRouterNotConfiguredError

    with patch(
        "app.services.vacancy.get_company_openrouter_key",
        new_callable=AsyncMock,
        side_effect=OpenRouterNotConfiguredError(),
    ):
        response = await async_client.post(
            "/api/v1/vacancies",
            json={
                "name": "Data Engineer",
                "description": "Требования: Spark, Hadoop.",
                "client_id": default_client,
            },
            headers=auth_headers,
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Data Engineer"
    assert body["recruiter_scoring_instructions"] is None


@pytest.mark.asyncio
async def test_create_vacancy_rubric_is_company_scoped(async_client, auth_headers, second_company, default_client):
    """Рубрикатор берёт ключ scoped по company_id из контекста (не глобальный)."""
    # Проверяем: generate_scoring_rubric вызывается с api_key из get_company_openrouter_key
    # (который уже мокируется conftest на 'test-openrouter-key' — это и есть company-scoped мок)
    rubric_text = "Критерии: Python."

    with patch(
        "app.services.vacancy.generate_scoring_rubric",
        new_callable=AsyncMock,
        return_value=rubric_text,
    ) as mock_gen:
        response = await async_client.post(
            "/api/v1/vacancies",
            json={
                "name": "ML Engineer",
                "description": "Требования: опыт PyTorch.",
                "client_id": default_client,
            },
            headers=auth_headers,
        )

    assert response.status_code == 201, response.text
    # generate_scoring_rubric вызван ровно один раз с ключом компании
    mock_gen.assert_called_once()
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["api_key"] == "test-openrouter-key"
