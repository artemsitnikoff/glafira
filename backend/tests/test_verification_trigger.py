"""Tests for verification trigger in scoring"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.models import Verification, Consent, Application, Vacancy, User
from app.services.glafira.scoring import score_pending_applications


class TestVerificationTrigger:

    async def test_scoring_triggers_verification_with_signed_consent(
        self, db_session, test_candidate, signed_consent
    ):
        """Test that scoring triggers verification when candidate has signed consent"""

        # Create vacancy and application
        vacancy = Vacancy(
            company_id=test_candidate.company_id,
            name="Test Position",
            city="Москва",
            description="Test requirement",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Mock scoring response
        mock_scoring_response = {
            "score": 75,
            "verdict": "good",
            "summary": "Good candidate",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": [{"criterion": "Python", "weight": 50, "points": 40, "comment": "matches"}],
            "forecast": "Ready in 2 weeks",
            "questions": []
        }

        # Mock verification functions
        with patch('app.services.glafira.scoring.call_json', return_value=mock_scoring_response), \
             patch('app.services.glafira.verify.clean_phone', return_value=None), \
             patch('app.services.glafira.verify.clean_email', return_value=None), \
             patch('app.services.glafira.verify.clean_name', return_value=None), \
             patch('app.services.glafira.verify.claude_cli_complete', return_value=None):

            result = await score_pending_applications(
                db_session,
                company_id=test_candidate.company_id,
                limit=1
            )

            assert result["scored"] == 1
            assert result["failed"] == 0

            # Check that verification was also created
            verification_result = await db_session.execute(
                select(Verification).where(
                    Verification.candidate_id == test_candidate.id
                )
            )
            verification = verification_result.scalar_one()
            assert verification.candidate_id == test_candidate.id
            assert verification.consent_id == signed_consent.id

    async def test_scoring_skips_verification_without_consent(
        self, db_session, test_candidate
    ):
        """Test that scoring skips verification when no signed consent exists"""

        # Create vacancy and application
        vacancy = Vacancy(
            company_id=test_candidate.company_id,
            name="Test Position",
            city="Москва",
            description="Test requirement",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Mock scoring response
        mock_scoring_response = {
            "score": 75,
            "verdict": "good",
            "summary": "Good candidate",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": [{"criterion": "Python", "weight": 50, "points": 40, "comment": "matches"}],
            "forecast": "Ready in 2 weeks",
            "questions": []
        }

        with patch('app.services.glafira.scoring.call_json', return_value=mock_scoring_response):

            result = await score_pending_applications(
                db_session,
                company_id=test_candidate.company_id,
                limit=1
            )

            assert result["scored"] == 1
            assert result["failed"] == 0

            # Check that NO verification was created
            verification_result = await db_session.execute(
                select(Verification).where(
                    Verification.candidate_id == test_candidate.id
                )
            )
            verification = verification_result.scalar_one_or_none()
            assert verification is None

    async def test_scoring_skips_verification_if_already_exists(
        self, db_session, test_candidate, signed_consent
    ):
        """Test that scoring skips verification if one already exists"""

        # Create existing verification
        existing_verification = Verification(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            consent_id=signed_consent.id,
            checked_at=datetime.now(timezone.utc),  # NOT NULL, без server_default
            status="clean",
            blocks=[],
            is_mock=True
        )
        db_session.add(existing_verification)

        # Create vacancy and application
        vacancy = Vacancy(
            company_id=test_candidate.company_id,
            name="Test Position",
            city="Москва",
            description="Test requirement",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Mock scoring response
        mock_scoring_response = {
            "score": 75,
            "verdict": "good",
            "summary": "Good candidate",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": [{"criterion": "Python", "weight": 50, "points": 40, "comment": "matches"}],
            "forecast": "Ready in 2 weeks",
            "questions": []
        }

        with patch('app.services.glafira.scoring.call_json', return_value=mock_scoring_response):

            result = await score_pending_applications(
                db_session,
                company_id=test_candidate.company_id,
                limit=1
            )

            assert result["scored"] == 1
            assert result["failed"] == 0

            # Check that only ONE verification exists (the original one)
            verification_result = await db_session.execute(
                select(Verification).where(
                    Verification.candidate_id == test_candidate.id
                )
            )
            verifications = verification_result.scalars().all()
            assert len(verifications) == 1
            assert verifications[0].id == existing_verification.id

    async def test_scoring_continues_if_verification_fails(
        self, db_session, test_candidate, signed_consent
    ):
        """Test that scoring continues even if verification fails"""

        # Create vacancy and application
        vacancy = Vacancy(
            company_id=test_candidate.company_id,
            name="Test Position",
            city="Москва",
            description="Test requirement",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response"
        )
        db_session.add(application)
        await db_session.commit()

        # Mock scoring response
        mock_scoring_response = {
            "score": 75,
            "verdict": "good",
            "summary": "Good candidate",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": [{"criterion": "Python", "weight": 50, "points": 40, "comment": "matches"}],
            "forecast": "Ready in 2 weeks",
            "questions": []
        }

        with patch('app.services.glafira.scoring.call_json', return_value=mock_scoring_response), \
             patch('app.services.glafira.verify.verify_candidate', side_effect=Exception("Verification failed")):

            result = await score_pending_applications(
                db_session,
                company_id=test_candidate.company_id,
                limit=1
            )

            # Scoring should still succeed even if verification failed
            assert result["scored"] == 1
            assert result["failed"] == 0

            # Check that scoring result exists
            await db_session.refresh(test_candidate)
            assert test_candidate.ai_score == 75


class TestVerificationRBAC:
    """Test RBAC for verification endpoints"""

    async def test_manager_cannot_start_verification(
        self, async_client, manager_user: User, test_candidate
    ):
        """Test that managers cannot start verification (платный DaData + OSINT)"""
        # Get manager token
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": manager_user.email, "password": "Glafira2026!"},
        )
        assert login_response.status_code == 200
        manager_token = login_response.json()["access_token"]
        manager_headers = {"Authorization": f"Bearer {manager_token}"}

        candidate_id = str(test_candidate.id)

        # Try to start verification as manager - should fail
        response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/verify",
            headers=manager_headers
        )

        assert response.status_code == 403
        error = response.json()
        assert "FORBIDDEN" in error["error"]["code"]
        assert "Менеджеры не могут запускать верификацию" in error["error"]["message"]