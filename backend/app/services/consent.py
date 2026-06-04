from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError, AlreadySignedError
from ..models import Candidate, Consent, Message
from ..schemas.consent import ConsentOut, ConsentRequest
from ..services.audit import audit




async def get_candidate_consent(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID
) -> ConsentOut | None:
    """Get latest consent for candidate"""
    # Verify candidate exists and belongs to company
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    result = await session.execute(
        select(Consent)
        .where(Consent.candidate_id == candidate_id)
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()

    return ConsentOut.model_validate(consent) if consent else None


async def _next_consent_number(session: AsyncSession, company_id: UUID) -> str:
    """Следующий номер согласия PD-NNN/YY под advisory-lock на компанию."""
    lock_key = f"consent_number:{company_id}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": lock_key}
    )

    current_year = datetime.now(timezone.utc).year
    year_suffix = str(current_year)[-2:]

    seq_result = await session.execute(
        text(
            "SELECT COALESCE(MAX(CAST(SPLIT_PART(SPLIT_PART(number, '-', 2), '/', 1) AS INTEGER)), 0) + 1 "
            "FROM consents "
            "WHERE company_id = :company_id AND number LIKE :pattern"
        ),
        {"company_id": company_id, "pattern": f"PD-%/{year_suffix}"},
    )
    seq = seq_result.scalar_one()
    return f"PD-{seq:03d}/{year_suffix}"


async def request_consent(
    session: AsyncSession,
    candidate_id: UUID,
    request_data: ConsentRequest,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentOut:
    """Request consent from candidate"""
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

    # Generate unique consent number with advisory lock
    lock_key = f"consent_number:{company_id}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": lock_key}
    )

    current_year = datetime.now(timezone.utc).year
    year_suffix = str(current_year)[-2:]

    seq_result = await session.execute(
        text(
            "SELECT COALESCE(MAX(CAST(SPLIT_PART(SPLIT_PART(number, '-', 2), '/', 1) AS INTEGER)), 0) + 1 "
            "FROM consents "
            "WHERE company_id = :company_id AND number LIKE :pattern"
        ),
        {"company_id": company_id, "pattern": f"PD-%/{year_suffix}"},
    )
    seq = seq_result.scalar_one()
    number = f"PD-{seq:03d}/{year_suffix}"

    now = datetime.now(timezone.utc)

    # Create consent
    consent = Consent(
        company_id=company_id,
        candidate_id=candidate_id,
        number=number,
        status="pending",
        channel=request_data.channel,
        requested_at=now,
        created_at=now,
    )

    session.add(consent)
    await session.flush()

    # Create outgoing AI message
    message_body = "Здравствуйте! Для рассмотрения вашей кандидатуры мне понадобится ваше согласие на обработку персональных данных. Подпишите, пожалуйста, ссылку: [auto-generated]"

    message = Message(
        company_id=company_id,
        candidate_id=candidate_id,
        channel=request_data.channel,
        direction="out",
        sender_type="ai",
        body=message_body,
        sent_at=now,
        created_at=now
    )

    session.add(message)

    # Audit
    await audit(
        session,
        action="request_consent",
        entity_type="consent",
        entity_id=consent.id,
        after={
            "number": number,
            "status": "pending",
            "channel": request_data.channel
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return ConsentOut.model_validate(consent)


async def sign_consent(
    session: AsyncSession,
    consent_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentOut:
    """Sign consent"""
    # Get consent
    result = await session.execute(
        select(Consent)
        .join(Candidate, Consent.candidate_id == Candidate.id)
        .where(
            Consent.id == consent_id,
            Candidate.company_id == company_id
        )
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise NotFoundError("Согласие")

    if consent.status == "signed":
        raise AlreadySignedError()

    # Update consent
    now = datetime.now(timezone.utc)
    consent.status = "signed"
    consent.signed_at = now

    # Audit
    await audit(
        session,
        action="sign_consent",
        entity_type="consent",
        entity_id=consent.id,
        before={"status": "pending"},
        after={"status": "signed", "signed_at": now.isoformat()},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return ConsentOut.model_validate(consent)


async def confirm_consent_signed_by_recruiter(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentOut:
    """Рекрутёр под свою ответственность отмечает согласие подписанным (бумага и т.п.).

    Если есть ожидающее согласие — подписывает его; если согласия нет (или отозвано) —
    создаёт уже подписанным (channel='offline'). Идемпотентно: уже подписано → вернуть как есть.
    Сообщение кандидату НЕ шлётся (в отличие от request_consent).
    """
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

    # Последнее согласие любого статуса
    result = await session.execute(
        select(Consent)
        .where(Consent.candidate_id == candidate_id)
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    # Уже подписано — идемпотентно
    if consent and consent.status == "signed":
        return ConsentOut.model_validate(consent)

    if consent and consent.status == "pending":
        before = {"status": "pending"}
        consent.status = "signed"
        consent.signed_at = now
    else:
        # Нет согласия (или отозвано) — создаём уже подписанным
        number = await _next_consent_number(session, company_id)
        consent = Consent(
            company_id=company_id,
            candidate_id=candidate_id,
            number=number,
            status="signed",
            channel="offline",
            signed_at=now,
            requested_at=now,
            created_at=now,
        )
        session.add(consent)
        await session.flush()
        before = None

    await audit(
        session,
        action="confirm_consent_signed",
        entity_type="consent",
        entity_id=consent.id,
        before=before,
        after={"status": "signed", "signed_at": now.isoformat(), "by": "recruiter"},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return ConsentOut.model_validate(consent)


async def sign_consent_by_candidate(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentOut:
    """Sign latest pending consent for candidate"""
    # Verify candidate exists and belongs to company
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

    # Get latest pending consent
    result = await session.execute(
        select(Consent)
        .where(
            Consent.candidate_id == candidate_id,
            Consent.status == 'pending'
        )
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise NotFoundError("Нет ожидающего подписания согласия")

    # Update consent
    now = datetime.now(timezone.utc)
    consent.status = "signed"
    consent.signed_at = now

    # Audit
    await audit(
        session,
        action="sign_consent_by_candidate",
        entity_type="consent",
        entity_id=consent.id,
        before={"status": "pending"},
        after={"status": "signed", "signed_at": now.isoformat()},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return ConsentOut.model_validate(consent)