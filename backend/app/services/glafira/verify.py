"""Верификация кандидатов"""

import hashlib
import logging
import random
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...core.errors import ConsentRequiredError, NotFoundError, FeatureNotImplementedError
from ...models import Candidate, Consent, Verification, Event
from ...services.audit import audit

logger = logging.getLogger(__name__)


def _generate_mock_verification_blocks(candidate_id: UUID) -> tuple[str, list[dict]]:
    """Generate deterministic mock verification blocks"""
    # Use candidate ID for deterministic randomness
    seed = int(hashlib.sha256(str(candidate_id).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    blocks = []

    # Define all 7 blocks
    block_configs = [
        ("inn", "Проверка ИНН", [{"name": "ФНС", "type": "gov"}]),
        ("fssp", "Исполнительные производства", [{"name": "ФССП", "type": "gov"}]),
        ("bankruptcy", "Реестр банкротов", [{"name": "ЕФРСБ", "type": "gov"}]),
        ("registries", "Прочие реестры", [{"name": "РОСРЕЕСТР", "type": "gov"}]),
        ("public", "Публичные источники", [{"name": "Соцсети", "type": "public"}]),
        ("ai_intel", "AI-анализ", [{"name": "Глафира", "type": "ai"}]),
        ("alimony", "Алименты", [{"name": "ФССП", "type": "gov"}]),
    ]

    # Most blocks are clean, 1-2 can have issues
    issue_count = rng.randint(0, 2)
    issue_indices = rng.sample(range(len(block_configs)), min(issue_count, len(block_configs)))

    for idx, (key, title, sources) in enumerate(block_configs):
        if idx in issue_indices:
            # This block has an issue
            status = rng.choice(["info", "warn", "risk"])
        else:
            status = "clean"

        # Generate deterministic mock data per block
        if key == "inn":
            inn_suffix = str(seed)[-10:]
            data = {
                "inn": f"77{inn_suffix}",
                "tax_status": "active" if status == "clean" else "inactive",
                "last_check": "2026-05-25"
            }
        elif key == "fssp":
            data = {
                "open_cases": 0 if status == "clean" else rng.randint(1, 3),
                "total_debt": 0 if status == "clean" else rng.randint(10000, 500000)
            }
        elif key == "bankruptcy":
            data = {
                "is_bankrupt": False,
                "bankruptcy_cases": 0 if status == "clean" else 1
            }
        elif key == "registries":
            data = {
                "sanctions_found": status != "clean",
                "registry_count": 0 if status == "clean" else 1
            }
        elif key == "public":
            data = {
                "mentions_count": rng.randint(0, 5),
                "negative_mentions": 0 if status == "clean" else rng.randint(1, 3)
            }
        elif key == "ai_intel":
            data = {
                "reputation_score": 85 if status == "clean" else rng.randint(20, 60),
                "confidence": 0.92
            }
        elif key == "alimony":
            data = {
                "alimony_debt": 0 if status == "clean" else rng.randint(50000, 200000),
                "active_cases": 0 if status == "clean" else 1
            }
        else:
            data = {}

        blocks.append({
            "key": key,
            "title": title,
            "sources": sources,
            "status": status,
            "data": data
        })

    # Determine overall status
    statuses = [block["status"] for block in blocks]
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
        raise FeatureNotImplementedError(details={
            "feature": "real_verification",
            "hint": "Set GLAFIRA_VERIFY_MODE=mock to use mock data"
        })

    # Generate mock verification data
    overall_status, blocks = _generate_mock_verification_blocks(candidate_id)

    # Create verification record
    now = datetime.now(timezone.utc)
    is_mock = (settings.GLAFIRA_VERIFY_MODE == 'mock')
    verification = Verification(
        company_id=company_id,
        candidate_id=candidate_id,
        consent_id=consent.id,
        checked_at=now,
        status=overall_status,
        blocks=blocks,
        is_mock=is_mock,
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