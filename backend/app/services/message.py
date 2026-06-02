import html
import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..core.errors import NotFoundError, ValidationError
from ..models import Candidate, Message, User, Vacancy, Application
from ..schemas.message import MessageOut, MessageCreate
from ..schemas.base import Paginated
from ..services.audit import audit
from ..services.chat_log import log_chat
from ..services.integrations.hh import client as hh_client
from ..services.integrations.hh.service import get_valid_access_token
from ..services.integrations.smtp.service import send_email
from ..services.integrations.smtp.templates import render_simple_email


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


async def _send_hh(session, company_id, candidate_id, message_data, validated_application) -> str | None:
    """Реальная отправка в hh через новый Chats API. Возвращает external_id (id сообщения hh) или None."""
    hh_chat_id = None
    hh_negotiation_id = None
    target_application = None

    if message_data.application_id:
        if validated_application:
            hh_chat_id = validated_application.hh_chat_id
            hh_negotiation_id = validated_application.hh_negotiation_id
            target_application = validated_application
    else:
        # Ищем любую заявку кандидата с chat_id/negotiation_id
        app_result = await session.execute(
            select(Application).where(
                Application.candidate_id == candidate_id,
                Application.company_id == company_id,
                Application.hh_negotiation_id.isnot(None),
            ).limit(1)
        )
        target_application = app_result.scalar_one_or_none()
        if target_application:
            hh_chat_id = target_application.hh_chat_id
            hh_negotiation_id = target_application.hh_negotiation_id

    access_token = await get_valid_access_token(session, company_id)

    # Ленивый бэкфилл chat_id из negotiation, если пуст
    if not hh_chat_id and hh_negotiation_id:
        negotiation_data = await hh_client.get_negotiation(access_token, hh_negotiation_id)
        chat_id_from_negotiation = negotiation_data.get("chat_id")
        if chat_id_from_negotiation:
            hh_chat_id = str(chat_id_from_negotiation)
            if target_application:
                target_application.hh_chat_id = hh_chat_id
                await session.flush()

    if not hh_chat_id:
        raise ValidationError("Канал hh недоступен: у кандидата нет чата hh")

    hh_response = await hh_client.send_chat_message(access_token, hh_chat_id, message_data.body)
    return hh_response.get("id") if isinstance(hh_response, dict) else None


async def _send_email(session, company_id, candidate, message_data, validated_application) -> None:
    """Реальная отправка письма кандидату через SMTP-ядро + единый шаблон писем."""
    if not candidate.email:
        raise ValidationError("Канал email недоступен: у кандидата нет email")
    subject = (
        f"Сообщение по вакансии «{validated_application.vacancy.name}»"
        if validated_application and validated_application.vacancy
        else "Новое сообщение от работодателя"
    )
    safe_body = html.escape(message_data.body).replace("\n", "<br>")
    body_html = render_simple_email(
        heading="Новое сообщение",
        body_html=f'<p style="margin:0;font-size:15px;line-height:1.6;color:#1A1F29;">{safe_body}</p>',
        preheader=message_data.body[:120],
    )
    await send_email(
        session,
        company_id,
        to=candidate.email,
        subject=subject,
        body_text=message_data.body,
        body_html=body_html,
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
    candidate = candidate_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Кандидат")

    # Validate application_id ownership if provided
    validated_application = None
    if message_data.application_id:
        app_result = await session.execute(
            select(Application)
            .options(joinedload(Application.vacancy))
            .where(
                Application.id == message_data.application_id,
                Application.company_id == company_id,
                Application.candidate_id == candidate_id
            )
        )
        validated_application = app_result.scalar_one_or_none()
        if not validated_application:
            raise NotFoundError("Заявка")

    # Get sender user
    user_result = await session.execute(
        select(User).where(User.id == actor_user_id)
    )
    user = user_result.scalar_one()

    now = datetime.now(timezone.utc)
    external_id = None
    channel = message_data.channel
    cand_name = candidate.full_name or "Кандидат"

    # Каналы с РЕАЛЬНОЙ отправкой: hh (Chats API) и email (SMTP-ядро + единый шаблон).
    # Прочие (telegram/max/whatsapp/sms) — пока только запись в карточку (рабочего API нет).
    # Упал реальный канал → лог + проброс, сообщение НЕ сохраняется (никакого фейка «отправлено»).
    if channel in ("hh", "email"):
        try:
            if channel == "hh":
                external_id = await _send_hh(session, company_id, candidate_id, message_data, validated_application)
            else:
                await _send_email(session, company_id, candidate, message_data, validated_application)
        except Exception as e:
            log_chat(f"{channel} → {cand_name} • НЕ отправлено: {e}")
            raise
        log_chat(f"{channel} → {cand_name} • отправлено")
    else:
        log_chat(f"{channel} → {cand_name} • сохранено (канал без реальной отправки)")

    # Create message (для hh/email — только после успешной реальной отправки)
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
        created_at=now,
        external_id=external_id
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

    # Return MessageOut with validated application context
    application_context = None
    vacancy_id = None
    if validated_application and validated_application.vacancy:
        application_context = f"Контекст: вакансия {validated_application.vacancy.name}"
        vacancy_id = validated_application.vacancy.id

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