from fastapi import APIRouter, Depends, Path
from uuid import UUID

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...database import get_db
from ...core.errors import ForbiddenError
from ...core.permissions import can_manager_access_candidate
from ...schemas.consent import ConsentOut, ConsentRequest
from ...services.consent import (
    get_candidate_consent,
    request_consent,
    sign_consent_by_candidate,
    confirm_consent_signed_by_recruiter
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/candidates/{candidate_id}/consent", response_model=ConsentOut)
async def get_consent(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # RBAC: менеджер может читать статус согласия только для своих кандидатов
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к согласию данного кандидата")

    from ...core.errors import NotFoundError
    consent = await get_candidate_consent(session, candidate_id, company_id)
    if not consent:
        raise NotFoundError("Согласие")
    return consent


@router.post("/candidates/{candidate_id}/consent/request", response_model=ConsentOut, status_code=201)
async def request_consent_route(
    candidate_id: UUID,
    data: ConsentRequest = ConsentRequest(),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # RBAC: менеджеры не могут запрашивать согласия
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут запрашивать согласия на обработку данных")

    result = await request_consent(session, candidate_id, data, company_id, user.id)
    await session.commit()
    return result


@router.post("/candidates/{candidate_id}/consent/sign", response_model=ConsentOut)
async def sign_consent_route(
    candidate_id: UUID,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # RBAC: менеджеры не могут подписывать согласия за кандидатов
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут подписывать согласия")

    result = await sign_consent_by_candidate(session, candidate_id, company_id, user.id)
    await session.commit()
    return result


@router.post("/candidates/{candidate_id}/consent/confirm-signed", response_model=ConsentOut)
async def confirm_consent_signed_route(
    candidate_id: UUID,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    """Рекрутёр подтверждает, что согласие получено (например, на бумаге).

    Ответственность на рекрутёре. Создаёт/подписывает Consent без отправки сообщения кандидату.
    """
    # RBAC: менеджеры не могут подтверждать согласия (это действие рекрутёра)
    if user.role == "manager":
        raise ForbiddenError("Менеджеры не могут подтверждать подписанные согласия")

    result = await confirm_consent_signed_by_recruiter(session, candidate_id, company_id, user.id)
    await session.commit()
    return result