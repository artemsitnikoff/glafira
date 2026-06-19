"""Тесты маппинга секций резюме hh при take_selected / invite_selected / build_candidate_resume_sections.

⚠️ ВСЕ ТЕСТЫ НА МОКАХ — реальных hh-вызовов нет.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from sqlalchemy import select

from app.services.integrations.hh.service import build_candidate_resume_sections
from app.services.smart_search import take_selected
from app.models import (
    Candidate, Application,
    CandidateExperience, CandidateSkill, CandidateEducation,
    SmartSearchRun,
)

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


def _make_resume_with_sections(
    resume_id: str = "res_sections",
    first_name: str = "Пётр",
    last_name: str = "Секционов",
) -> dict:
    """hh-резюме с опытом, навыками, образованием и зарплатой."""
    return {
        "id": resume_id,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": None,
        "title": "Backend-разработчик",
        "area": {"id": "1", "name": "Санкт-Петербург"},
        "contact": [
            {
                "type": {"id": "cell"},
                "value": {"formatted": "79111234567", "number": "79111234567"},
            },
            {
                "type": {"id": "email"},
                "value": "petr@sections.ru",
            },
        ],
        "salary": {"from": 150000, "to": 250000, "currency": "RUR"},
        "skills": "Python, FastAPI, PostgreSQL",
        "skill_set": ["Python", "FastAPI", "PostgreSQL"],
        "experience": [
            {
                "position": "Senior Backend Engineer",
                "company": "ООО Рога и Копыта",
                "start": "2021-03-01",
                "end": None,
                "description": "Разработка микросервисов на FastAPI",
            },
            {
                "position": "Python Developer",
                "company": "ИП Петров",
                "start": "2019-01-01",
                "end": "2021-02-28",
                "description": None,
            },
        ],
        "education": {
            "primary": [
                {
                    "name": "СПбГУ",
                    "organization": "Математико-механический факультет",
                    "result": "Прикладная математика",
                    "year": 2019,
                },
            ]
        },
    }


async def _create_run(db_session, company_id, vacancy_id) -> SmartSearchRun:
    run = SmartSearchRun(
        company_id=company_id,
        vacancy_id=vacancy_id,
        status="done",
        stage="done",
        params={"scan_n": 10},
        scored_candidates=[
            {"hh_resume_id": "res_sections", "name": "Пётр Секционов", "score": 85, "passed": True}
        ],
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Тест 1: build_candidate_resume_sections — юнит-тест хелпера
# ---------------------------------------------------------------------------

def test_build_candidate_resume_sections_basic():
    """Хелпер строит ORM-объекты из резюме: опыт / навыки / образование."""
    candidate_id = uuid4()
    company_id = uuid4()
    resume = _make_resume_with_sections()

    rows = build_candidate_resume_sections(candidate_id, company_id, resume)

    experiences = [r for r in rows if isinstance(r, CandidateExperience)]
    skills = [r for r in rows if isinstance(r, CandidateSkill)]
    educations = [r for r in rows if isinstance(r, CandidateEducation)]

    # Опыт: 2 записи
    assert len(experiences) == 2
    assert experiences[0].position == "Senior Backend Engineer"
    assert experiences[0].company == "ООО Рога и Копыта"
    assert experiences[0].period is not None  # "2021-03 — по наст. время"
    assert experiences[0].description == "Разработка микросервисов на FastAPI"
    assert experiences[0].order_index == 0
    assert experiences[0].candidate_id == candidate_id
    assert experiences[0].company_id == company_id

    assert experiences[1].position == "Python Developer"
    assert experiences[1].description is None
    assert experiences[1].order_index == 1

    # Навыки: 3 записи
    assert len(skills) == 3
    skill_names = {s.skill for s in skills}
    assert skill_names == {"Python", "FastAPI", "PostgreSQL"}
    for s in skills:
        assert s.candidate_id == candidate_id
        assert s.company_id == company_id

    # Образование: 1 запись
    assert len(educations) == 1
    assert educations[0].institution == "СПбГУ"
    assert educations[0].years == "2019"
    assert educations[0].candidate_id == candidate_id
    assert educations[0].company_id == company_id


def test_build_candidate_resume_sections_skips_empty_position():
    """Опыт с пустым position пропускается."""
    candidate_id = uuid4()
    company_id = uuid4()
    resume = {
        "experience": [
            {"position": "", "company": "ООО Тест", "start": None, "end": None},
            {"position": "  ", "company": "ООО Пусто", "start": None, "end": None},
            {"position": "Реальная должность", "company": "ООО Реальная", "start": None, "end": None},
        ],
        "skill_set": [],
        "education": {},
    }
    rows = build_candidate_resume_sections(candidate_id, company_id, resume)
    experiences = [r for r in rows if isinstance(r, CandidateExperience)]
    assert len(experiences) == 1
    assert experiences[0].position == "Реальная должность"


def test_build_candidate_resume_sections_skips_empty_skill():
    """Пустые навыки пропускаются."""
    candidate_id = uuid4()
    company_id = uuid4()
    resume = {
        "experience": [],
        "skill_set": ["Python", "", "  ", "FastAPI"],
        "education": {},
    }
    rows = build_candidate_resume_sections(candidate_id, company_id, resume)
    skills = [r for r in rows if isinstance(r, CandidateSkill)]
    assert len(skills) == 2
    assert {s.skill for s in skills} == {"Python", "FastAPI"}


def test_build_candidate_resume_sections_skips_empty_institution():
    """Образование с пустым name/organization пропускается."""
    candidate_id = uuid4()
    company_id = uuid4()
    resume = {
        "experience": [],
        "skill_set": [],
        "education": {
            "primary": [
                {"name": "", "organization": "", "result": "Что-то", "year": 2020},
                {"name": "МГУ", "organization": "Физфак", "result": "Физика", "year": 2022},
            ]
        },
    }
    rows = build_candidate_resume_sections(candidate_id, company_id, resume)
    educations = [r for r in rows if isinstance(r, CandidateEducation)]
    assert len(educations) == 1
    assert educations[0].institution == "МГУ"


def test_build_candidate_resume_sections_empty_resume():
    """Пустое резюме → пустой список (не падает)."""
    rows = build_candidate_resume_sections(uuid4(), uuid4(), {})
    assert rows == []


def test_build_candidate_resume_sections_truncates_fields():
    """Длинные поля обрезаются до [:255] / [:120] / [:40]."""
    candidate_id = uuid4()
    company_id = uuid4()
    long_str = "А" * 300
    resume = {
        "experience": [{"position": long_str, "company": long_str, "start": None, "end": None}],
        "skill_set": [long_str],
        "education": {"primary": [{"name": long_str, "organization": long_str, "year": 2020}]},
    }
    rows = build_candidate_resume_sections(candidate_id, company_id, resume)
    experiences = [r for r in rows if isinstance(r, CandidateExperience)]
    skills = [r for r in rows if isinstance(r, CandidateSkill)]
    educations = [r for r in rows if isinstance(r, CandidateEducation)]

    assert len(experiences[0].position) == 255
    assert len(experiences[0].company) == 255
    assert len(skills[0].skill) == 120
    assert len(educations[0].institution) == 255


# ---------------------------------------------------------------------------
# Тест 2: take_selected создаёт секции резюме + зарплатные поля
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.services.smart_search.hh_client.invite_to_vacancy")
@patch("app.services.smart_search.hh_client.get_resume_by_id")
@patch("app.services.smart_search.hh_service.get_valid_access_token")
@patch("app.services.smart_search.check_access")
@patch("app.services.smart_search.AsyncSessionLocal")
async def test_take_selected_creates_resume_sections(
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
    """take_selected при full_resume с experience/skill_set/education
    создаёт строки CandidateExperience / CandidateSkill / CandidateEducation
    с правильным company_id и привязкой к кандидату."""

    mock_session_local.side_effect = _session_local_returning(db_session)
    mock_check_access.return_value = (True, True, None)
    mock_token.return_value = "test_token"

    resume_id = "res_sections"
    full_resume = _make_resume_with_sections(resume_id=resume_id)
    mock_get_resume.return_value = full_resume

    run = await _create_run(db_session, test_company.id, test_vacancy.id)

    result = await take_selected(
        db_session,
        test_company.id,
        admin_user.id,
        run.id,
        [resume_id],
    )

    assert result["taken_count"] == 1
    candidate_id = result["results"][0]["candidate_id"]

    # Опыт: 2 записи
    exp_result = await db_session.execute(
        select(CandidateExperience).where(CandidateExperience.candidate_id == candidate_id)
    )
    experiences = exp_result.scalars().all()
    assert len(experiences) == 2
    assert any(e.position == "Senior Backend Engineer" for e in experiences)
    assert all(e.company_id == test_company.id for e in experiences)

    # Навыки: 3 записи
    skill_result = await db_session.execute(
        select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)
    )
    skills = skill_result.scalars().all()
    assert len(skills) == 3
    assert {s.skill for s in skills} == {"Python", "FastAPI", "PostgreSQL"}
    assert all(s.company_id == test_company.id for s in skills)

    # Образование: 1 запись
    edu_result = await db_session.execute(
        select(CandidateEducation).where(CandidateEducation.candidate_id == candidate_id)
    )
    educations = edu_result.scalars().all()
    assert len(educations) == 1
    assert educations[0].institution == "СПбГУ"
    assert educations[0].company_id == test_company.id

    # Зарплата + last_company
    candidate = await db_session.get(Candidate, candidate_id)
    assert candidate.salary_from == 150000
    assert candidate.salary_to == 250000
    assert candidate.salary_expectation == 150000  # синхронен с salary_from
    assert candidate.currency == "RUR"
    assert candidate.last_company == "ООО Рога и Копыта"

    # invite_to_vacancy НЕ вызывался
    mock_invite.assert_not_called()
