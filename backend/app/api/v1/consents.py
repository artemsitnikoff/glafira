from fastapi import APIRouter, Depends, Path
from uuid import UUID

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...database import get_db
from ...schemas.consent import ConsentOut, ConsentRequest
from ...services.consent import (
    get_candidate_consents,
    request_consent,
    sign_consent
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/candidates/{candidate_id}/consents", response_model=list[ConsentOut])
async def get_consents(
    candidate_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    return await get_candidate_consents(session, candidate_id, company_id)


@router.post("/candidates/{candidate_id}/consents/request", response_model=ConsentOut, status_code=201)
async def request_consent_route(
    candidate_id: UUID,
    data: ConsentRequest = ConsentRequest(),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    result = await request_consent(session, candidate_id, data, company_id, user.id)
    await session.commit()
    return result


@router.post("/consents/{consent_id}/sign", response_model=ConsentOut)
async def sign_consent_route(
    consent_id: UUID,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    result = await sign_consent(session, consent_id, company_id, user.id)
    await session.commit()
    return result