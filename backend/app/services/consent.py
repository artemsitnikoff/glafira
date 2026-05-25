from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError, AlreadySignedError
from ..models import Candidate, Consent, Message
from ..schemas.consent import ConsentOut, ConsentRequest
from ..services.audit import audit


async def get_candidate_consents(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID
) -> list[ConsentOut]:
    """Get consent history for candidate"""
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
    )
    consents = result.scalars().all()

    return [ConsentOut.model_validate(consent) for consent in consents]


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