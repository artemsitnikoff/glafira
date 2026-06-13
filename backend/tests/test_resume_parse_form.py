"""Тесты парсинга резюме для формы создания кандидата"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO

from app.core.security import create_access_token


def _manager_headers(manager_user) -> dict:
    token = create_access_token({"sub": str(manager_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_parse_resume_endpoint_success(async_client, auth_headers):
    """Тест успешного парсинга резюме (мок parse_resume_to_dict на пути импорта роутера)"""
    mock_resume_data = {
        "first_name": "Алексей",
        "last_name": "Иванов",
        "middle_name": "Петрович",
        "phone": "+7 916 123-45-67",
        "email": "aleksey.ivanov@example.com",
        "city": "Москва",
        "salary_expectation": 150000,
        "last_position": "Senior Python Developer",
        "last_company": "ООО Технологии",
        "last_period": "Янв 2022 - наст. время",
        "about": "Опытный разработчик с 5 лет опыта в Python",
        "experience": [
            {
                "position": "Senior Python Developer",
                "company": "ООО Технологии",
                "period": "Янв 2022 - наст. время",
                "description": "Разработка веб-приложений на Django/FastAPI"
            }
        ],
        "skills": ["Python", "Django", "FastAPI", "PostgreSQL"],
        "education": [
            {"institution": "МГУ", "specialty": "Программная инженерия", "years": "2015-2019"}
        ],
        "languages": ["Русский - Родной", "Английский - B2"]
    }

    # ВАЖНО: патчим имя в модуле роутера (top-level импорт), а не в источнике
    with patch('app.api.v1.candidates.parse_resume_to_dict', new_callable=AsyncMock) as mock_parse:
        mock_parse.return_value = mock_resume_data
        files = {"file": ("resume.txt", BytesIO(b"Test resume content"), "text/plain")}
        response = await async_client.post("/api/v1/candidates/parse-resume", files=files, headers=auth_headers)

    assert response.status_code == 200
    result = response.json()
    assert result["parsed"] is True
    assert result["fields"]["first_name"] == "Алексей"
    assert result["fields"]["last_name"] == "Иванов"
    assert result["fields"]["middle_name"] == "Петрович"
    assert result["fields"]["salary_expectation"] == 150000
    assert len(result["fields"]["experience"]) == 1
    assert len(result["fields"]["skills"]) == 4
    assert len(result["fields"]["education"]) == 1
    assert len(result["fields"]["languages"]) == 2


@pytest.mark.asyncio
async def test_parse_resume_unsupported_format(async_client, auth_headers):
    """Тест неподдерживаемого формата файла → parsed=false (не 500)"""
    with patch('app.api.v1.candidates.parse_resume_to_dict', new_callable=AsyncMock) as mock_parse:
        mock_parse.return_value = None
        files = {"file": ("resume.doc", BytesIO(b"Test doc content"), "application/msword")}
        response = await async_client.post("/api/v1/candidates/parse-resume", files=files, headers=auth_headers)

    assert response.status_code == 200
    result = response.json()
    assert result["parsed"] is False
    assert result["reason"]
    assert result["fields"] in ({}, None)


@pytest.mark.asyncio
async def test_parse_resume_manager_forbidden(async_client, manager_user):
    """Тест запрета менеджеру парсить резюме → 403"""
    files = {"file": ("resume.pdf", BytesIO(b"Test resume content"), "application/pdf")}
    response = await async_client.post(
        "/api/v1/candidates/parse-resume", files=files, headers=_manager_headers(manager_user)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_candidate_with_experience_skills_education(db_session, admin_user, test_company):
    """Тест создания кандидата с опытом, навыками и образованием"""
    from app.services.candidate import create_candidate
    from app.schemas.candidate import CandidateCreate, ExperienceCreate, EducationCreate

    candidate_data = CandidateCreate(
        first_name="Алексей", last_name="Иванов", middle_name="Петрович", source="manual",
        phone="+7 916 123-45-67", email="aleksey.ivanov@example.com", city="Москва",
        salary_expectation=150000, last_position="Senior Python Developer",
        last_company="ООО Технологии", last_period="Янв 2022 - наст. время",
        experience=[
            ExperienceCreate(position="Senior Python Developer", company="ООО Технологии",
                             period="Янв 2022 - наст. время", description="Django/FastAPI"),
            ExperienceCreate(position="Python Developer", company="ООО Стартап",
                             period="Дек 2019 - Дек 2021", description="API и админки"),
        ],
        skills=["Python", "Django", "FastAPI", "PostgreSQL"],
        education=[EducationCreate(institution="МГУ", specialty="Программная инженерия", years="2015-2019")],
    )

    result = await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)

    assert result.first_name == "Алексей"
    assert result.last_position == "Senior Python Developer"
    assert len(result.experience) == 2
    assert len(result.skills) == 4
    assert "Python" in result.skills  # CandidateDetail.skills — список строк
    assert len(result.education) == 1
    assert result.education[0].institution == "МГУ"


@pytest.mark.asyncio
async def test_create_candidate_empty_experience_position_rejected():
    """Пустой position в опыте теперь отклоняется СХЕМОЙ (ExperienceCreate.position
    min_length=1) — пустые записи не доходят до сервиса (раньше «пропускались» в коде)."""
    from app.schemas.candidate import ExperienceCreate

    with pytest.raises(ValueError):  # pydantic.ValidationError ⊂ ValueError
        ExperienceCreate(position="", company="ООО Тест", period="2020-2021")


@pytest.mark.asyncio
async def test_create_candidate_sync_last_position_from_experience(db_session, admin_user, test_company):
    """Тест синхронизации last_position из опыта работы, когда явно не задан"""
    from app.services.candidate import create_candidate
    from app.schemas.candidate import CandidateCreate, ExperienceCreate

    candidate_data = CandidateCreate(
        first_name="Семён", last_name="Синков", source="manual",
        experience=[
            ExperienceCreate(position="Senior Developer", company="Компания А", period="Янв 2022 - наст. время"),
            ExperienceCreate(position="Junior Developer", company="Компания Б", period="2020-2021"),
        ],
    )
    result = await create_candidate(db_session, candidate_data, test_company.id, admin_user.id)
    assert result.last_position == "Senior Developer"
    assert result.last_company == "Компания А"


@pytest.mark.asyncio
async def test_upload_document_with_parse_false(db_session, admin_user, test_company, test_candidate):
    """Тест загрузки документа с parse=False → парсер НЕ вызывается"""
    from app.services.document import upload_document

    mock_file = MagicMock()
    mock_file.filename = "resume.pdf"
    mock_file.content_type = "application/pdf"  # upload_document валидирует content_type
    mock_file.read = AsyncMock(return_value=b"test content")

    with patch('app.services.glafira.resume_parse.parse_and_apply_resume', new_callable=AsyncMock) as mock_parse:
        result = await upload_document(
            db_session, test_candidate.id, mock_file, "resume", False, test_company.id, admin_user.id
        )
        mock_parse.assert_not_called()
        assert result.filename == "resume.pdf"


@pytest.mark.asyncio
async def test_upload_document_with_parse_true(db_session, admin_user, test_company, test_candidate):
    """Тест загрузки документа с parse=True (дефолт) → парсер вызывается"""
    from app.services.document import upload_document

    mock_file = MagicMock()
    mock_file.filename = "resume.pdf"
    mock_file.content_type = "application/pdf"  # upload_document валидирует content_type
    mock_file.read = AsyncMock(return_value=b"test content")

    with patch('app.services.glafira.resume_parse.parse_and_apply_resume', new_callable=AsyncMock) as mock_parse:
        result = await upload_document(
            db_session, test_candidate.id, mock_file, "resume", True, test_company.id, admin_user.id
        )
        mock_parse.assert_called_once()
        assert result.filename == "resume.pdf"
