import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..core.errors import NotFoundError
from ..models import Candidate, Message, User, Vacancy, Application
from ..schemas.message import MessageOut, MessageCreate
from ..schemas.base import Paginated
from ..services.audit import audit


async def get_messages_paginated(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24,
    channel: str | None = None,
    application_id: UUID | None = None
) -> Paginated[MessageOut]:
    """Get paginated messages for candidate"""
    # Verify candidate exists
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    # Build filters
    filters = [Message.candidate_id == candidate_id]

    if channel:
        filters.append(Message.channel == channel)

    if application_id:
        filters.append(Message.application_id == application_id)

    # Count total
    from sqlalchemy import func
    count_result = await session.execute(
        select(func.count(Message.id)).where(and_(*filters))
    )
    total = count_result.scalar_one()

    # Main query
    stmt = (
        select(Message)
        .options(
            joinedload(Message.sender_user),
            joinedload(Message.application).joinedload(Application.vacancy)
        )
        .where(and_(*filters))
        .order_by(Message.sent_at.asc())  # Chronological order
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(stmt)
    messages = result.scalars().all()

    # Convert to MessageOut
    items = []
    for message in messages:
        sender_name = None
        if message.sender_user:
            sender_name = message.sender_user.full_name
        elif message.sender_type == "ai":
            sender_name = "Глафира"

        application_context = None
        vacancy_id = None
        if message.application and message.application.vacancy:
            application_context = f"Контекст: вакансия {message.application.vacancy.name}"
            vacancy_id = message.application.vacancy.id

        items.append(MessageOut(
            id=message.id,
            channel=message.channel,
            direction=message.direction,
            sender_type=message.sender_type,
            sender_name=sender_name,
            body=message.body,
            sent_at=message.sent_at,
            application_context=application_context,
            vacancy_id=vacancy_id
        ))

    pages = math.ceil(total / page_size) if total > 0 else 0

    return Paginated[MessageOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


async def send_message(
    session: AsyncSession,
    candidate_id: UUID,
    message_data: MessageCreate,
    company_id: UUID,
    actor_user_id: UUID
) -> MessageOut:
    """Send message to candidate"""
    # Verify candidate exists
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    # Get sender user
    user_result = await session.execute(
        select(User).where(User.id == actor_user_id)
    )
    user = user_result.scalar_one()

    now = datetime.now(timezone.utc)

    # Create message
    message = Message(
        company_id=company_id,
        candidate_id=candidate_id,
        application_id=message_data.application_id,
        channel=message_data.channel,
        direction="out",
        sender_type="recruiter",
        sender_user_id=actor_user_id,
        body=message_data.body,
        sent_at=now,
        created_at=now
    )

    session.add(message)

    # Audit
    await audit(
        session,
        action="send_message",
        entity_type="message",
        entity_id=message.id,
        after={
            "channel": message_data.channel,
            "body": message_data.body[:100] + "..." if len(message_data.body) > 100 else message_data.body
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()

    # Return MessageOut
    application_context = None
    vacancy_id = None
    if message_data.application_id:
        app_result = await session.execute(
            select(Application)
            .options(joinedload(Application.vacancy))
            .where(Application.id == message_data.application_id)
        )
        app = app_result.scalar_one_or_none()
        if app and app.vacancy:
            application_context = f"Контекст: вакансия {app.vacancy.name}"
            vacancy_id = app.vacancy.id

    return MessageOut(
        id=message.id,
        channel=message.channel,
        direction=message.direction,
        sender_type=message.sender_type,
        sender_name=user.full_name,
        body=message.body,
        sent_at=message.sent_at,
        application_context=application_context,
        vacancy_id=vacancy_id
    )