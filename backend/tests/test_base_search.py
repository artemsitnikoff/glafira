"""Тесты поиска по собственной базе кандидатов"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.services.base_search import (
    parse_query_to_criteria,
    search_base,
    search_by_vacancy,
    create_search_run,
    increment_added_to_funnel,
    get_candidates_count
)
from app.models import Candidate, CandidateSkill, BaseSearchRun, Vacancy
from app.core.errors import GlafiraParseError, NotFoundError


@pytest.mark.asyncio
class TestBaseSearch:

    async def test_parse_query_success(self):
        """Тест успешного парсинга запроса через LLM"""
        mock_response = {
            "role": "Python разработчик",
            "skills": ["Python", "Django", "PostgreSQL"],
            "experience": "3-5 лет",
            "city": "Москва",
            "salary_from": 150000,
            "salary_to": 200000
        }

        with patch('app.services.base_search.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await parse_query_to_criteria("Python разработчик в Москве, Django, 150-200k")

            assert result["role"] == "Python разработчик"
            assert result["skills"] == ["Python", "Django", "PostgreSQL"]
            assert result["city"] == "Москва"
            assert result["salary_from"] == 150000
            assert result["salary_to"] == 200000

    async def test_parse_query_fallback(self):
        """Тест fallback при ошибке LLM"""
        with patch('app.services.base_search.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = GlafiraParseError(details={"reason": "API error"})

            result = await parse_query_to_criteria("Python разработчик Django PostgreSQL")

            assert result["role"] == "Python разработчик Django PostgreSQL"
            assert "python" in result["skills"]
            assert "разработчик" in result["skills"]
            assert "django" in result["skills"]
            assert "postgresql" in result["skills"]
            assert result["city"] == ""
            assert result["salary_from"] is None

    async def test_search_base_by_skills(self, db_session, test_company, admin_user):
        """Тест поиска по навыкам"""
        # Создаём кандидатов
        candidate1 = Candidate(
            company_id=test_company.id,
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            last_position="Python Developer",
            city="Москва",
            ai_score=85
        )
        candidate2 = Candidate(
            company_id=test_company.id,
            last_name="Петров",
            first_name="Пётр",
            middle_name=None,
            last_position="Java Developer",
            city="Санкт-Петербург",
            ai_score=75
        )
        db_session.add_all([candidate1, candidate2])
        await db_session.flush()

        # Добавляем навыки
        skill1 = CandidateSkill(
            company_id=test_company.id,
            candidate_id=candidate1.id,
            skill="Python",
            order_index=0
        )
        skill2 = CandidateSkill(
            company_id=test_company.id,
            candidate_id=candidate1.id,
            skill="Django",
            order_index=1
        )
        skill3 = CandidateSkill(
            company_id=test_company.id,
            candidate_id=candidate2.id,
            skill="Java",
            order_index=0
        )
        db_session.add_all([skill1, skill2, skill3])
        await db_session.commit()

        # Поиск по Python
        result = await search_base(
            db_session,
            test_company.id,
            skills=["Python", "Django"]
        )

        assert result["total"] == 1
        assert len(result["results"]) == 1

        candidate_result = result["results"][0]
        assert candidate_result["full_name"] == "Иванов Иван Иванович"
        assert "Python" in candidate_result["matched_skills"]
        assert "Django" in candidate_result["matched_skills"]
        assert candidate_result["match_percent"] == 100  # 2/2 навыка совпали

    async def test_search_base_by_position(self, db_session, test_company):
        """Тест поиска по должности"""
        candidate = Candidate(
            company_id=test_company.id,
            last_name="Разработчиков",
            first_name="Андрей",
            last_position="Senior Python Developer",
            ai_score=90
        )
        db_session.add(candidate)
        await db_session.commit()

        result = await search_base(
            db_session,
            test_company.id,
            role="Python Developer"
        )

        assert result["total"] == 1
        assert result["results"][0]["last_position"] == "Senior Python Developer"

    async def test_search_base_by_city(self, db_session, test_company):
        """Тест поиска по городу"""
        candidate = Candidate(
            company_id=test_company.id,
            last_name="Москвич",
            first_name="Иван",
            city="Москва",
            ai_score=80
        )
        db_session.add(candidate)
        await db_session.commit()

        result = await search_base(
            db_session,
            test_company.id,
            city="Москва"
        )

        assert result["total"] == 1
        assert result["results"][0]["city"] == "Москва"

    async def test_search_base_by_salary(self, db_session, test_company):
        """Тест поиска по зарплате (включая NULL)"""
        candidate1 = Candidate(
            company_id=test_company.id,
            last_name="Богатый",
            first_name="Иван",
            salary_expectation=150000,
            ai_score=80
        )
        candidate2 = Candidate(
            company_id=test_company.id,
            last_name="Бедный",
            first_name="Пётр",
            salary_expectation=80000,
            ai_score=70
        )
        candidate3 = Candidate(
            company_id=test_company.id,
            last_name="Неопределённый",
            first_name="Василий",
            salary_expectation=None,
            ai_score=75
        )
        db_session.add_all([candidate1, candidate2, candidate3])
        await db_session.commit()

        # Поиск с минимальной зарплатой 100k
        result = await search_base(
            db_session,
            test_company.id,
            salary_from=100000
        )

        # Должны найти кандидата с 150k + кандидата с NULL зарплатой
        assert result["total"] == 2
        names = [r["full_name"] for r in result["results"]]
        assert "Богатый Иван" in names
        assert "Неопределённый Василий" in names

    async def test_company_isolation(self, db_session, test_company, admin_user):
        """Тест изоляции по company_id"""
        # Создаём другую компанию
        from app.models import Company
        other_company = Company(name="Другая компания")
        db_session.add(other_company)
        await db_session.flush()

        # Кандидат в нашей компании
        our_candidate = Candidate(
            company_id=test_company.id,
            last_name="Наш",
            first_name="Кандидат",
            ai_score=80
        )
        # Кандидат в другой компании
        other_candidate = Candidate(
            company_id=other_company.id,
            last_name="Чужой",
            first_name="Кандидат",
            ai_score=85
        )
        db_session.add_all([our_candidate, other_candidate])
        await db_session.commit()

        # Поиск от нашей компании
        result = await search_base(
            db_session,
            test_company.id
        )

        # Должны найти только нашего кандидата
        assert result["total"] == 1
        assert result["results"][0]["full_name"] == "Наш Кандидат"

    async def test_match_percentage_calculation(self, db_session, test_company):
        """Тест подсчёта процента совпадения навыков"""
        candidate = Candidate(
            company_id=test_company.id,
            last_name="Тестовый",
            first_name="Кандидат",
            ai_score=80
        )
        db_session.add(candidate)
        await db_session.flush()

        # Добавляем навыки: Python, Django
        skills = [
            CandidateSkill(
                company_id=test_company.id,
                candidate_id=candidate.id,
                skill="Python",
                order_index=0
            ),
            CandidateSkill(
                company_id=test_company.id,
                candidate_id=candidate.id,
                skill="Django",
                order_index=1
            )
        ]
        db_session.add_all(skills)
        await db_session.commit()

        # Ищем по навыкам [Python, Django, React] - должно быть 67% (2/3)
        result = await search_base(
            db_session,
            test_company.id,
            skills=["Python", "Django", "React"]
        )

        assert result["total"] == 1
        candidate_result = result["results"][0]
        assert candidate_result["match_percent"] == 67  # round(2/3*100)
        assert len(candidate_result["matched_skills"]) == 2
        assert "Python" in candidate_result["matched_skills"]
        assert "Django" in candidate_result["matched_skills"]

    async def test_search_by_vacancy(self, db_session, test_company, test_vacancy):
        """Тест поиска по критериям вакансии"""
        mock_filters = {
            "area": "Информационные технологии",
            "professional_role": "Программист, разработчик",
            "experience": "3–6 лет",
            "skills": ["Python", "Django"]
        }

        with patch('app.services.base_search.derive_vacancy_filters', new_callable=AsyncMock) as mock_derive:
            mock_derive.return_value = mock_filters

            # Создаём подходящего кандидата
            candidate = Candidate(
                company_id=test_company.id,
                last_name="Подходящий",
                first_name="Кандидат",
                last_position="Python Developer",
                ai_score=85
            )
            db_session.add(candidate)
            await db_session.flush()

            skill = CandidateSkill(
                company_id=test_company.id,
                candidate_id=candidate.id,
                skill="Python",
                order_index=0
            )
            db_session.add(skill)
            await db_session.commit()

            result = await search_by_vacancy(
                db_session,
                test_company.id,
                test_vacancy.id
            )

            assert result["total"] == 1
            assert result["vacancy_title"] == test_vacancy.name
            assert result["criteria"]["skills"] == ["Python", "Django"]

    async def test_search_run_crud(self, db_session, test_company):
        """Тест CRUD истории поиска"""
        # Создание записи
        run = await create_search_run(
            db_session,
            test_company.id,
            "prompt",
            "Python разработчик",
            None,
            5
        )
        await db_session.commit()

        assert run.search_type == "prompt"
        assert run.query_text == "Python разработчик"
        assert run.found == 5
        assert run.added_to_funnel == 0

        # Инкремент счётчика
        await increment_added_to_funnel(db_session, test_company.id, run.id)
        await db_session.commit()

        # Обновляем объект из БД
        await db_session.refresh(run)
        assert run.added_to_funnel == 1

    async def test_get_candidates_count(self, db_session, test_company):
        """Тест подсчёта кандидатов в базе"""
        # Создаём кандидатов
        candidates = [
            Candidate(
                company_id=test_company.id,
                last_name=f"Кандидат{i}",
                first_name="Тест",
                ai_score=80
            )
            for i in range(3)
        ]
        db_session.add_all(candidates)

        # Удалённый кандидат (не должен считаться)
        from datetime import datetime
        deleted_candidate = Candidate(
            company_id=test_company.id,
            last_name="Удалённый",
            first_name="Кандидат",
            deleted_at=datetime.utcnow(),
            ai_score=70
        )
        db_session.add(deleted_candidate)
        await db_session.commit()

        count = await get_candidates_count(db_session, test_company.id)
        assert count == 3  # Только не удалённые

    async def test_vacancy_not_found(self, db_session, test_company):
        """Тест обработки несуществующей вакансии"""
        fake_vacancy_id = uuid4()

        with pytest.raises(NotFoundError):
            await search_by_vacancy(
                db_session,
                test_company.id,
                fake_vacancy_id
            )

    async def test_run_not_found_increment(self, db_session, test_company):
        """Тест обработки несуществующей записи при инкременте"""
        fake_run_id = uuid4()

        with pytest.raises(NotFoundError):
            await increment_added_to_funnel(
                db_session,
                test_company.id,
                fake_run_id
            )