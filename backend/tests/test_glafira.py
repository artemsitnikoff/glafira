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
        mock_response = type('Response', (), {
            'content': [type('Content', (), {
                'text': '{"score": 78, "verdict": "good", "summary": "Хороший кандидат", "strengths": ["Python", "FastAPI"], "risks": ["нет опыта в Django"], "requirements_match": {"Python": "соответствует"}, "forecast": "готов через 2 недели"}'
            })()]
        })()

        with patch('app.services.glafira.client.get_client') as mock_get:
            mock_client = mock_get.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response)

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

        # Mock invalid Claude response
        mock_response = type('Response', (), {
            'content': [type('Content', (), {
                'text': 'Sorry, I cannot process this request'
            })()]
        })()

        with patch('app.services.glafira.client.get_client') as mock_get:
            mock_client = mock_get.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response)

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
        mock_response_a = type('Response', (), {
            'content': [type('Content', (), {
                'text': '{"score": 70, "verdict": "good", "summary": "Подходит для A", "strengths": ["Python"], "risks": [], "requirements_match": {}, "forecast": "2 недели"}'
            })()]
        })()

        mock_response_b = type('Response', (), {
            'content': [type('Content', (), {
                'text': '{"score": 90, "verdict": "good", "summary": "Отлично подходит для B", "strengths": ["Python", "FastAPI"], "risks": [], "requirements_match": {}, "forecast": "1 неделя"}'
            })()]
        })()

        # Score for vacancy A
        with patch('app.services.glafira.client.get_client') as mock_get:
            mock_client = mock_get.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response_a)

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
        with patch('app.services.glafira.client.get_client') as mock_get:
            mock_client = mock_get.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response_b)

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
        blocks = body['blocks']
        required_blocks = ['inn', 'fssp', 'bankruptcy', 'registries', 'public', 'ai_intel', 'alimony']

        for block_key in required_blocks:
            assert block_key in blocks
            assert 'status' in blocks[block_key]
            assert 'summary' in blocks[block_key]
            assert 'details' in blocks[block_key]
            assert blocks[block_key]['status'] in ['clean', 'info', 'warn', 'risk']

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