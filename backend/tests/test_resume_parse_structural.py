"""Тест структурного извлечения опыта/навыков/образования из резюме"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate, CandidateExperience, CandidateSkill, CandidateEducation
from app.services.glafira.resume_parse import parse_and_apply_resume


@pytest.fixture
def mock_rich_resume_data():
    """Богатый JSON-ответ от LLM с полной структурой"""
    return {
        "last_position": "Senior Python Developer",
        "last_company": "Яндекс",
        "last_period": "Янв 2022 — Наст. время",
        "salary_expectation": "250000",  # Строка для проверки коэрции
        "city": "Москва",
        "phone": "+7 123 456-78-90",
        "email": "john.doe@example.com",
        "experience_years": 5,
        "experience": [
            {
                "position": "Senior Python Developer",
                "company": "Яндекс",
                "period": "Янв 2022 — Наст. время",
                "description": "Разработка высоконагруженных веб-сервисов. Оптимизация производительности на 40%."
            },
            {
                "position": "Python Developer",
                "company": "ВКонтакте",
                "period": "Мар 2020 — Дек 2021",
                "description": "Разработка API для социальной сети. Миграция на микросервисную архитектуру."
            },
            {
                "position": None,  # Пустая position — должна быть пропущена
                "company": "Неизвестная компания",
                "period": "2019",
                "description": "Тестовая запись"
            }
        ],
        "skills": ["Python", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes"],
        "education": [
            {
                "institution": "МГУ имени М.В. Ломоносова",
                "specialty": "Прикладная математика и информатика",
                "years": "2015 — 2019"
            },
            {
                "institution": "Coursera",
                "specialty": "Machine Learning",
                "years": "2020"
            }
        ]
    }


@pytest.mark.asyncio
@patch('app.services.glafira.resume_parse.call_json')
@patch('app.services.glafira.resume_parse.extract_resume_text')
async def test_parse_and_apply_resume_creates_structural_records(
    mock_extract_text,
    mock_call_json,
    mock_rich_resume_data
):
    """Тест создания CandidateExperience/Skill/Education с правильной коэрцией"""

    # Arrange
    mock_extract_text.return_value = "Rich resume content..."
    mock_call_json.return_value = mock_rich_resume_data

    # Создаём мок-сессию и кандидата
    session = AsyncMock(spec=AsyncSession)
    candidate_id = uuid.uuid4()
    company_id = uuid.uuid4()

    # Мок кандидата без существующих записей
    candidate = Candidate(
        id=candidate_id,
        company_id=company_id,
        first_name="Иван",
        last_name="Иванов",
        source="manual"
    )
    candidate.experience = []  # Пустые списки
    candidate.skills = []
    candidate.education = []

    # await session.execute(...) → синхронный Result; .scalar_one_or_none() → candidate
    _result = MagicMock()
    _result.scalar_one_or_none.return_value = candidate
    session.execute = AsyncMock(return_value=_result)
    session.add = AsyncMock()
    session.flush = AsyncMock()

    # Act
    await parse_and_apply_resume(
        session=session,
        candidate_id=candidate_id,
        content=b"fake pdf content",
        filename="resume.pdf",
        company_id=company_id
    )

    # Assert
    # Проверяем вызов парсера с увеличенным max_tokens
    mock_call_json.assert_called_once()
    call_kwargs = mock_call_json.call_args.kwargs
    assert call_kwargs['max_tokens'] == 8000

    # Проверяем создание записей опыта (2 валидных из 3)
    experience_calls = [call for call in session.add.call_args_list
                       if isinstance(call[0][0], CandidateExperience)]
    assert len(experience_calls) == 2  # Третья запись без position должна быть пропущена

    exp1 = experience_calls[0][0][0]
    assert exp1.position == "Senior Python Developer"
    assert exp1.company == "Яндекс"
    assert exp1.period == "Янв 2022 — Наст. время"
    assert exp1.order_index == 0

    exp2 = experience_calls[1][0][0]
    assert exp2.position == "Python Developer"
    assert exp2.company == "ВКонтакте"
    assert exp2.order_index == 1

    # Проверяем создание навыков
    skill_calls = [call for call in session.add.call_args_list
                  if isinstance(call[0][0], CandidateSkill)]
    assert len(skill_calls) == 6
    assert skill_calls[0][0][0].skill == "Python"
    assert skill_calls[0][0][0].order_index == 0

    # Проверяем создание образования
    edu_calls = [call for call in session.add.call_args_list
                if isinstance(call[0][0], CandidateEducation)]
    assert len(edu_calls) == 2
    assert edu_calls[0][0][0].institution == "МГУ имени М.В. Ломоносова"
    assert edu_calls[1][0][0].specialty == "Machine Learning"

    # Проверяем коэрцию скаляров
    assert candidate.salary_expectation == 250000  # Строка → int
    assert candidate.last_position == "Senior Python Developer"


@pytest.mark.asyncio
@patch('app.services.glafira.resume_parse.call_json')
@patch('app.services.glafira.resume_parse.extract_resume_text')
async def test_parse_does_not_overwrite_existing_structural_records(
    mock_extract_text,
    mock_call_json
):
    """Тест: повторный парсинг не затирает существующие структурные записи"""

    # Arrange
    mock_extract_text.return_value = "Some resume content"
    mock_call_json.return_value = {
        "experience": [{"position": "New Position", "company": "New Company"}],
        "skills": ["New Skill"],
        "education": [{"institution": "New University"}]
    }

    session = AsyncMock(spec=AsyncSession)
    candidate_id = uuid.uuid4()
    company_id = uuid.uuid4()

    # Кандидат с существующими записями
    candidate = Candidate(
        id=candidate_id,
        company_id=company_id,
        first_name="Иван",
        last_name="Иванов",
        source="manual"
    )

    # Имитируем существующие записи
    existing_exp = CandidateExperience(candidate_id=candidate_id, position="Existing Position")
    candidate.experience = [existing_exp]
    candidate.skills = [CandidateSkill(candidate_id=candidate_id, skill="Existing Skill")]
    candidate.education = [CandidateEducation(candidate_id=candidate_id, institution="Existing Uni")]

    # await session.execute(...) → синхронный Result; .scalar_one_or_none() → candidate
    _result = MagicMock()
    _result.scalar_one_or_none.return_value = candidate
    session.execute = AsyncMock(return_value=_result)
    session.add = AsyncMock()
    session.flush = AsyncMock()

    # Act
    await parse_and_apply_resume(
        session=session,
        candidate_id=candidate_id,
        content=b"fake content",
        filename="resume.pdf",
        company_id=company_id
    )

    # Assert - никаких новых записей не должно быть добавлено
    session.add.assert_not_called()


@pytest.mark.asyncio
@patch('app.services.glafira.resume_parse.call_json')
@patch('app.services.glafira.resume_parse.extract_resume_text')
async def test_parse_handles_empty_text_gracefully(mock_extract_text, mock_call_json):
    """Тест: пустой текст (скан-PDF) обрабатывается корректно"""

    # Arrange
    mock_extract_text.return_value = None  # Пустой текст

    session = AsyncMock(spec=AsyncSession)
    candidate_id = uuid.uuid4()
    company_id = uuid.uuid4()

    # Act
    await parse_and_apply_resume(
        session=session,
        candidate_id=candidate_id,
        content=b"fake content",
        filename="scan.pdf",
        company_id=company_id
    )

    # Assert - парсер не должен вызываться
    mock_call_json.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.asyncio
@patch('app.services.glafira.resume_parse.call_json')
@patch('app.services.glafira.resume_parse.extract_resume_text')
async def test_parse_populates_extra_additional_fields(mock_extract_text, mock_call_json):
    """languages/relocation/business_trips/remote → candidate.extra (блок «Дополнительно» карточки)"""

    mock_extract_text.return_value = "resume content"
    mock_call_json.return_value = {
        "languages": ["Русский — Родной", "Английский — B1", "", None],  # пустые должны отфильтроваться
        "relocation": "Готов к переезду",
        "business_trips": "Не готов к командировкам",
        "remote": "Удалённо, на месте работодателя",
    }

    session = AsyncMock(spec=AsyncSession)
    candidate_id = uuid.uuid4()
    company_id = uuid.uuid4()
    candidate = Candidate(
        id=candidate_id, company_id=company_id,
        first_name="Иван", last_name="Иванов", source="manual"
    )
    candidate.experience = []
    candidate.skills = []
    candidate.education = []
    candidate.extra = {}

    # await session.execute(...) → синхронный Result; .scalar_one_or_none() → candidate
    _result = MagicMock()
    _result.scalar_one_or_none.return_value = candidate
    session.execute = AsyncMock(return_value=_result)
    session.add = AsyncMock()
    session.flush = AsyncMock()

    await parse_and_apply_resume(
        session=session, candidate_id=candidate_id,
        content=b"x", filename="r.pdf", company_id=company_id
    )

    assert candidate.extra["languages"] == ["Русский — Родной", "Английский — B1"]
    assert candidate.extra["relocation"] == "Готов к переезду"
    assert candidate.extra["business_trips"] == "Не готов к командировкам"
    assert candidate.extra["remote"] == "Удалённо, на месте работодателя"