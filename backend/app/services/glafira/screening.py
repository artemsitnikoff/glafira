"""Чат-скрининг кандидатов"""

from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .client import call_json
from .prompts import build_screening_system_prompt
from ..settings.glafira import get_company_openrouter_key
from ...core.errors import NotFoundError, GlafiraParseError
from ...models import Application, Candidate, Vacancy, Message, Event, GlafiraSettings
from ...services.audit import audit
from ...services.company_display import resolve_company_display_name


def _get_tone_description(tone: str) -> str:
    """Get tone description for prompt"""
    descriptions = {
        'friendly': 'дружелюбный, неформальный стиль общения',
        'formal': 'официальный, вежливый стиль общения',
        'business': 'деловой, прямой стиль общения'
    }
    return descriptions.get(tone, 'деловой стиль общения')


def _get_address_mode(use_informal: bool) -> str:
    """Get address mode for prompt"""
    return "на ты" if use_informal else "на вы"


def _get_emoji_description(emoji_level: str) -> str:
    """Get emoji usage description"""
    levels = {
        'none': 'не использовать эмодзи',
        'minimal': 'минимальное использование эмодзи',
        'moderate': 'умеренное использование эмодзи',
        'active': 'активное использование эмодзи'
    }
    return levels.get(emoji_level, 'умеренное использование эмодзи')


async def start_screening(
    session: AsyncSession,
    *,
    candidate_id: UUID,
    application_id: UUID | None = None,
    script_key: str | None = None,
    company_id: UUID,
    actor_user_id: UUID
) -> dict:
    """Start screening conversation for a candidate"""

    # Get candidate
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

    # Get application and vacancy if application_id provided
    application = None
    vacancy = None
    if application_id is not None:
        app_result = await session.execute(
            select(Application)
            .options(joinedload(Application.vacancy))
            .where(
                Application.id == application_id,
                Application.candidate_id == candidate_id,
                Application.company_id == company_id
            )
        )
        application = app_result.scalar_one_or_none()
        if not application:
            raise NotFoundError("Заявка")
        vacancy = application.vacancy

    # Get glafira settings
    settings_result = await session.execute(
        select(GlafiraSettings).where(GlafiraSettings.company_id == company_id)
    )
    glafira_settings = settings_result.scalar_one_or_none()

    # Use default settings if not found
    if not glafira_settings:
        tone = 'business'
        use_informal = False
        emoji_level = 'moderate'
    else:
        tone = glafira_settings.tone
        use_informal = glafira_settings.use_informal
        emoji_level = glafira_settings.emoji_level

    # Компания вакансии (заказчик → фолбэк на арендатора): Глафира должна называть
    # кандидату компанию, для которой ведёт подбор. Без вакансии — компания-арендатор.
    company_name = await resolve_company_display_name(session, company_id, vacancy)

    # Build system prompt
    system_prompt = build_screening_system_prompt(
        company_name=company_name,
        tone=tone,
        tone_description=_get_tone_description(tone),
        address_mode=_get_address_mode(use_informal),
        emoji_level=_get_emoji_description(emoji_level)
    )

    # Create user prompt. Компания пуста (не определилась) → не оставляем дырку «компании «»».
    _co = (company_name or "").strip()
    if vacancy is not None:
        context_text = (
            f'на вакансию "{vacancy.name}" компании «{_co}»' if _co
            else f'на вакансию "{vacancy.name}"'
        )
    else:
        context_text = f'(общий скрининг, компания «{_co}»)' if _co else '(общий скрининг)'

    user_prompt = f"""Начни скрининг кандидата {context_text}.

Информация о кандидате:
- Имя: {candidate.full_name}
- Город: {candidate.city or "не указан"}
- Последнее место работы: {candidate.last_company or "не указано"}
- Последняя должность: {candidate.last_position or "не указана"}
- Ожидания по ЗП: {candidate.salary_expectation or "не указано"}

Поприветствуй кандидата и начни беседу. Цель — понять мотивацию, опыт и готовность к работе.
Верни JSON в формате: {{"message": "текст ответа", "finished": false, "extracted": {{}}}}"""

    # Резолвим API-ключ компании
    api_key = await get_company_openrouter_key(session, company_id)

    # Call Claude API
    response_data = await call_json(
        system=system_prompt,
        user=user_prompt,
        api_key=api_key,
        max_tokens=1024
    )

    # Validate required fields - no fallbacks, strict validation
    if "message" not in response_data:
        raise GlafiraParseError(details={
            "reason": "Missing 'message' field in LLM response",
            "got": list(response_data.keys())
        })

    ai_response = response_data["message"]
    finished = response_data.get("finished", False)
    extracted = response_data.get("extracted", {})

    # Create outgoing message
    now = datetime.now(timezone.utc)
    message = Message(
        company_id=company_id,
        candidate_id=candidate.id,
        application_id=application_id,
        channel=candidate.preferred_channel or 'telegram',
        direction='out',
        sender_type='ai',
        sender_user_id=None,
        body=ai_response,
        sent_at=now,
        created_at=now
    )

    session.add(message)

    # Create event
    event = Event(
        company_id=company_id,
        type='new',  # Using existing type for conversation start
        actor_type='ai',
        actor_user_id=actor_user_id,
        text=f"Глафира начала скрининг кандидата {candidate.full_name}",
        entities=[
            {"type": "candidate", "id": str(candidate.id), "label": candidate.full_name},
        ] + ([{"type": "vacancy", "id": str(vacancy.id), "label": vacancy.name}] if vacancy else []) + [
            {"type": "message", "id": str(message.id), "label": "Начало скрининга"}
        ],
        candidate_id=candidate.id,
        vacancy_id=vacancy.id if vacancy else None,
        created_at=now
    )
    session.add(event)

    # Audit log
    await audit(
        session,
        action='start_screening',
        entity_type='message',
        entity_id=message.id,
        after={
            'candidate_id': str(candidate.id),
            'application_id': str(application_id) if application_id else None,
            'body_length': len(ai_response)
        },
        actor_user_id=actor_user_id,
        actor_type='ai',
        company_id=company_id,
    )

    await session.flush()
    return {
        "message": ai_response,
        "finished": finished,
        "extracted": extracted
    }


async def reply_screening(
    session: AsyncSession,
    *,
    candidate_id: UUID,
    message: str,
    company_id: UUID,
    actor_user_id: UUID
) -> dict:
    """Reply to candidate message in screening conversation"""

    # Get candidate
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

    # Save incoming candidate message first
    now = datetime.now(timezone.utc)
    incoming_msg = Message(
        company_id=company_id,
        candidate_id=candidate.id,
        application_id=None,  # No longer tied to specific application
        channel=candidate.preferred_channel or 'telegram',
        direction='in',
        sender_type='candidate',
        sender_user_id=None,
        body=message,
        sent_at=now,
        created_at=now
    )
    session.add(incoming_msg)

    # Get conversation history (last 10 messages)
    history_result = await session.execute(
        select(Message)
        .where(Message.candidate_id == candidate.id)
        .order_by(Message.sent_at.desc())
        .limit(10)
    )
    history_messages = list(reversed(history_result.scalars().all()))

    # Get glafira settings
    settings_result = await session.execute(
        select(GlafiraSettings).where(GlafiraSettings.company_id == company_id)
    )
    glafira_settings = settings_result.scalar_one_or_none()

    # Use default settings if not found
    if not glafira_settings:
        tone = 'business'
        use_informal = False
        emoji_level = 'moderate'
    else:
        tone = glafira_settings.tone
        use_informal = glafira_settings.use_informal
        emoji_level = glafira_settings.emoji_level

    # Компания вакансии. Вакансии в скоупе НЕТ (есть только кандидат), но диалог всегда
    # начат start_screening — оно пишет исходящее сообщение с application_id (:160).
    # Берём вакансию ИМЕННО ЭТОГО диалога: у кандидата может быть несколько откликов к
    # РАЗНЫМ заказчикам, и «последняя заявка» назвала бы кандидату чужую компанию посреди
    # разговора (промпт при этом велит «никогда не называй другую компанию»).
    dialog_vacancy = (await session.execute(
        select(Vacancy)
        .join(Application, Application.vacancy_id == Vacancy.id)
        .join(Message, Message.application_id == Application.id)
        .where(
            Message.candidate_id == candidate.id,
            Message.company_id == company_id,
            Message.direction == 'out',
            Message.sender_type == 'ai',
            Application.company_id == company_id,
            Vacancy.company_id == company_id,
            Vacancy.deleted_at.is_(None),
        )
        .order_by(Message.sent_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    # Фолбэк: диалог без привязки (старые сообщения) → последняя заявка кандидата.
    # Заявок нет вовсе → хелпер отдаст компанию-арендатора.
    if dialog_vacancy is None:
        dialog_vacancy = (await session.execute(
            select(Vacancy)
            .join(Application, Application.vacancy_id == Vacancy.id)
            .where(
                Application.candidate_id == candidate.id,
                Application.company_id == company_id,
                Vacancy.company_id == company_id,
                Vacancy.deleted_at.is_(None),
            )
            .order_by(Application.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

    company_name = await resolve_company_display_name(session, company_id, dialog_vacancy)

    # Build system prompt
    system_prompt = build_screening_system_prompt(
        company_name=company_name,
        tone=tone,
        tone_description=_get_tone_description(tone),
        address_mode=_get_address_mode(use_informal),
        emoji_level=_get_emoji_description(emoji_level)
    )

    # Build conversation context
    conversation_history = []
    for msg in history_messages:
        speaker = "Глафира" if msg.sender_type == 'ai' else candidate.full_name
        conversation_history.append(f"{speaker}: {msg.body}")

    # Add current candidate message to history
    conversation_history.append(f"{candidate.full_name}: {message}")

    # Компания пуста (не определилась) → без дырки «для компании «»».
    _co_reply = (company_name or "").strip()
    _for_company = f' для компании «{_co_reply}»' if _co_reply else ''

    user_prompt = f"""Продолжи скрининг кандидата {candidate.full_name}{_for_company}.

История беседы:
{chr(10).join(conversation_history)}

Ответь на последнее сообщение кандидата, задай уточняющие вопросы по опыту или навыкам.
Попробуй извлечь ключевую информацию (зарплатные ожидания, готовность к переезду, и т.д.).
Верни JSON в формате: {{"message": "ответ", "finished": false, "extracted": {{"salary_expectation": 100000, "ready_relocate": true}}}}"""

    # Резолвим API-ключ компании
    api_key = await get_company_openrouter_key(session, company_id)

    # Call Claude API
    response_data = await call_json(
        system=system_prompt,
        user=user_prompt,
        api_key=api_key,
        max_tokens=1024
    )

    # Validate required fields - no fallbacks, strict validation
    if "message" not in response_data:
        raise GlafiraParseError(details={
            "reason": "Missing 'message' field in LLM response",
            "got": list(response_data.keys())
        })

    ai_response = response_data["message"]
    finished = response_data.get("finished", False)
    extracted = response_data.get("extracted", {})

    # Create outgoing AI message
    outgoing_msg = Message(
        company_id=company_id,
        candidate_id=candidate.id,
        application_id=None,  # No longer tied to specific application
        channel=candidate.preferred_channel or 'telegram',
        direction='out',
        sender_type='ai',
        sender_user_id=None,
        body=ai_response,
        # Ответ AI на 1с позже входящего — детерминированный порядок истории диалога
        # (иначе одинаковый sent_at с incoming_msg → недетерминированная сортировка).
        sent_at=now + timedelta(seconds=1),
        created_at=now
    )

    session.add(outgoing_msg)

    # Create event
    event = Event(
        company_id=company_id,
        type='new',  # Using existing type for conversation continue
        actor_type='ai',
        actor_user_id=actor_user_id,
        text=f"Глафира ответила кандидату {candidate.full_name}",
        entities=[
            {"type": "candidate", "id": str(candidate.id), "label": candidate.full_name},
            {"type": "message", "id": str(outgoing_msg.id), "label": "Ответ в скрининге"}
        ],
        candidate_id=candidate.id,
        vacancy_id=None,
        created_at=now
    )
    session.add(event)

    # Audit log
    await audit(
        session,
        action='reply_screening',
        entity_type='message',
        entity_id=outgoing_msg.id,
        after={
            'candidate_id': str(candidate.id),
            'application_id': None,
            'response_length': len(ai_response),
            'candidate_message_length': len(message)
        },
        actor_user_id=actor_user_id,
        actor_type='ai',
        company_id=company_id,
    )

    await session.flush()
    return {
        "message": ai_response,
        "finished": finished,
        "extracted": extracted
    }