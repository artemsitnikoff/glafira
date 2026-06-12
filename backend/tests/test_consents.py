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

    async def test_manager_cannot_request_consent(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: Candidate
    ):
        """Test that managers cannot request consent"""
        # Get manager token
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": manager_user.email, "password": "Glafira2026!"},
        )
        assert login_response.status_code == 200
        manager_token = login_response.json()["access_token"]
        manager_headers = {"Authorization": f"Bearer {manager_token}"}

        candidate_id = str(test_candidate.id)

        # Try to request consent as manager - should fail
        response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/request",
            headers=manager_headers,
            json={"channel": "telegram"}
        )

        assert response.status_code == 403
        error = response.json()
        assert "FORBIDDEN" in error["error"]["code"]
        assert "Менеджеры не могут запрашивать согласия" in error["error"]["message"]

    async def test_manager_cannot_confirm_signed_consent(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: Candidate
    ):
        """Test that managers cannot confirm signed consent"""
        # Get manager token
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": manager_user.email, "password": "Glafira2026!"},
        )
        assert login_response.status_code == 200
        manager_token = login_response.json()["access_token"]
        manager_headers = {"Authorization": f"Bearer {manager_token}"}

        candidate_id = str(test_candidate.id)

        # Try to confirm signed consent as manager - should fail
        response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/confirm-signed",
            headers=manager_headers
        )

        assert response.status_code == 403
        error = response.json()
        assert "FORBIDDEN" in error["error"]["code"]
        assert "Менеджеры не могут подтверждать" in error["error"]["message"]