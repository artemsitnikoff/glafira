"""Verification API endpoints"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...deps import get_current_user, get_db
from ...core.errors import NotFoundError
from ...models import User, Consent
from ...schemas.verification import VerificationOut, VerifyBlock
from ...services.glafira.verify import verify_candidate, get_candidate_verification

router = APIRouter()


@router.post("/candidates/{candidate_id}/verify", response_model=VerificationOut, status_code=201)
async def verify_candidate_endpoint(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Verify candidate using Glafira"""

    verification = await verify_candidate(
        session,
        candidate_id=candidate_id,
        company_id=current_user.company_id,
        actor_user_id=current_user.id
    )

    await session.commit()

    # Get consent number
    consent_result = await session.execute(
        select(Consent).where(Consent.id == verification.consent_id)
    )
    consent = consent_result.scalar_one()

    # Convert blocks from old dict format to new list format if needed
    if isinstance(verification.blocks, dict):
        # Old format - convert to new
        blocks = []
        for key, block_data in verification.blocks.items():
            blocks.append(VerifyBlock(
                key=key,
                title=f"Block {key}",  # placeholder
                sources=[{"name": "Mock", "type": "api"}],
                status=block_data.get("status", "clean"),
                data=block_data.get("details", {})
            ))
    else:
        # New format - already a list
        blocks = [VerifyBlock(**block) for block in verification.blocks]

    return VerificationOut(
        id=verification.id,
        candidate_id=verification.candidate_id,
        consent_id=verification.consent_id,
        consent_number=consent.number,
        status=verification.status,
        blocks=blocks,
        created_at=verification.created_at
    )


@router.get("/candidates/{candidate_id}/verification", response_model=VerificationOut)
async def get_candidate_verification_endpoint(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get latest verification for candidate"""

    verification = await get_candidate_verification(
        session,
        candidate_id=candidate_id,
        company_id=current_user.company_id
    )

    if not verification:
        raise NotFoundError("Верификация")

    # Get consent number
    consent_result = await session.execute(
        select(Consent).where(Consent.id == verification.consent_id)
    )
    consent = consent_result.scalar_one()

    # Convert blocks from old dict format to new list format if needed
    if isinstance(verification.blocks, dict):
        # Old format - convert to new
        blocks = []
        for key, block_data in verification.blocks.items():
            blocks.append(VerifyBlock(
                key=key,
                title=f"Block {key}",  # placeholder
                sources=[{"name": "Mock", "type": "api"}],
                status=block_data.get("status", "clean"),
                data=block_data.get("details", {})
            ))
    else:
        # New format - already a list
        blocks = [VerifyBlock(**block) for block in verification.blocks]

    return VerificationOut(
        id=verification.id,
        candidate_id=verification.candidate_id,
        consent_id=verification.consent_id,
        consent_number=consent.number,
        status=verification.status,
        blocks=blocks,
        created_at=verification.created_at
    )