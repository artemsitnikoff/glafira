from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from uuid import UUID
import re

from ...models import CompanyDefaultStage
from ...core.errors import NotFoundError, ValidationError, ConflictError
from ...core.stages import STAGES, PROTECTED_STAGE_KEYS
from ...services.audit import audit


async def list_default_stages(session: AsyncSession, company_id: UUID) -> list[CompanyDefaultStage]:
    """Get company default stages (чистое чтение, без сайд-эффектов)"""
    result = await session.execute(
        select(CompanyDefaultStage)
        .where(CompanyDefaultStage.company_id == company_id)
        .order_by(CompanyDefaultStage.order_index)
    )
    return list(result.scalars().all())


async def ensure_default_stages(session: AsyncSession, company_id: UUID) -> list[CompanyDefaultStage]:
    """Инвариант: у компании ВСЕГДА есть дефолт-воронка с защищёнными этапами.

    Если этапов нет (компания не была провижинирована) — создаёт базовую воронку из
    core/stages.py STAGES (включая hired/rejected/added/response, которые нельзя удалить).
    Идемпотентна: при наличии этапов ничего не создаёт. Возвращает полный список по порядку.
    Вызывающий обязан закоммитить (на GET-эндпоинте — после сборки ответа).
    """
    stages = await list_default_stages(session, company_id)
    if stages:
        return stages

    for stage_def in STAGES.values():
        session.add(
            CompanyDefaultStage(
                company_id=company_id,
                stage_key=stage_def.key,
                label=stage_def.label,
                order_index=stage_def.order_index,
                is_terminal=stage_def.is_terminal,
            )
        )
    await session.flush()
    return await list_default_stages(session, company_id)


async def create_default_stage(
    session: AsyncSession, company_id: UUID, data, actor_user_id: UUID
) -> CompanyDefaultStage:
    """Create new default stage"""
    if not data.label or not data.label.strip():
        raise ValidationError("label не может быть пустым")

    if not data.stage_key or not data.stage_key.strip():
        raise ValidationError("stage_key не может быть пустым")

    # Validate stage_key format
    if not re.match(r"^[a-z0-9_]+$", data.stage_key) or len(data.stage_key) > 20:
        raise ValidationError("stage_key должен содержать только [a-z0-9_] и быть не длиннее 20 символов")

    # Check uniqueness
    existing = await session.execute(
        select(CompanyDefaultStage)
        .where(
            CompanyDefaultStage.company_id == company_id,
            CompanyDefaultStage.stage_key == data.stage_key
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"Этап с ключом '{data.stage_key}' уже существует")

    stage = CompanyDefaultStage(
        company_id=company_id,
        stage_key=data.stage_key,
        label=data.label.strip(),
        order_index=data.order_index or 0,
        is_terminal=data.is_terminal or False,
    )

    session.add(stage)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="create_default_stage",
        entity_type="company_default_stage",
        entity_id=stage.id,
        after={
            "stage_key": stage.stage_key,
            "label": stage.label,
            "order_index": stage.order_index,
            "is_terminal": stage.is_terminal,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return stage


async def update_default_stage(
    session: AsyncSession, stage_key: str, company_id: UUID, data, actor_user_id: UUID
) -> CompanyDefaultStage:
    """Update default stage (only label)"""
    result = await session.execute(
        select(CompanyDefaultStage)
        .where(
            CompanyDefaultStage.company_id == company_id,
            CompanyDefaultStage.stage_key == stage_key
        )
    )
    stage = result.scalar_one_or_none()

    if not stage:
        raise NotFoundError("Этап воронки")

    if not data.label or not data.label.strip():
        raise ValidationError("label не может быть пустым")

    # Store original values for audit
    before = {"label": stage.label}

    stage.label = data.label.strip()
    await session.flush()

    # Audit log
    after = {"label": stage.label}

    await audit(
        session,
        action="update_default_stage",
        entity_type="company_default_stage",
        entity_id=stage.id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return stage


async def delete_default_stage(
    session: AsyncSession, stage_key: str, company_id: UUID, actor_user_id: UUID
) -> None:
    """Delete default stage (if not protected)"""
    if stage_key in PROTECTED_STAGE_KEYS:
        raise ValidationError(f"Защищённый этап '{stage_key}' нельзя удалять")

    result = await session.execute(
        select(CompanyDefaultStage)
        .where(
            CompanyDefaultStage.company_id == company_id,
            CompanyDefaultStage.stage_key == stage_key
        )
    )
    stage = result.scalar_one_or_none()

    if not stage:
        raise NotFoundError("Этап воронки")

    # Store original values for audit
    before = {
        "stage_key": stage.stage_key,
        "label": stage.label,
        "order_index": stage.order_index,
        "is_terminal": stage.is_terminal,
    }

    await session.delete(stage)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="delete_default_stage",
        entity_type="company_default_stage",
        entity_id=stage.id,
        before=before,
        after=None,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )


async def reorder_default_stages(
    session: AsyncSession, company_id: UUID, reorder_data, actor_user_id: UUID
) -> None:
    """Reorder default stages"""
    if not reorder_data.order:
        raise ValidationError("Список порядка не может быть пустым")

    # Get existing stages
    result = await session.execute(
        select(CompanyDefaultStage)
        .where(CompanyDefaultStage.company_id == company_id)
    )
    stages = {stage.stage_key: stage for stage in result.scalars().all()}

    # Validate all stages exist
    for stage_key in reorder_data.order:
        if stage_key not in stages:
            raise ValidationError(f"Этап '{stage_key}' не найден")

    # Store original order for audit
    before = {stage.stage_key: stage.order_index for stage in stages.values()}

    # Update order_index
    for new_index, stage_key in enumerate(reorder_data.order, start=1):
        stages[stage_key].order_index = new_index

    await session.flush()

    # Store new order for audit
    after = {stage.stage_key: stage.order_index for stage in stages.values()}

    # Audit log
    await audit(
        session,
        action="reorder_default_stages",
        entity_type="company_default_stage",
        entity_id=None,  # Multiple entities affected
        before={"order": before},
        after={"order": after},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )