"""Тесты поиска по собственной базе кандидатов"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.services.base_search import (
    parse_query_to_criteria,
    search_base,
    search_by_vacancy,
    increment_added_to_funnel,
    get_candidates_count,
    retrieve_base,
    cosine_to_percent,
    vector_retrieve_scored,
    get_base_search_run_status,
    vector_retrieve
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
            ai_score=85,
            source="manual"
        )
        candidate2 = Candidate(
            company_id=test_company.id,
            last_name="Петров",
            first_name="Пётр",
            middle_name=None,
            last_position="Java Developer",
            city="Санкт-Петербург",
            ai_score=75,
            source="manual"
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
            ai_score=90,
            source="manual"
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
            ai_score=80,
            source="manual"
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
            ai_score=80,
            source="manual"
        )
        candidate2 = Candidate(
            company_id=test_company.id,
            last_name="Бедный",
            first_name="Пётр",
            salary_expectation=80000,
            ai_score=70,
            source="manual"
        )
        candidate3 = Candidate(
            company_id=test_company.id,
            last_name="Неопределённый",
            first_name="Василий",
            salary_expectation=None,
            ai_score=75,
            source="manual"
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
            ai_score=80,
            source="manual"
        )
        # Кандидат в другой компании
        other_candidate = Candidate(
            company_id=other_company.id,
            last_name="Чужой",
            first_name="Кандидат",
            ai_score=85,
            source="manual"
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
            ai_score=80,
            source="manual"
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
                ai_score=85,
                source="manual"
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


    async def test_get_candidates_count(self, db_session, test_company):
        """Тест подсчёта кандидатов в базе"""
        # Создаём кандидатов
        candidates = [
            Candidate(
                company_id=test_company.id,
                last_name=f"Кандидат{i}",
                first_name="Тест",
                ai_score=80,
                source="manual"
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
            ai_score=70,
            source="manual"
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
    async def test_run_base_evaluate_basic(self, db_session, test_company):
        """Базовый тест функции _run_base_evaluate"""
        from app.services.base_search import _run_base_evaluate
        from unittest.mock import AsyncMock

        # Создаём run в статусе running
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            status="running",
            stage="rerank",
            found=1,
            to_evaluate=1,
            evaluated=0,
            criteria={"role": "Python", "skills": ["Python"], "city": "", "salary_from": None, "salary_to": None},
            results=[]
        )
        db_session.add(run)
        await db_session.commit()

        # Мокаем векторный поиск и AI по месту импорта в base_search
        with patch('app.services.base_search.vector_retrieve_scored') as mock_vector, \
             patch('app.services.base_search._load_candidates_for_rerank') as mock_load, \
             patch('app.services.base_search._rerank_candidates_with_progress') as mock_rerank, \
             patch('app.services.base_search.score_resume_dict') as mock_score, \
             patch('app.services.base_search.AsyncSessionLocal') as mock_session_class:

            # Мокаем векторный поиск - пустой результат, чтобы сработал SQL fallback
            mock_vector.return_value = []

            # Мокаем загрузку кандидатов - возвращаем минимальные данные
            mock_load.return_value = []

            # Мокаем rerank - возвращаем пустой список
            mock_rerank.return_value = []

            # Мокаем LLM-скоринг для детерминированности (офлайн)
            mock_score.return_value = {"score": 75}

            # Мокаем сессию для финализации - тот же паттерн что в test_smart_search.py
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            # Возвращаем тот же объект run, чтобы мутации применились к нему
            mock_session.get.return_value = run

            # Запускаем функцию - должна завершиться без exception
            await _run_base_evaluate(run.id, test_company.id, 1)

            # Проверяем, что run был финализирован корректно (ассертим на in-memory run)
            assert run.status == "done"  # Должен успешно завершиться
            assert run.stage == "done"   # Фаза завершена
            assert run.finished_at is not None  # Время финиша проставлено
            assert isinstance(run.results, list)  # Результаты есть (хотя бы пустой список)
            mock_session.commit.assert_called()  # Финализация сделала commit

    @pytest.mark.asyncio
    async def test_run_base_evaluate_timeout(self, db_session, test_company):
        """Тест что _run_base_evaluate финализирует run при таймауте"""
        from app.services.base_search import _run_base_evaluate
        from unittest.mock import AsyncMock
        import asyncio

        # Создаём run в статусе running
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            status="running",
            stage="evaluate",
            found=1,
            to_evaluate=1,
            evaluated=0,
            criteria={"role": "Python", "skills": ["Python"], "city": "", "salary_from": None, "salary_to": None},
            results=[]
        )
        db_session.add(run)
        await db_session.commit()

        with patch('app.services.base_search._calculate_evaluate_timeout') as mock_timeout, \
             patch('app.services.base_search.vector_retrieve_scored') as mock_vector, \
             patch('app.services.base_search.AsyncSessionLocal') as mock_session_class:

            # Мокаем таймаут на 1 секунду
            mock_timeout.return_value = 1

            # Мокаем векторный поиск чтобы висел дольше таймаута
            async def _slow_vector_operation(*args, **kwargs):
                await asyncio.sleep(2)  # Зависаем на 2 секунды (больше таймаута в 1 сек)
                return []

            mock_vector.side_effect = _slow_vector_operation

            # Мокаем сессию для финализации
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session.get.return_value = run

            # Вызываем функцию - должна поймать TimeoutError и финализировать
            await _run_base_evaluate(run.id, test_company.id, 1)

            # Проверяем что run был финализирован при таймауте
            assert run.status == "error"
            assert "таймаут" in run.error.lower()
            assert run.finished_at is not None
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_retrieve_base_prompt(self, db_session, test_company, admin_user):
        """Тест фазы RETRIEVE для поиска по промпту"""
        # Мокаем LLM
        with patch('app.services.base_search.parse_query_to_criteria') as mock_parse:
            # Настройка моков
            mock_parse.return_value = {
                "role": "разработчик",
                "skills": ["Python", "FastAPI"],
                "city": "Москва",
                "salary_from": 100000,
                "salary_to": None
            }

            result = await retrieve_base(
                db_session,
                test_company.id,
                "prompt",
                "Python разработчик в Москве",
                None,
                None
            )

            # Проверки нового контракта
            assert "run_id" in result
            assert "total" in result
            assert isinstance(result["total"], int)
            assert result["total"] >= 0

            # Проверяем, что создался run со статусом retrieved
            run_id = result["run_id"]
            run = await get_base_search_run_status(db_session, run_id, test_company.id)
            assert run is not None
            assert run.status == "retrieved"
            assert run.stage == "retrieve"
            assert run.results == []

    @pytest.mark.asyncio
    async def test_retrieve_base_vacancy(self, db_session, test_company, admin_user):
        """Тест фазы RETRIEVE для поиска по вакансии"""
        # Создаём тестовую вакансию
        from app.models import Vacancy
        vacancy = Vacancy(
            company_id=test_company.id,
            name="Python Developer",
            description="Требуется Python разработчик",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        with patch('app.services.base_search.derive_vacancy_filters') as mock_derive:
            mock_derive.return_value = {
                "professional_role": "разработчик",
                "skills": ["Python"],
                "city": "",
                "salary_from": None,
                "salary_to": None
            }

            result = await retrieve_base(
                db_session,
                test_company.id,
                "vacancy",
                "Python Developer",
                vacancy.id,
                None
            )

            # Проверки нового контракта
            assert "run_id" in result
            assert "total" in result
            assert isinstance(result["total"], int)

            # Проверяем, что создался run со статусом retrieved
            run_id = result["run_id"]
            run = await get_base_search_run_status(db_session, run_id, test_company.id)
            assert run is not None
            assert run.status == "retrieved"
            assert run.stage == "retrieve"
            assert run.vacancy_id == vacancy.id
            assert run.results == []

    @pytest.mark.asyncio
    async def test_reindex_batch_embedding(self, db_session, test_company):
        """Тест батчевого эмбеддинга при reindex_all_embeddings"""
        from app.services.base_search import reindex_all_embeddings
        from unittest.mock import AsyncMock, patch

        # Создаём несколько кандидатов
        candidates = []
        for i in range(3):
            candidate = Candidate(
                company_id=test_company.id,
                last_name=f"TestLast{i}",
                first_name=f"TestFirst{i}",
                resume_text=f"Test resume text {i}",
                source="manual"
            )
            db_session.add(candidate)
            candidates.append(candidate)

        await db_session.commit()

        # Мокаем embed_texts для проверки батчевого вызова
        fake_embeddings = [[0.1] * 384, [0.2] * 384, [0.3] * 384]

        def _session_local_returning(db_session):
            """Паттерн патча сессии как в tests/test_smart_search.py"""
            async_session_mock = AsyncMock()
            async_session_mock.return_value.__aenter__.return_value = db_session
            return async_session_mock

        with patch('app.services.base_search.embed_texts') as mock_embed_texts, \
             patch('app.services.base_search.AsyncSessionLocal', _session_local_returning(db_session)):

            mock_embed_texts.return_value = fake_embeddings

            # Запускаем переиндексацию
            await reindex_all_embeddings(test_company.id)

            # Проверяем, что embed_texts был вызван ОДИН раз с батчем текстов
            assert mock_embed_texts.call_count == 1
            call_args = mock_embed_texts.call_args[0]
            batch_texts = call_args[0]
            assert len(batch_texts) == 3  # Батч из 3 текстов
            assert all("Test resume text" in text for text in batch_texts)

    @pytest.mark.asyncio
    async def test_vector_retrieve_exists_optimization(self, db_session, test_company):
        """Тест оптимизации COUNT → EXISTS в vector_retrieve"""
        # Мокаем embed_query для возврата None (нет эмбеддинга)
        with patch('app.services.base_search.embed_query') as mock_embed:
            mock_embed.return_value = None

            result = await vector_retrieve(db_session, test_company.id, "test query", 10)

            # При отсутствии эмбеддинга должен вернуться пустой список
            assert result == []

        # Тест с валидным эмбеддингом но без записей в БД
        with patch('app.services.base_search.embed_query') as mock_embed:
            mock_embed.return_value = [0.1] * 384

            result = await vector_retrieve(db_session, test_company.id, "test query", 10)

            # При отсутствии записей в БД должен вернуться пустой список
            assert result == []