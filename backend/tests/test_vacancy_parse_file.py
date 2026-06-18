"""Тесты парсинга файла вакансии POST /vacancies/parse-file"""

import pytest
from unittest.mock import patch, AsyncMock
from io import BytesIO

from app.core.security import create_access_token


def _manager_headers(manager_user) -> dict:
    token = create_access_token({"sub": str(manager_user.id)})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Успешный парсинг — call_json возвращает нужные поля
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_vacancy_file_success(async_client, auth_headers):
    """Успешный парсинг: поля заполнены, ЗП приведена к int, отсутствующее = null."""
    mock_vacancy_data = {
        "name": "Менеджер по продажам",
        "city": "Москва",
        "department": "Отдел продаж",
        "employment_type": "Полная занятость",
        "salary_from": 120000,
        "salary_to": 180000,
        "description": "Обязанности: продажи, переговоры.\nТребования: опыт от 2 лет.",
    }

    # Патчим по месту импорта (в роутере vacancies.py)
    with patch("app.api.v1.vacancies.parse_vacancy_to_dict", new_callable=AsyncMock) as mock_parse:
        mock_parse.return_value = mock_vacancy_data
        files = {"file": ("vacancy.txt", BytesIO(b"Test vacancy content"), "text/plain")}
        response = await async_client.post(
            "/api/v1/vacancies/parse-file", files=files, headers=auth_headers
        )

    assert response.status_code == 200
    result = response.json()
    assert result["parsed"] is True
    assert result["reason"] is None
    f = result["fields"]
    assert f["name"] == "Менеджер по продажам"
    assert f["city"] == "Москва"
    assert f["department"] == "Отдел продаж"
    assert f["employment_type"] == "Полная занятость"
    assert f["salary_from"] == 120000
    assert f["salary_to"] == 180000
    assert "продажи" in f["description"]


# ---------------------------------------------------------------------------
# Зарплата только нижняя граница — salary_to null
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_vacancy_file_salary_from_only(async_client, auth_headers):
    """Когда указана только одна граница ЗП — salary_to остаётся null."""
    mock_data = {
        "name": "Бухгалтер",
        "city": None,
        "department": None,
        "employment_type": None,
        "salary_from": 90000,
        "salary_to": None,
        "description": None,
    }

    with patch("app.api.v1.vacancies.parse_vacancy_to_dict", new_callable=AsyncMock) as mock_parse:
        mock_parse.return_value = mock_data
        files = {"file": ("vac.pdf", BytesIO(b"PDF content"), "application/pdf")}
        response = await async_client.post(
            "/api/v1/vacancies/parse-file", files=files, headers=auth_headers
        )

    assert response.status_code == 200
    result = response.json()
    assert result["parsed"] is True
    assert result["fields"]["salary_from"] == 90000
    assert result["fields"]["salary_to"] is None


# ---------------------------------------------------------------------------
# Неподдерживаемый формат / не распознан текст → parse_vacancy_to_dict = None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_vacancy_file_unsupported_format(async_client, auth_headers):
    """Неподдерживаемый формат или пустой текст: parsed=False + reason, без 500."""
    with patch("app.api.v1.vacancies.parse_vacancy_to_dict", new_callable=AsyncMock) as mock_parse:
        mock_parse.return_value = None
        files = {"file": ("vacancy.doc", BytesIO(b"Binary content"), "application/msword")}
        response = await async_client.post(
            "/api/v1/vacancies/parse-file", files=files, headers=auth_headers
        )

    assert response.status_code == 200
    result = response.json()
    assert result["parsed"] is False
    assert result["reason"]
    assert result["fields"] == {}


# ---------------------------------------------------------------------------
# RBAC: менеджер → 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_vacancy_file_manager_forbidden(async_client, manager_user):
    """Менеджер не может парсить файл вакансии → 403."""
    files = {"file": ("vacancy.pdf", BytesIO(b"Test content"), "application/pdf")}
    response = await async_client.post(
        "/api/v1/vacancies/parse-file",
        files=files,
        headers=_manager_headers(manager_user),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Нет ключа компании → OpenRouterNotConfiguredError → 400 (не 500, не фейк-поля)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_vacancy_file_no_openrouter_key(async_client, auth_headers):
    """Нет ключа OpenRouter у компании → 400 OPENROUTER_NOT_CONFIGURED, не 500."""
    from app.core.errors import OpenRouterNotConfiguredError

    with patch(
        "app.api.v1.vacancies.get_company_openrouter_key",
        new_callable=AsyncMock,
        side_effect=OpenRouterNotConfiguredError(),
    ):
        files = {"file": ("vacancy.pdf", BytesIO(b"Test content"), "application/pdf")}
        response = await async_client.post(
            "/api/v1/vacancies/parse-file", files=files, headers=auth_headers
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "OPENROUTER_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# Сервисный слой: parse_vacancy_to_dict с мок extract_resume_text + call_json
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_vacancy_to_dict_success():
    """parse_vacancy_to_dict: текст извлечён → call_json → поля корректно коэрсируются."""
    from app.services.glafira.vacancy_parse import parse_vacancy_to_dict

    llm_response = {
        "name": "  Senior Python Developer  ",  # пробелы — _to_str срежет
        "city": "Санкт-Петербург",
        "department": None,
        "employment_type": "Полная занятость",
        "salary_from": "130 000",  # строка — _to_int распарсит
        "salary_to": 200000,
        "description": "Разработка микросервисов.",
    }

    with (
        patch(
            "app.services.glafira.vacancy_parse.extract_resume_text",
            new_callable=AsyncMock,
            return_value="Текст вакансии",
        ),
        patch(
            "app.services.glafira.vacancy_parse.call_json",
            new_callable=AsyncMock,
            return_value=llm_response,
        ),
    ):
        result = await parse_vacancy_to_dict(b"content", "vacancy.pdf", "test-key")

    assert result is not None
    assert result["name"] == "Senior Python Developer"
    assert result["city"] == "Санкт-Петербург"
    assert result["department"] is None
    assert result["salary_from"] == 130000  # строка→int
    assert result["salary_to"] == 200000
    assert result["description"] == "Разработка микросервисов."


@pytest.mark.asyncio
async def test_parse_vacancy_to_dict_no_text():
    """Если extract_resume_text вернул None — parse_vacancy_to_dict возвращает None."""
    from app.services.glafira.vacancy_parse import parse_vacancy_to_dict

    with patch(
        "app.services.glafira.vacancy_parse.extract_resume_text",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await parse_vacancy_to_dict(b"", "vacancy.doc", "test-key")

    assert result is None


@pytest.mark.asyncio
async def test_parse_vacancy_to_dict_call_json_exception():
    """Если call_json кидает исключение — parse_vacancy_to_dict возвращает None, не 500."""
    from app.services.glafira.vacancy_parse import parse_vacancy_to_dict

    with (
        patch(
            "app.services.glafira.vacancy_parse.extract_resume_text",
            new_callable=AsyncMock,
            return_value="Текст вакансии",
        ),
        patch(
            "app.services.glafira.vacancy_parse.call_json",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM timeout"),
        ),
    ):
        result = await parse_vacancy_to_dict(b"content", "vacancy.pdf", "test-key")

    assert result is None
