"""Tests for verification trigger in scoring"""

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.models import Verification, Consent, Application, Vacancy
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