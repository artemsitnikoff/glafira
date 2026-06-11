"""Тесты API поиска по собственной базе кандидатов"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models import Candidate, CandidateSkill, BaseSearchRun


@pytest.mark.asyncio
class TestBaseSearchAPI:

    async def test_base_search_prompt_success(self, async_client, auth_headers, test_company, db_session):
        """Тест успешного поиска по текстовому запросу"""
        # Создаём кандидата с навыками
        candidate = Candidate(
            company_id=test_company.id,
            last_name="Разработчиков",
            first_name="Андрей",
            last_position="Python Developer",
            city="Москва",
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

        # Мокаем парсинг LLM
        mock_criteria = {
            "role": "Python Developer",
            "skills": ["Python"],
            "city": "Москва",
            "experience": "",
            "salary_from": None,
            "salary_to": None
        }

        with patch('app.services.base_search.parse_query_to_criteria', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = mock_criteria

            response = await async_client.post(
                "/api/v1/smart/base/search",
                json={
                    "search_type": "prompt",
                    "query": "Python разработчик в Москве"
                },
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()

        # Новый API возвращает результаты синхронно
        assert "run_id" in data
        assert "found" in data
        assert "candidates" in data
        run_id = data["run_id"]

        # Должны найти 1 кандидата
        assert data["found"] == 1
        assert len(data["candidates"]) == 1
        candidate = data["candidates"][0]
        assert candidate["full_name"] == "Разработчиков Андрей"
        assert candidate["scored_by"] == "cosine"

        # Проверяем, что запись создалась в БД со статусом retrieved
        from app.services.base_search import get_base_search_run_status
        run = await get_base_search_run_status(db_session, run_id, test_company.id)
        assert run is not None
        assert run.search_type == "prompt"
        assert run.status == "retrieved"
        assert run.query_text == "Python разработчик в Москве"
        assert run.stage == "retrieve"

    async def test_base_search_vacancy_success(self, async_client, auth_headers, test_company, test_vacancy, db_session):
        """Тест поиска по критериям вакансии"""
        # Создаём кандидата
        candidate = Candidate(
            company_id=test_company.id,
            last_name="Соискатель",
            first_name="Иван",
            last_position="Backend Developer",
            ai_score=80
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

        # Мокаем фильтры из вакансии
        mock_filters = {
            "area": "IT",
            "professional_role": "Backend Developer",
            "experience": "3-5 лет",
            "skills": ["Python", "Django"]
        }

        with patch('app.services.base_search.derive_vacancy_filters', new_callable=AsyncMock) as mock_derive:
            mock_derive.return_value = mock_filters

            response = await async_client.post(
                "/api/v1/smart/base/search",
                json={
                    "search_type": "vacancy",
                    "vacancy_id": str(test_vacancy.id)
                },
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()

        # Новый API возвращает только run_id
        assert "run_id" in data
        run_id = data["run_id"]

        # Проверяем, что запись создалась в БД
        from app.services.base_search import get_base_search_run_status
        run = await get_base_search_run_status(db_session, run_id, test_company.id)
        assert run is not None
        assert run.search_type == "vacancy"
        assert run.vacancy_id == test_vacancy.id
        assert run.status == "retrieved"

    async def test_base_search_prompt_validation_error(self, async_client, auth_headers):
        """Тест валидации запроса - prompt без query"""
        response = await async_client.post(
            "/api/v1/smart/base/search",
            json={
                "search_type": "prompt"
                # query отсутствует
            },
            headers=auth_headers
        )

        assert response.status_code == 400
        assert "query" in response.json()["error"]["message"].lower()

    async def test_base_search_vacancy_validation_error(self, async_client, auth_headers):
        """Тест валидации запроса - vacancy без vacancy_id"""
        response = await async_client.post(
            "/api/v1/smart/base/search",
            json={
                "search_type": "vacancy"
                # vacancy_id отсутствует
            },
            headers=auth_headers
        )

        assert response.status_code == 400
        assert "vacancy_id" in response.json()["error"]["message"].lower()

    async def test_base_search_short_query_error(self, async_client, auth_headers):
        """Тест валидации короткого запроса"""
        response = await async_client.post(
            "/api/v1/smart/base/search",
            json={
                "search_type": "prompt",
                "query": "ab"  # < 3 символов
            },
            headers=auth_headers
        )

        assert response.status_code == 400

    async def test_base_search_manager_forbidden(self, async_client, test_company, manager_user, db_session):
        """Тест запрета доступа для менеджера"""
        from app.core.security import create_access_token

        # Авторизация под менеджером
        token = create_access_token({"sub": str(manager_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.post(
            "/api/v1/smart/base/search",
            json={
                "search_type": "prompt",
                "query": "Python разработчик"
            },
            headers=headers
        )

        assert response.status_code == 403

    async def test_get_base_runs_success(self, async_client, auth_headers, test_company, db_session):
        """Тест получения истории поиска"""
        # Создаём записи истории
        runs = [
            BaseSearchRun(
                company_id=test_company.id,
                search_type="prompt",
                query_text=f"Python разработчик {i}",
                found=i + 1,
                added_to_funnel=i
            )
            for i in range(3)
        ]
        db_session.add_all(runs)
        await db_session.commit()

        response = await async_client.get(
            "/api/v1/smart/base/runs",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 3
        # Проверяем сортировку по created_at desc
        assert data[0]["query_text"] == "Python разработчик 2"
        assert data[1]["query_text"] == "Python разработчик 1"

        # Проверяем структуру
        run_data = data[0]
        assert "id" in run_data
        assert run_data["search_type"] == "prompt"
        assert run_data["found"] == 3
        assert run_data["added_to_funnel"] == 2
        assert "created_at" in run_data

    async def test_get_base_count_success(self, async_client, auth_headers, test_company, db_session):
        """Тест получения количества кандидатов"""
        # Создаём кандидатов
        candidates = [
            Candidate(
                company_id=test_company.id,
                last_name=f"Кандидат{i}",
                first_name="Тест"
            )
            for i in range(5)
        ]
        db_session.add_all(candidates)
        await db_session.commit()

        response = await async_client.get(
            "/api/v1/smart/base/count",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["count"] == 5

    async def test_mark_added_success(self, async_client, auth_headers, test_company, db_session):
        """Тест отметки добавления в воронку"""
        # Создаём запись поиска
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            found=2,
            added_to_funnel=0
        )
        db_session.add(run)
        await db_session.commit()

        response = await async_client.post(
            f"/api/v1/smart/base/runs/{run.id}/mark-added",
            json={},
            headers=auth_headers
        )

        assert response.status_code == 204

        # Проверяем, что счётчик увеличился
        await db_session.refresh(run)
        assert run.added_to_funnel == 1

    async def test_mark_added_run_not_found(self, async_client, auth_headers):
        """Тест отметки несуществующей записи"""
        fake_run_id = uuid4()

        response = await async_client.post(
            f"/api/v1/smart/base/runs/{fake_run_id}/mark-added",
            json={},
            headers=auth_headers
        )

        assert response.status_code == 404

    async def test_company_isolation_in_api(self, async_client, auth_headers, test_company, db_session):
        """Тест изоляции данных разных компаний в API"""
        # Создаём другую компанию
        from app.models import Company, User
        other_company = Company(name="Другая компания")
        db_session.add(other_company)
        await db_session.flush()

        # Пользователь другой компании
        other_user = User(
            email="other@example.com",
            password_hash="fake",
            company_id=other_company.id,
            role="admin"
        )
        db_session.add(other_user)

        # Запись поиска другой компании
        other_run = BaseSearchRun(
            company_id=other_company.id,
            search_type="prompt",
            query_text="Java разработчик",
            found=1
        )
        db_session.add(other_run)
        await db_session.commit()

        # Запрос истории нашей компанией
        response = await async_client.get(
            "/api/v1/smart/base/runs",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Не должны видеть записи другой компании
        assert len(data) == 0

    async def test_fallback_llm_parsing(self, async_client, auth_headers, test_company, db_session):
        """Тест fallback при ошибке LLM"""
        # Создаём кандидата
        candidate = Candidate(
            company_id=test_company.id,
            last_name="Программист",
            first_name="Пётр",
            last_position="Python Django разработчик"
        )
        db_session.add(candidate)
        await db_session.commit()

        # Мокаем ошибку LLM и fallback
        with patch('app.services.base_search.call_json', new_callable=AsyncMock) as mock_call:
            from app.core.errors import GlafiraParseError
            mock_call.side_effect = GlafiraParseError(details={"reason": "API error"})

            response = await async_client.post(
                "/api/v1/smart/base/search",
                json={
                    "search_type": "prompt",
                    "query": "Python Django разработчик"
                },
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()

        # Новый API возвращает run_id даже при fallback
        assert "run_id" in data

    async def test_get_base_search_run_status_success(self, async_client, auth_headers, test_company, db_session):
        """Тест получения статуса выполнения поиска"""
        # Создаём run с результатами
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            status="done",
            stage="done",
            found=5,
            to_evaluate=3,
            evaluated=3,
            results=[{
                "id": str(uuid4()),
                "full_name": "Тестовый Кандидат",
                "age": 30,
                "last_position": "Python Developer",
                "last_company": "Tech Corp",
                "last_period": "2023-2024",
                "city": "Москва",
                "ai_score": 85,
                "source": "hh",
                "salary_expectation": 150000,
                "matched_skills": ["Python", "Django"],
                "all_skills": ["Python", "Django", "PostgreSQL"],
                "match_percent": 90,
                "has_pdn": True
            }],
            criteria={
                "role": "Python разработчик",
                "skills": ["Python", "Django"],
                "city": "Москва",
                "salary_from": None,
                "salary_to": None
            },
            query_echo="Python разработчик в Москве"
        )
        db_session.add(run)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/smart/base/runs/{run.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(run.id)
        assert data["status"] == "done"
        assert data["stage"] == "done"
        assert data["found"] == 5
        assert data["to_evaluate"] == 3
        assert data["evaluated"] == 3
        assert data["query_echo"] == "Python разработчик в Москве"
        assert len(data["results"]) == 1

        # Проверяем результат
        result = data["results"][0]
        assert result["full_name"] == "Тестовый Кандидат"
        assert result["match_percent"] == 90
        assert result["has_pdn"] is True

        # Проверяем критерии
        criteria = data["criteria"]
        assert criteria["role"] == "Python разработчик"
        assert criteria["skills"] == ["Python", "Django"]

    async def test_get_base_search_run_status_not_found(self, async_client, auth_headers):
        """Тест получения статуса несуществующего поиска"""
        fake_run_id = uuid4()

        response = await async_client.get(
            f"/api/v1/smart/base/runs/{fake_run_id}",
            headers=auth_headers
        )

        assert response.status_code == 404

    async def test_get_base_search_run_status_company_isolation(self, async_client, auth_headers, test_company, db_session):
        """Тест изоляции по company_id при получении статуса"""
        # Создаём другую компанию
        from app.models import Company
        other_company = Company(name="Другая компания")
        db_session.add(other_company)
        await db_session.flush()

        # Создаём run в другой компании
        other_run = BaseSearchRun(
            company_id=other_company.id,
            search_type="prompt",
            query_text="Java разработчик",
            status="done"
        )
        db_session.add(other_run)
        await db_session.commit()

        # Пытаемся получить чужой run
        response = await async_client.get(
            f"/api/v1/smart/base/runs/{other_run.id}",
            headers=auth_headers
        )

        assert response.status_code == 404

    async def test_get_base_search_run_status_manager_forbidden(self, async_client, test_company, manager_user, db_session):
        """Тест запрета доступа для менеджера к статусу поиска"""
        from app.core.security import create_access_token

        # Создаём run
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            status="done"
        )
        db_session.add(run)
        await db_session.commit()

        # Авторизация под менеджером
        token = create_access_token({"sub": str(manager_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            f"/api/v1/smart/base/runs/{run.id}",
            headers=headers
        )

        assert response.status_code == 403

    async def test_evaluate_search_success(self, async_client, auth_headers, test_company, db_session):
        """Тест успешного запуска фазы EVALUATE"""
        # Создаём run в статусе retrieved с результатами
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            status="retrieved",
            stage="retrieve",
            found=2,
            to_evaluate=0,
            evaluated=0,
            results=[
                {
                    "id": str(uuid4()),
                    "full_name": "Иванов Иван",
                    "scored_by": "cosine",
                    "match_percent": 80,
                    "matched_skills": ["Python"],
                    "all_skills": ["Python", "Django"]
                },
                {
                    "id": str(uuid4()),
                    "full_name": "Петров Пётр",
                    "scored_by": "cosine",
                    "match_percent": 70,
                    "matched_skills": ["Python"],
                    "all_skills": ["Python"]
                }
            ]
        )
        db_session.add(run)
        await db_session.commit()

        response = await async_client.post(
            f"/api/v1/smart/base/runs/{run.id}/evaluate",
            json={"evaluate_n": 2},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == str(run.id)

        # Проверяем, что статус изменился на running
        await db_session.refresh(run)
        assert run.status == "running"
        assert run.stage == "rerank"
        assert run.to_evaluate == 2

    async def test_evaluate_search_not_found(self, async_client, auth_headers, test_company):
        """Тест evaluate для несуществующего run"""
        fake_id = uuid4()

        response = await async_client.post(
            f"/api/v1/smart/base/runs/{fake_id}/evaluate",
            json={"evaluate_n": 1},
            headers=auth_headers
        )

        assert response.status_code == 404

    async def test_evaluate_search_empty_results(self, async_client, auth_headers, test_company, db_session):
        """Тест evaluate для run без результатов"""
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            status="retrieved",
            results=[]
        )
        db_session.add(run)
        await db_session.commit()

        response = await async_client.post(
            f"/api/v1/smart/base/runs/{run.id}/evaluate",
            json={"evaluate_n": 1},
            headers=auth_headers
        )

        assert response.status_code == 400
        assert "Нечего оценивать" in response.json()["detail"]

    async def test_evaluate_search_manager_forbidden(self, async_client, manager_user, test_company, db_session):
        """Тест запрета для менеджера на evaluate"""
        # Создаём run
        run = BaseSearchRun(
            company_id=test_company.id,
            search_type="prompt",
            query_text="Python разработчик",
            status="retrieved",
            results=[{"id": str(uuid4()), "scored_by": "cosine"}]
        )
        db_session.add(run)
        await db_session.commit()

        # Авторизация под менеджером
        from app.security import create_access_token
        token = create_access_token({"sub": str(manager_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.post(
            f"/api/v1/smart/base/runs/{run.id}/evaluate",
            json={"evaluate_n": 1},
            headers=headers
        )

        assert response.status_code == 403

    async def test_evaluate_search_company_isolation(self, async_client, auth_headers, test_company, db_session):
        """Тест изоляции по company_id для evaluate"""
        # Создаём другую компанию
        from app.models import Company
        other_company = Company(name="Другая компания")
        db_session.add(other_company)
        await db_session.flush()

        # Создаём run в другой компании
        run = BaseSearchRun(
            company_id=other_company.id,
            search_type="prompt",
            query_text="test",
            status="retrieved",
            results=[{"id": str(uuid4())}]
        )
        db_session.add(run)
        await db_session.commit()

        # Пытаемся evaluate чужой run
        response = await async_client.post(
            f"/api/v1/smart/base/runs/{run.id}/evaluate",
            json={"evaluate_n": 1},
            headers=auth_headers
        )

        assert response.status_code == 404