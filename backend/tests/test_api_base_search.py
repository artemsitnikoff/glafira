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

        assert data["found"] == 1
        assert data["total"] == 1
        assert len(data["results"]) == 1
        assert data["query_echo"] == "Python разработчик в Москве"
        assert data["vacancy_title"] is None

        candidate_data = data["results"][0]
        assert candidate_data["full_name"] == "Разработчиков Андрей"
        assert candidate_data["last_position"] == "Python Developer"
        assert candidate_data["city"] == "Москва"
        assert "Python" in candidate_data["matched_skills"]

        # Проверяем критерии
        criteria = data["criteria"]
        assert criteria["role"] == "Python Developer"
        assert criteria["skills"] == ["Python"]

        # Проверяем, что создалась запись истории
        assert "run_id" in data

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

        assert data["found"] == 1
        assert data["query_echo"] == test_vacancy.name
        assert data["vacancy_title"] == test_vacancy.name

        criteria = data["criteria"]
        assert criteria["skills"] == ["Python", "Django"]

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

        # Fallback должен найти кандидата по должности
        assert data["found"] >= 1

        # Критерии должны содержать оригинальный запрос
        criteria = data["criteria"]
        assert criteria["role"] == "Python Django разработчик"