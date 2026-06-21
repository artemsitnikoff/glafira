"""Verification API endpoints"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...deps import get_current_user, get_db
from ...core.errors import NotFoundError, ForbiddenError
from ...core.permissions import can_manager_access_candidate
from ...models import User, Consent
from ...schemas.verification import VerificationOut, VerifyBlock
from ...services.glafira.verify import verify_candidate, get_candidate_verification, fill_candidate_osint

router = APIRouter()

# Держим ссылки на фоновые задачи разведки, иначе GC может убить их на полпути
# (asyncio.create_task без сильной ссылки — известная ловушка).
_osint_bg_tasks: set = set()


@router.post("/candidates/{candidate_id}/verify", response_model=VerificationOut, status_code=201)
async def verify_candidate_endpoint(
    candidate_id: UUID,
    force: bool = Query(False, description="Пересоздать верификацию даже если уже существует (тратит DaData + OSINT)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Verify candidate using Glafira.

    По умолчанию (force=false) возвращает существующую верификацию, если она уже есть —
    чтобы повторный клик/запрос не вызывал повторное списание DaData и OSINT-разведку.
    С force=true всегда запускает полную проверку заново.
    """

    # RBAC: менеджеры не могут запускать платную верификацию (DaData + OSINT)
    if current_user.role == "manager":
        raise ForbiddenError("Менеджеры не могут запускать верификацию")

    # Идемпотентность: если верификация уже есть и force не задан — возвращаем существующую
    # без повторного списания DaData×3 и спавна OSINT-фона.
    if not force:
        existing = await get_candidate_verification(session, candidate_id, current_user.company_id)
        if existing:
            verification = existing
            # Получаем consent для ответа
            consent_result = await session.execute(
                select(Consent).where(Consent.id == verification.consent_id)
            )
            consent = consent_result.scalar_one()
            if isinstance(verification.blocks, dict):
                blocks = []
                for key, block_data in verification.blocks.items():
                    blocks.append(VerifyBlock(
                        key=key,
                        title=f"Block {key}",
                        sources=[{"name": "Mock", "type": "api"}],
                        status=block_data.get("status", "clean"),
                        data=block_data.get("details", {})
                    ))
            else:
                blocks = [VerifyBlock(**block) for block in verification.blocks]
            return VerificationOut(
                id=verification.id,
                candidate_id=verification.candidate_id,
                consent_id=verification.consent_id,
                consent_number=consent.number,
                status=verification.status,
                blocks=blocks,
                is_mock=verification.is_mock,
                created_at=verification.created_at
            )

    verification = await verify_candidate(
        session,
        candidate_id=candidate_id,
        company_id=current_user.company_id,
        actor_user_id=current_user.id
    )

    await session.commit()

    # Интернет-разведка идёт в фоне (60–90с) — не держим HTTP-запрос. Своя сессия внутри.
    # Фронт подхватит результат поллингом (pending → заполнено).
    _task = asyncio.create_task(fill_candidate_osint(candidate_id, current_user.company_id))
    _osint_bg_tasks.add(_task)
    _task.add_done_callback(_osint_bg_tasks.discard)

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
        is_mock=verification.is_mock,
        created_at=verification.created_at
    )


@router.get("/candidates/{candidate_id}/verification", response_model=VerificationOut)
async def get_candidate_verification_endpoint(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get latest verification for candidate"""

    # RBAC: менеджер может читать статус верификации только для своих кандидатов
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, current_user.company_id):
            raise ForbiddenError("Нет доступа к верификации данного кандидата")

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
        is_mock=verification.is_mock,
        created_at=verification.created_at
    )