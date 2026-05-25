import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Candidate, Message


class TestConsents:
    async def test_consent_request_then_sign(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_candidate: Candidate,
        db_session: AsyncSession
    ):
        """Test consent request creates pending consent and AI message, then sign works"""
        candidate_id = str(test_candidate.id)

        # Request consent
        response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/request",
            headers=auth_headers,
            json={"channel": "telegram"}
        )

        assert response.status_code == 201
        consent = response.json()
        assert consent["status"] == "pending"
        assert consent["candidate_id"] == candidate_id
        assert consent["channel"] == "telegram"
        assert consent["number"].startswith("PD-")
        assert consent["number"].endswith("/26")  # Current year suffix

        consent_id = consent["id"]

        # Check that AI message was created
        messages_result = await db_session.execute(
            select(Message).where(
                Message.candidate_id == test_candidate.id,
                Message.sender_type == "ai",
                Message.direction == "out"
            )
        )
        ai_messages = messages_result.scalars().all()
        assert len(ai_messages) == 1
        assert "согласие на обработку персональных данных" in ai_messages[0].body

        # Sign consent
        sign_response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/sign",
            headers=auth_headers
        )

        assert sign_response.status_code == 200
        signed_consent = sign_response.json()
        assert signed_consent["status"] == "signed"
        assert signed_consent["signed_at"] is not None

    async def test_has_pdn_flag(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_candidate: Candidate
    ):
        """Test has_pdn flag changes from False to True after consent signing"""
        candidate_id = str(test_candidate.id)

        # Check initial has_pdn = False
        response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        candidate = response.json()
        assert candidate["has_pdn"] is False

        # Request and sign consent
        consent_response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/request",
            headers=auth_headers,
            json={"channel": "telegram"}
        )
        assert consent_response.status_code == 201

        await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/sign",
            headers=auth_headers
        )

        # Check has_pdn = True
        response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        candidate = response.json()
        assert candidate["has_pdn"] is True