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
            f"/api/v1/candidates/{candidate_id}/messages",
            headers=auth_headers,
            json={
                "channel": "sms",
                "body": "Тестовое сообщение"
            }
        )

        assert response.status_code == 201
        message = response.json()
        assert message["body"] == "Тестовое сообщение"
        assert message["channel"] == "sms"
        assert message["direction"] == "out"
        assert message["sender_type"] == "recruiter"

        # List messages
        list_response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}/messages",
            headers=auth_headers
        )

        assert list_response.status_code == 200
        messages_data = list_response.json()
        assert messages_data["total"] >= 1

        # Find our message
        messages = messages_data["items"]
        test_message = next((m for m in messages if m["body"] == "Тестовое сообщение"), None)
        assert test_message is not None
        assert test_message["channel"] == "sms"
        assert test_message["sender_type"] == "recruiter"

        # Test with channel filter
        filter_response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}/messages",
            headers=auth_headers,
            params={
                "channel": "sms"
            }
        )

        assert filter_response.status_code == 200
        filtered_data = filter_response.json()
        filtered_messages = filtered_data["items"]
        telegram_message = next((m for m in filtered_messages if m["body"] == "Тестовое сообщение"), None)
        assert telegram_message is not None


async def test_message_vacancy_id_from_application(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_candidate: Candidate,
    db_session: AsyncSession,
):
    """Test MessageOut includes vacancy_id from application.vacancy"""
    from app.models import Vacancy, Application

    # Create vacancy
    vacancy = Vacancy(
        company_id=test_candidate.company_id,
        name="Test Vacancy for Messages",
        status="active",
    )
    db_session.add(vacancy)
    await db_session.flush()

    # Create application
    application = Application(
        company_id=test_candidate.company_id,
        candidate_id=test_candidate.id,
        vacancy_id=vacancy.id,
        stage="response",
    )
    db_session.add(application)
    await db_session.flush()

    # Send message with application_id
    response = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/messages",
        headers=auth_headers,
        json={
            "channel": "sms",
            "body": "Message with application context",
            "application_id": str(application.id)
        }
    )
    assert response.status_code == 201

    # List messages and check vacancy_id
    list_response = await async_client.get(
        f"/api/v1/candidates/{test_candidate.id}/messages",
        headers=auth_headers
    )
    assert list_response.status_code == 200

    messages_data = list_response.json()
    test_message = next(
        (m for m in messages_data["items"] if m["body"] == "Message with application context"),
        None
    )
    assert test_message is not None
    assert test_message["vacancy_id"] == str(vacancy.id)
    assert test_message["application_context"] is not None
    assert "Test Vacancy for Messages" in test_message["application_context"]

async def test_send_message_audit_entity_id_is_message_id(
    db_session: AsyncSession,
    admin_user: User,
    test_candidate: Candidate,
):
    """send_message пишет audit с entity_id = message.id (НЕ NULL).

    id — server_default gen_random_uuid(); у pending-объекта он None → без flush
    перед audit() запись ушла бы с entity_id=NULL. Канал sms — без реальной отправки.
    """
    from sqlalchemy import select
    from app.services.message import send_message
    from app.schemas.message import MessageCreate
    from app.models import AuditLog, Message

    result = await send_message(
        db_session,
        test_candidate.id,
        MessageCreate(channel="sms", body="Привет"),
        admin_user.company_id,
        admin_user.id,
    )
    await db_session.flush()

    msg = (await db_session.execute(
        select(Message).where(Message.id == result.id)
    )).scalar_one()

    audit_row = (await db_session.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "message", AuditLog.action == "send_message")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )).scalar_one()

    assert audit_row.entity_id is not None
    assert audit_row.entity_id == msg.id
