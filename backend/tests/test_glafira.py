"""Tests for Glafira AI functionality"""

from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiEvaluation, Event, Verification, Vacancy, Application


class TestGlafiraScoring:

    async def test_scoring_with_mocked_claude_saves_ai_evaluation(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that AI scoring saves evaluation correctly"""

        # Create a test vacancy
        vacancy_data = {
            "name": "Python Developer",
            "city": "Москва",
            "description": "Требуется Python разработчик",
            "salary_from": 100000,
            "salary_to": 150000,
            "client_id": None
        }
        vacancy_response = await async_client.post(
            "/api/v1/vacancies",
            headers=auth_headers,
            json=vacancy_data
        )
        assert vacancy_response.status_code == 201
        vacancy_id = vacancy_response.json()["id"]

        # Create application manually in database
        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy_id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Mock Claude response
        mock_json_response = {
            "score": 78,
            "verdict": "good",
            "summary": "Хороший кандидат",
            "strengths": ["Python", "FastAPI"],
            "risks": ["нет опыта в Django"],
            "requirements_match": [{"criterion": "Python", "weight": 50, "points": 40, "comment": "соответствует"}],
            "forecast": "готов через 2 недели"
        }

        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_json_response

            response = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_id
                }
            )

            assert response.status_code == 201
            body = response.json()
            assert body['score'] == 78
            assert body['verdict'] == "good"
            assert body['summary'] == "Хороший кандидат"

        # Verify database records
        evaluation_result = await db_session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        evaluation = evaluation_result.scalar_one()
        assert evaluation.score == 78

        # Check candidate ai_score updated
        await db_session.refresh(test_candidate)
        assert test_candidate.ai_score == 78

        # Check application ai_score updated
        await db_session.refresh(application)
        assert application.ai_score == 78

        # Check event created
        event_result = await db_session.execute(
            select(Event).where(
                Event.type == 'score',
                Event.candidate_id == test_candidate.id
            )
        )
        event = event_result.scalar_one()
        assert event.actor_type == 'ai'

    async def test_scoring_parse_error_returns_502(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that Claude parse error returns 502"""

        # Create a test vacancy
        vacancy_data = {
            "name": "Python Developer",
            "city": "Москва",
            "description": "Требуется Python разработчик",
            "client_id": None
        }
        vacancy_response = await async_client.post(
            "/api/v1/vacancies",
            headers=auth_headers,
            json=vacancy_data
        )
        vacancy_id = vacancy_response.json()["id"]

        # Create application manually in database
        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy_id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Mock parse error from call_json
        from app.core.errors import GlafiraParseError

        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = GlafiraParseError(details={"raw": "Sorry, I cannot process this request", "reason": "Invalid JSON"})

            response = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_id
                }
            )

            assert response.status_code == 502
            assert response.json()['error']['code'] == 'GLAFIRA_PARSE_ERROR'

        # Verify no evaluation was saved
        evaluation_result = await db_session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        evaluation = evaluation_result.scalar_one_or_none()
        assert evaluation is None

    async def test_score_and_get_evaluation_per_vacancy_not_mixed(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that evaluations are properly isolated per vacancy"""

        # Create two test vacancies
        vacancy_a_data = {
            "name": "Python Developer A",
            "city": "Москва",
            "description": "Требуется Python разработчик для проекта A",
            "salary_from": 100000,
            "client_id": None
        }
        vacancy_a_response = await async_client.post(
            "/api/v1/vacancies",
            headers=auth_headers,
            json=vacancy_a_data
        )
        assert vacancy_a_response.status_code == 201
        vacancy_a_id = vacancy_a_response.json()["id"]

        vacancy_b_data = {
            "name": "Python Developer B",
            "city": "Москва",
            "description": "Требуется Python разработчик для проекта B",
            "salary_from": 120000,
            "client_id": None
        }
        vacancy_b_response = await async_client.post(
            "/api/v1/vacancies",
            headers=auth_headers,
            json=vacancy_b_data
        )
        assert vacancy_b_response.status_code == 201
        vacancy_b_id = vacancy_b_response.json()["id"]

        # Create two applications manually in database
        application_a = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy_a_id,
            stage="response"
        )
        application_b = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy_b_id,
            stage="response"
        )
        db_session.add(application_a)
        db_session.add(application_b)
        await db_session.commit()

        # Mock Claude responses with different scores
        mock_json_response_a = {
            "score": 70,
            "verdict": "good",
            "summary": "Подходит для A",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": [],
            "forecast": "2 недели"
        }

        mock_json_response_b = {
            "score": 90,
            "verdict": "good",
            "summary": "Отлично подходит для B",
            "strengths": ["Python", "FastAPI"],
            "risks": [],
            "requirements_match": [],
            "forecast": "1 неделя"
        }

        # Score for vacancy A
        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_json_response_a

            response_a = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_a_id
                }
            )

            assert response_a.status_code == 201
            body_a = response_a.json()
            assert body_a['score'] == 70
            assert body_a['summary'] == "Подходит для A"

        # Score for vacancy B
        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_json_response_b

            response_b = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_b_id
                }
            )

            assert response_b.status_code == 201
            body_b = response_b.json()
            assert body_b['score'] == 90
            assert body_b['summary'] == "Отлично подходит для B"

        # Verify evaluations are properly isolated
        eval_a_response = await async_client.get(
            f'/api/v1/candidates/{test_candidate.id}/evaluation?vacancy_id={vacancy_a_id}',
            headers=auth_headers
        )
        assert eval_a_response.status_code == 200
        eval_a_body = eval_a_response.json()
        assert eval_a_body['score'] == 70
        assert eval_a_body['summary'] == "Подходит для A"

        eval_b_response = await async_client.get(
            f'/api/v1/candidates/{test_candidate.id}/evaluation?vacancy_id={vacancy_b_id}',
            headers=auth_headers
        )
        assert eval_b_response.status_code == 200
        eval_b_body = eval_b_response.json()
        assert eval_b_body['score'] == 90
        assert eval_b_body['summary'] == "Отлично подходит для B"

        # Verify that two separate evaluations exist in database
        evaluations_result = await db_session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        evaluations = evaluations_result.scalars().all()
        assert len(evaluations) == 2

        mutually_exclusive = await async_client.get(
            f'/api/v1/candidates/{test_candidate.id}/evaluation?application_id={application_a.id}&vacancy_id={vacancy_a_id}',
            headers=auth_headers
        )
        assert mutually_exclusive.status_code == 400
        assert mutually_exclusive.json()['error']['code'] == 'VALIDATION_ERROR'


class TestGlafiraVerification:

    async def test_verify_without_consent_returns_403(
        self, async_client, auth_headers, test_candidate
    ):
        """Test that verification without consent returns 403"""

        response = await async_client.post(
            f'/api/v1/candidates/{test_candidate.id}/verify',
            headers=auth_headers
        )

        assert response.status_code == 403
        assert response.json()['error']['code'] == 'CONSENT_REQUIRED'

    async def test_verify_with_signed_consent_returns_full_verification(
        self, async_client, auth_headers, test_candidate, signed_consent, db_session
    ):
        """Test that verification with signed consent returns full result"""

        response = await async_client.post(
            f'/api/v1/candidates/{test_candidate.id}/verify',
            headers=auth_headers
        )

        assert response.status_code == 201
        body = response.json()

        # Check all required verification blocks are present
        # (contacts via DaData + честные госреестр-заглушки + OSINT-разведка)
        blocks = body['blocks']
        required_blocks = ['contacts', 'inn', 'fssp', 'bankruptcy', 'registries', 'alimony', 'public_expertise', 'mentions']

        # blocks is now a list of objects, not a dict
        block_keys = [block['key'] for block in blocks]

        for block_key in required_blocks:
            assert block_key in block_keys

        # Check each block has required fields
        for block in blocks:
            assert 'key' in block
            assert 'title' in block
            assert 'sources' in block
            assert 'status' in block
            assert 'data' in block
            assert block['status'] in ['clean', 'info', 'warn', 'risk']

        # Check overall status
        assert body['status'] in ['clean', 'info', 'warn', 'risk']

        # Verify database record
        verification_result = await db_session.execute(
            select(Verification).where(
                Verification.candidate_id == test_candidate.id
            )
        )
        verification = verification_result.scalar_one()
        assert verification.consent_id == signed_consent.id

        # Check event created with 'verify' type
        event_result = await db_session.execute(
            select(Event).where(
                Event.type == 'verify',
                Event.candidate_id == test_candidate.id
            )
        )
        event = event_result.scalar_one()
        assert event.actor_type == 'ai'

    async def test_get_nonexistent_verification_returns_404(
        self, async_client, auth_headers, test_candidate
    ):
        """Test getting non-existent verification returns 404"""

        response = await async_client.get(
            f'/api/v1/candidates/{test_candidate.id}/verification',
            headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()['error']['code'] == 'NOT_FOUND'


class TestGlafiraLLMClusterFixes:
    """Tests for LLM-cluster bugs #19 and #20"""

    async def test_scoring_validates_llm_structure_and_rejects_broken_data(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test #19: scoring validates structure of LLM response and rejects broken types"""

        # Create test vacancy
        vacancy_data = {
            "name": "Test Position",
            "city": "Москва",
            "description": "Test requirement",
            "client_id": None
        }
        vacancy_response = await async_client.post(
            "/api/v1/vacancies",
            headers=auth_headers,
            json=vacancy_data
        )
        assert vacancy_response.status_code == 201
        vacancy_id = vacancy_response.json()["id"]

        # Create application
        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy_id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Test with broken structure: requirements_match as string instead of array
        broken_response_1 = {
            "score": 85,
            "verdict": "good",
            "summary": "Хорошо",
            "strengths": ["навык"],
            "risks": ["риск"],
            "requirements_match": "строка вместо массива",  # Неправильный тип
            "forecast": "2 недели",
            "questions": ["вопрос"]
        }

        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = broken_response_1

            response = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_id
                }
            )

            assert response.status_code == 502
            assert response.json()['error']['code'] == 'GLAFIRA_PARSE_ERROR'
            assert "не прошёл валидацию схемы" in response.json()['error']['details']['reason']

        # Verify AiEvaluation was NOT created
        evaluations_result = await db_session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        evaluations = evaluations_result.scalars().all()
        assert len(evaluations) == 0

        # Test with another broken structure: strengths as numbers, forecast as null
        broken_response_2 = {
            "score": 75,
            "verdict": "partial",
            "summary": {"объект": "вместо строки"},  # Неправильный тип
            "strengths": [1, 2, 3],  # Числа вместо строк
            "risks": ["риск"],
            "requirements_match": [],
            "forecast": None,  # null вместо строки
            "questions": ["вопрос"]
        }

        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = broken_response_2

            response = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_id
                }
            )

            assert response.status_code == 502
            assert response.json()['error']['code'] == 'GLAFIRA_PARSE_ERROR'

        # Verify still no AiEvaluation created
        evaluations_result = await db_session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        evaluations = evaluations_result.scalars().all()
        assert len(evaluations) == 0

    async def test_scoring_accepts_valid_structure_and_creates_evaluation(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test #19: valid complete LLM structure passes and creates AiEvaluation"""

        # Create test vacancy
        vacancy_data = {
            "name": "Test Position",
            "city": "Москва",
            "description": "Test requirement",
            "client_id": None
        }
        vacancy_response = await async_client.post(
            "/api/v1/vacancies",
            headers=auth_headers,
            json=vacancy_data
        )
        assert vacancy_response.status_code == 201
        vacancy_id = vacancy_response.json()["id"]

        # Create application
        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy_id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Valid structure matching EvaluationOut schema
        valid_response = {
            "score": 85,
            "verdict": "good",
            "summary": "Отличный кандидат",
            "strengths": ["Python", "FastAPI"],
            "risks": ["мало опыта"],
            "requirements_match": [
                {
                    "criterion": "Python",
                    "weight": 50,
                    "points": 40,
                    "comment": "Хороший уровень"
                }
            ],
            "forecast": "2 недели",
            "questions": ["Опыт с async?"]
        }

        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = valid_response

            response = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_id
                }
            )

            assert response.status_code == 201
            body = response.json()
            assert body['score'] == 85
            assert body['verdict'] == "good"
            assert body['summary'] == "Отличный кандидат"

        # Verify AiEvaluation WAS created
        evaluations_result = await db_session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        evaluation = evaluations_result.scalar_one()
        assert evaluation.score == 85
        assert evaluation.verdict == "good"

    def test_scoring_prompt_contains_anti_injection_protection(self):
        """Test #20: scoring prompts contain anti-injection instructions"""
        from app.services.glafira.prompts import SCORING_SYSTEM_PROMPT, SCORING_USER_TEMPLATE

        # Check system prompt has anti-injection instruction
        assert "попытк" in SCORING_SYSTEM_PROMPT or "не инструкции" in SCORING_SYSTEM_PROMPT
        assert "манипуляци" in SCORING_SYSTEM_PROMPT

        # Check user template has data markers
        assert "<<<РЕЗЮМЕ_КАНДИДАТА" in SCORING_USER_TEMPLATE
        assert "<<<КОНЕЦ_РЕЗЮМЕ>>>" in SCORING_USER_TEMPLATE
        assert "<<<ОПИСАНИЕ_ВАКАНСИИ" in SCORING_USER_TEMPLATE
        assert "<<<КОНЕЦ_ОПИСАНИЯ>>>" in SCORING_USER_TEMPLATE

    def test_scoring_user_template_format_does_not_break(self):
        """Test #20: SCORING_USER_TEMPLATE.format() doesn't crash with KeyError"""
        from app.services.glafira.prompts import SCORING_USER_TEMPLATE

        # Test that all required placeholders work
        test_kwargs = {
            'vacancy_name': 'Test Vacancy',
            'vacancy_city': 'Москва',
            'vacancy_salary': '100k-150k RUB',
            'vacancy_description': 'Описание вакансии',
            'candidate_name': 'Тест Тестов',
            'candidate_city': 'СПб',
            'candidate_phone': '+7123456789',
            'candidate_email': 'test@test.com',
            'resume_text': 'Текст резюме',
            'experience_text': 'Опыт работы',
            'skills_text': 'Навыки',
            'salary_expectation': '120k RUB'
        }

        # This should not raise KeyError or IndexError
        formatted = SCORING_USER_TEMPLATE.format(**test_kwargs)

        # Check that data markers are preserved in formatted output
        assert "<<<РЕЗЮМЕ_КАНДИДАТА" in formatted
        assert "<<<КОНЕЦ_РЕЗЮМЕ>>>" in formatted
        assert "Текст резюме" in formatted