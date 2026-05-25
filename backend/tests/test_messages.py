import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Candidate


class TestMessages:
    async def test_send_and_list_messages(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_candidate: Candidate
    ):
        """Test sending message returns 201 and listing shows it"""
        candidate_id = str(test_candidate.id)

        # Send message
        response = await async_client.post(
            "/api/v1/messages",
            headers=auth_headers,
            params={"candidate_id": candidate_id},
            json={
                "channel": "telegram",
                "body": "Тестовое сообщение"
            }
        )

        assert response.status_code == 201
        message = response.json()
        assert message["body"] == "Тестовое сообщение"
        assert message["channel"] == "telegram"
        assert message["direction"] == "out"
        assert message["sender_type"] == "recruiter"

        # List messages
        list_response = await async_client.get(
            "/api/v1/messages",
            headers=auth_headers,
            params={"candidate_id": candidate_id}
        )

        assert list_response.status_code == 200
        messages_data = list_response.json()
        assert messages_data["total"] >= 1

        # Find our message
        messages = messages_data["items"]
        test_message = next((m for m in messages if m["body"] == "Тестовое сообщение"), None)
        assert test_message is not None
        assert test_message["channel"] == "telegram"
        assert test_message["sender_type"] == "recruiter"

        # Test with channel filter
        filter_response = await async_client.get(
            "/api/v1/messages",
            headers=auth_headers,
            params={
                "candidate_id": candidate_id,
                "channel": "telegram"
            }
        )

        assert filter_response.status_code == 200
        filtered_data = filter_response.json()
        filtered_messages = filtered_data["items"]
        telegram_message = next((m for m in filtered_messages if m["body"] == "Тестовое сообщение"), None)
        assert telegram_message is not None