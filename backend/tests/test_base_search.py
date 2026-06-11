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
    get_candidates_count,
    retrieve_base,
    cosine_to_percent,
    vector_retrieve_scored,
    get_base_search_run_status
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

    async def test_start_base_search_prompt(self, db_session, test_company):
        """Тест запуска асинхронного поиска по запросу"""
        mock_criteria = {
            "role": "Python разработчик",
            "skills": ["Python", "Django"],
            "experience": "",
            "city": "Москва",
            "salary_from": None,
            "salary_to": None
        }

        with patch('app.services.base_search.parse_query_to_criteria', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = mock_criteria

            # Запускаем поиск
            run_id = await start_base_search(
                db_session,
                test_company.id,
                "prompt",
                "Python разработчик в Москве",
                None
            )

            # Проверяем, что run создался
            run = await get_base_search_run_status(db_session, run_id, test_company.id)
            assert run is not None
            assert run.search_type == "prompt"
            assert run.status == "running"
            assert run.stage == "retrieve"
            assert run.query_text == "Python разработчик в Москве"
            assert run.criteria == mock_criteria

    async def test_start_base_search_vacancy(self, db_session, test_company, test_vacancy):
        """Тест запуска асинхронного поиска по вакансии"""
        mock_filters = {
            "professional_role": "Программист",
            "skills": ["Python"],
            "city": "",
            "salary_from": 100000,
            "salary_to": 150000
        }

        with patch('app.services.base_search.derive_vacancy_filters', new_callable=AsyncMock) as mock_derive:
            mock_derive.return_value = mock_filters

            # Запускаем поиск
            run_id = await start_base_search(
                db_session,
                test_company.id,
                "vacancy",
                "",
                test_vacancy.id
            )

            # Проверяем, что run создался
            run = await get_base_search_run_status(db_session, run_id, test_company.id)
            assert run is not None
            assert run.search_type == "vacancy"
            assert run.status == "running"
            assert run.vacancy_id == test_vacancy.id
            assert run.vacancy_title == test_vacancy.name

    async def test_start_base_search_vacancy_with_override(self, db_session, test_company, test_vacancy):
        """Тест запуска поиска по вакансии с переопределёнными критериями"""
        override_criteria = {
            "role": "Senior Python Developer",
            "skills": ["Python", "Django", "PostgreSQL"],
            "city": "СПб",
            "salary_from": 200000,
            "salary_to": 300000
        }

        # Запускаем поиск с override
        run_id = await start_base_search(
            db_session,
            test_company.id,
            "vacancy",
            "",
            test_vacancy.id,
            override_criteria
        )

        # Проверяем, что criteria из override
        run = await get_base_search_run_status(db_session, run_id, test_vacancy.company_id)
        assert run is not None
        assert run.criteria == override_criteria

    async def test_get_base_search_run_status_not_found(self, db_session, test_company):
        """Тест получения статуса несуществующего поиска"""
        fake_run_id = uuid4()

        run = await get_base_search_run_status(db_session, fake_run_id, test_company.id)
        assert run is None

    async def test_company_isolation_base_search(self, db_session, test_company):
        """Тест изоляции по company_id в асинхронном поиске"""
        # Создаём другую компанию
        from app.models import Company
        other_company = Company(name="Другая компания")
        db_session.add(other_company)
        await db_session.flush()

        # Создаём run в другой компании
        other_run = BaseSearchRun(
            company_id=other_company.id,
            search_type="prompt",
            query_text="test",
            status="done"
        )
        db_session.add(other_run)
        await db_session.commit()

        # Пытаемся получить чужой run от нашей компании
        run = await get_base_search_run_status(db_session, other_run.id, test_company.id)
        assert run is None  # Должны получить None из-за изоляции


class TestNewFunctions:
    """Тесты новых функций двухфазного поиска"""

    def test_cosine_to_percent(self):
        """Тест конвертации косинуса в процент"""
        assert cosine_to_percent(0.0) == 100  # Идеальное совпадение
        assert cosine_to_percent(1.0) == 0    # Полная противоположность
        assert cosine_to_percent(0.5) == 50   # 50% совпадения
        assert cosine_to_percent(0.2) == 80   # 80% совпадения
        assert cosine_to_percent(-0.1) == 100 # Обрезка снизу
        assert cosine_to_percent(1.1) == 0    # Обрезка сверху

    @pytest.mark.asyncio
    async def test_retrieve_base_prompt(self, db_session, test_company, admin_user):
        """Тест фазы RETRIEVE для поиска по промпту"""
        # Мокаем LLM
        with patch('app.services.base_search.parse_query_to_criteria') as mock_parse, \
             patch('app.services.base_search.search_base') as mock_search, \
             patch('app.services.base_search.vector_retrieve_scored') as mock_vector, \
             patch('app.services.base_search._load_candidates_for_rerank') as mock_load:

            # Настройка моков
            mock_parse.return_value = {
                "role": "разработчик",
                "skills": ["Python", "FastAPI"],
                "city": "Москва",
                "salary_from": 100000,
                "salary_to": None
            }

            mock_search.return_value = {
                "total": 2,
                "results": [
                    {"id": "550e8400-e29b-41d4-a716-446655440001"},
                    {"id": "550e8400-e29b-41d4-a716-446655440002"}
                ]
            }

            mock_vector.return_value = [
                (uuid4(), 0.2),  # 80% cosine
                (uuid4(), 0.4),  # 60% cosine
            ]

            # Мок данных кандидатов
            mock_candidate = AsyncMock()
            mock_candidate.id = uuid4()
            mock_candidate.last_name = "Иванов"
            mock_candidate.first_name = "Иван"
            mock_candidate.middle_name = "Иванович"
            mock_candidate.birth_date = None
            mock_candidate.last_position = "Python Developer"
            mock_candidate.last_company = "Tech Corp"
            mock_candidate.last_period = "2023-2024"
            mock_candidate.city = "Москва"
            mock_candidate.ai_score = 85
            mock_candidate.source = "hh"
            mock_candidate.salary_expectation = 120000

            mock_load.return_value = [{
                "candidate": mock_candidate,
                "skills": [AsyncMock(skill="Python"), AsyncMock(skill="FastAPI")],
                "has_pdn": True
            }]

            result = await retrieve_base(
                db_session,
                test_company.id,
                "prompt",
                "Python разработчик в Москве",
                None,
                None
            )

            # Проверки
            assert "run_id" in result
            assert "found" in result
            assert "candidates" in result
            assert len(result["candidates"]) > 0

            # Проверяем что кандидат имеет scored_by = "cosine"
            candidate = result["candidates"][0]
            assert candidate["scored_by"] == "cosine"
            assert "match_percent" in candidate

    @pytest.mark.asyncio
    async def test_retrieve_base_vacancy(self, db_session, test_company, admin_user):
        """Тест фазы RETRIEVE для поиска по вакансии"""
        # Создаём тестовую вакансию
        vacancy = Vacancy(
            company_id=test_company.id,
            name="Python Developer",
            description="Требуется Python разработчик",
            status="published"
        )
        db_session.add(vacancy)
        await db_session.flush()

        with patch('app.services.base_search.derive_vacancy_filters') as mock_derive, \
             patch('app.services.base_search.search_base') as mock_search, \
             patch('app.services.base_search._load_candidates_for_rerank') as mock_load:

            mock_derive.return_value = {
                "professional_role": "разработчик",
                "skills": ["Python"],
                "city": "",
                "salary_from": None,
                "salary_to": None
            }

            mock_search.return_value = {"total": 0, "results": []}
            mock_load.return_value = []

            result = await retrieve_base(
                db_session,
                test_company.id,
                "vacancy",
                "Python Developer",
                vacancy.id,
                None
            )

            assert result["found"] == 0
            assert result["candidates"] == []