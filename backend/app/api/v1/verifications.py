"""Verification API endpoints"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...deps import get_current_user, get_db
from ...core.errors import NotFoundError
from ...models import User
from ...schemas.verification import VerificationOut
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

    return VerificationOut(
        id=verification.id,
        candidate_id=verification.candidate_id,
        consent_id=verification.consent_id,
        checked_at=verification.checked_at,
        status=verification.status,
        blocks=verification.blocks,
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

    return VerificationOut(
        id=verification.id,
        candidate_id=verification.candidate_id,
        consent_id=verification.consent_id,
        checked_at=verification.checked_at,
        status=verification.status,
        blocks=verification.blocks,
        created_at=verification.created_at
    )