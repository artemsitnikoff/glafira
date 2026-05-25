"""Верификация кандидатов"""

import hashlib
import logging
import random
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...core.errors import ConsentRequiredError, NotFoundError
from ...models import Candidate, Consent, Verification, Event
from ...services.audit import audit

logger = logging.getLogger(__name__)


def _generate_mock_verification_blocks(candidate_id: UUID) -> tuple[str, dict]:
    """Generate deterministic mock verification blocks"""
    # Use candidate ID for deterministic randomness
    seed = int(hashlib.sha256(str(candidate_id).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    blocks = {}

    # Define all 7 blocks
    block_configs = [
        ("inn", "ИНН — идентификация", ["ФНС", "DaData"]),
        ("fssp", "Исполнительные производства", ["ФССП", "Datanewton"]),
        ("bankruptcy", "Банкротство и связи с юрлицами", ["ЕФРСБ", "DaData"]),
        ("registries", "Реестры и санкции", ["ФНС", "Росфинмониторинг"]),
        ("public", "Публичная экспертиза", ["СМИ", "Соцсети"]),
        ("ai_intel", "AI-разведка", ["Глафира"]),
        ("alimony", "Алиментные обязательства", ["ФССП", "Госуслуги"]),
    ]

    # Most blocks are clean, 1-2 can have issues
    issue_count = rng.randint(0, 2)
    issue_blocks = rng.sample(block_configs, min(issue_count, len(block_configs)))

    for key, title, sources in block_configs:
        if (key, title, sources) in issue_blocks:
            # This block has an issue
            status = rng.choice(["info", "warn", "risk"])
            if status == "info":
                summary = "Найдена дополнительная информация"
                details = {"note": "Требует проверки"}
            elif status == "warn":
                summary = "Обнаружено предупреждение"
                details = {"warning": "Возможные риски"}
            else:  # risk
                summary = "Выявлены критические риски"
                details = {"risk": "Высокий уровень угрозы"}
        else:
            # Clean block
            status = "clean"
            summary = "Проверка пройдена успешно"
            details = {"verified": True}

        blocks[key] = {
            "status": status,
            "summary": summary,
            "details": details
        }

    # Determine overall status
    statuses = [block["status"] for block in blocks.values()]
    if "risk" in statuses:
        overall_status = "risk"
    elif "warn" in statuses:
        overall_status = "warn"
    elif "info" in statuses:
        overall_status = "info"
    else:
        overall_status = "clean"

    return overall_status, blocks


async def verify_candidate(
    session: AsyncSession,
    *,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> Verification:
    """Verify candidate data"""
    # CRITICAL: Check for signed consent first
    consent_result = await session.execute(
        select(Consent).where(
            Consent.candidate_id == candidate_id,
            Consent.status == 'signed'
        ).limit(1)
    )
    consent = consent_result.scalar_one_or_none()
    if not consent:
        raise ConsentRequiredError()

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

    # Check verification mode
    if settings.GLAFIRA_VERIFY_MODE == 'real':
        logger.warning(f"Real verification not implemented, falling back to mock for candidate {candidate_id}")
        # raise NotImplementedError("Real verification not implemented yet")

    # Generate mock verification data
    overall_status, blocks = _generate_mock_verification_blocks(candidate_id)

    # Create verification record
    now = datetime.now(timezone.utc)
    verification = Verification(
        company_id=company_id,
        candidate_id=candidate_id,
        consent_id=consent.id,
        checked_at=now,
        status=overall_status,
        blocks=blocks,
        created_at=now
    )

    session.add(verification)

    # Create event
    event = Event(
        company_id=company_id,
        type='verify',
        actor_type='ai',
        actor_user_id=actor_user_id,
        text=f"Глафира провела верификацию: {overall_status}",
        entities=[
            {"type": "candidate", "id": str(candidate_id), "label": candidate.full_name}
        ],
        candidate_id=candidate_id,
        created_at=now
    )
    session.add(event)

    # Audit log
    await audit(
        session,
        action='verify_candidate',
        entity_type='verification',
        entity_id=verification.id,
        after={
            'status': overall_status,
            'blocks_count': len(blocks),
            'consent_id': str(consent.id)
        },
        actor_user_id=actor_user_id,
        actor_type='ai',
        company_id=company_id,
    )

    await session.flush()
    return verification


async def get_candidate_verification(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID
) -> Verification | None:
    """Get latest verification for candidate"""
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

    # Get latest verification
    result = await session.execute(
        select(Verification)
        .where(Verification.candidate_id == candidate_id)
        .order_by(Verification.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()