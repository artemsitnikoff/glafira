"""Tests for Glafira AI safety and security features"""

from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiEvaluation, Message, Verification, Vacancy, Application
from app.core.errors import GlafiraParseError, FeatureNotImplementedError


class TestGlafiraSafety:

    async def test_scoring_invalid_response_returns_502(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that invalid LLM response returns 502 and doesn't create fake records"""

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

        # Mock invalid Claude response (wrong score type)
        mock_invalid_response = {
            "score": "abc",  # Invalid - should be int
            "verdict": "wrong",  # Invalid - not in allowed values
            "summary": "Test summary",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": {},
            "forecast": "2 weeks"
        }

        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_invalid_response

            response = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_id
                }
            )

            assert response.status_code == 502
            assert response.json()["error"]["code"] == "GLAFIRA_PARSE_ERROR"

        # Verify NO fake records were created in database
        evaluation_count = await db_session.execute(
            select(func.count(AiEvaluation.id)).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        count = evaluation_count.scalar_one()
        assert count == 0  # No fake evaluation records

    async def test_scoring_missing_field_returns_502(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that missing required field returns 502 and doesn't create fake records"""

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
        assert vacancy_response.status_code == 201
        vacancy_id = vacancy_response.json()["id"]

        # Mock Claude response missing required field
        mock_response_missing_field = {
            "score": 75,
            "verdict": "good",
            # Missing required fields: summary, strengths, risks, requirements_match, forecast
            "summary": "Test"
        }

        with patch('app.services.glafira.scoring.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response_missing_field

            response = await async_client.post(
                '/api/v1/glafira/score',
                headers=auth_headers,
                json={
                    'candidate_id': str(test_candidate.id),
                    'vacancy_id': vacancy_id
                }
            )

            assert response.status_code == 502
            assert response.json()["error"]["code"] == "GLAFIRA_PARSE_ERROR"
            assert "Missing required field" in response.json()["error"]["details"]["reason"]

        # Verify NO records were created
        evaluation_count = await db_session.execute(
            select(func.count(AiEvaluation.id)).where(
                AiEvaluation.candidate_id == test_candidate.id
            )
        )
        assert evaluation_count.scalar_one() == 0

    async def test_screening_llm_error_returns_502_no_fake_message(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that LLM parse error returns 502 and doesn't create fake message"""

        # Mock call_json to raise GlafiraParseError
        with patch('app.services.glafira.screening.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = GlafiraParseError(details={"reason": "test_error"})

            response = await async_client.post(
                '/api/v1/glafira/screening/start',
                headers=auth_headers,
                json={"candidate_id": str(test_candidate.id)}
            )

            assert response.status_code == 502
            assert response.json()["error"]["code"] == "GLAFIRA_PARSE_ERROR"

        # Verify NO fake greeting messages were created
        fake_message_count = await db_session.execute(
            select(func.count(Message.id)).where(
                Message.candidate_id == test_candidate.id,
                Message.body == "Привет! Готовы начать скрининг?"
            )
        )
        count = fake_message_count.scalar_one()
        assert count == 0  # No fake greeting message

        # Verify NO messages at all were created for this candidate
        all_message_count = await db_session.execute(
            select(func.count(Message.id)).where(
                Message.candidate_id == test_candidate.id
            )
        )
        total_count = all_message_count.scalar_one()
        assert total_count == 0

    async def test_screening_missing_message_field_returns_502(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that missing 'message' field returns 502 and doesn't create fake message"""

        # Mock Claude response missing 'message' field
        mock_response_no_message = {
            "finished": False,
            "extracted": {}
            # Missing required 'message' field
        }

        with patch('app.services.glafira.screening.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response_no_message

            response = await async_client.post(
                '/api/v1/glafira/screening/start',
                headers=auth_headers,
                json={"candidate_id": str(test_candidate.id)}
            )

            assert response.status_code == 502
            assert response.json()["error"]["code"] == "GLAFIRA_PARSE_ERROR"
            assert "Missing 'message' field" in response.json()["error"]["details"]["reason"]

        # Verify NO messages were created
        message_count = await db_session.execute(
            select(func.count(Message.id)).where(
                Message.candidate_id == test_candidate.id
            )
        )
        assert message_count.scalar_one() == 0

    async def test_verify_legacy_mode_ignored_runs_real(
        self, async_client, auth_headers, test_candidate, signed_consent, db_session, monkeypatch
    ):
        """GLAFIRA_VERIFY_MODE — legacy: verify_candidate его НЕ смотрит. Проверка реальная
        (is_mock=False), запись создаётся. (Старый стаб возвращал 501 — этого больше нет.)"""
        from app.config import settings
        monkeypatch.setattr(settings, 'GLAFIRA_VERIFY_MODE', 'real')

        response = await async_client.post(
            f'/api/v1/candidates/{test_candidate.id}/verify',
            headers=auth_headers
        )

        # Реальная (частичная) верификация выполняется независимо от legacy-флага
        assert response.status_code == 201
        assert response.json()["is_mock"] is False

        verification_count = await db_session.execute(
            select(func.count(Verification.id)).where(
                Verification.candidate_id == test_candidate.id
            )
        )
        assert verification_count.scalar_one() == 1

    async def test_verification_response_has_is_mock_false(
        self, async_client, auth_headers, test_candidate, signed_consent, db_session
    ):
        """Верификация частично РЕАЛЬНАЯ (DaData/OSINT) → is_mock=False везде (ответ/GET/БД)."""

        response = await async_client.post(
            f'/api/v1/candidates/{test_candidate.id}/verify',
            headers=auth_headers
        )

        assert response.status_code == 201
        body = response.json()
        assert "is_mock" in body
        assert body["is_mock"] is False

        # Test GET endpoint also returns is_mock
        verification_id = body["id"]
        get_response = await async_client.get(
            f'/api/v1/candidates/{test_candidate.id}/verification',
            headers=auth_headers
        )

        assert get_response.status_code == 200
        get_body = get_response.json()
        assert "is_mock" in get_body
        assert get_body["is_mock"] is False

        # Verify database record has is_mock set correctly
        verification_result = await db_session.execute(
            select(Verification).where(
                Verification.candidate_id == test_candidate.id
            )
        )
        verification = verification_result.scalar_one()
        assert verification.is_mock is False

    async def test_screening_reply_missing_message_field_returns_502(
        self, async_client, auth_headers, test_candidate, db_session
    ):
        """Test that screening reply with missing 'message' field returns 502"""

        # Mock Claude response missing 'message' field for reply
        mock_response_no_message = {
            "finished": False,
            "extracted": {}
            # Missing required 'message' field
        }

        with patch('app.services.glafira.screening.call_json', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response_no_message

            response = await async_client.post(
                '/api/v1/glafira/screening/reply',
                headers=auth_headers,
                json={"candidate_id": str(test_candidate.id), "message": "Test candidate message"}
            )

            assert response.status_code == 502
            assert response.json()["error"]["code"] == "GLAFIRA_PARSE_ERROR"
            assert "Missing 'message' field" in response.json()["error"]["details"]["reason"]

        # Verify NO fake AI reply messages were created
        fake_reply_count = await db_session.execute(
            select(func.count(Message.id)).where(
                Message.candidate_id == test_candidate.id,
                Message.body == "Понятно, спасибо за ответ!"
            )
        )
        count = fake_reply_count.scalar_one()
        assert count == 0

        # Note: The candidate's incoming message should still be saved before the LLM call fails
        # But no AI response message should be created
        ai_message_count = await db_session.execute(
            select(func.count(Message.id)).where(
                Message.candidate_id == test_candidate.id,
                Message.sender_type == 'ai'
            )
        )
        ai_count = ai_message_count.scalar_one()
        assert ai_count == 0  # No AI messages created