"""Настраиваемые пресеты воронок (FunnelTemplate) для формы создания вакансии.

«По умолчанию» здесь НЕ хранится — это company_default_stages (отдельный сервис default_funnel).
Здесь — дополнительные именованные шаблоны и их этапы.
"""
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ...models import FunnelTemplate, FunnelTemplateStage
from ...core.errors import NotFoundError, ValidationError, ConflictError
from ...core.stages import STAGES, PROTECTED_STAGE_KEYS
from ...services.audit import audit


async def list_templates(session: AsyncSession, company_id: UUID) -> list[FunnelTemplate]:
    result = await session.execute(
        select(FunnelTemplate)
        .where(FunnelTemplate.company_id == company_id)
        .order_by(FunnelTemplate.order_index, FunnelTemplate.name)
    )
    return list(result.scalars().all())


async def _get_owned_template(session: AsyncSession, template_id: UUID, company_id: UUID) -> FunnelTemplate:
    result = await session.execute(
        select(FunnelTemplate)
        .where(FunnelTemplate.id == template_id, FunnelTemplate.company_id == company_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundError("Шаблон воронки")
    return template


async def create_template(
    session: AsyncSession, company_id: UUID, name: str, actor_user_id: UUID
) -> FunnelTemplate:
    """Создаёт шаблон и наполняет его базовыми этапами из core STAGES (валидный, непустой)."""
    if not name or not name.strip():
        raise ValidationError("Название шаблона не может быть пустым")

    # order_index = в конец
    existing = await list_templates(session, company_id)
    template = FunnelTemplate(
        company_id=company_id,
        name=name.strip()[:60],
        order_index=(max((t.order_index for t in existing), default=0) + 1),
    )
    session.add(template)
    await session.flush()

    for stage_def in STAGES.values():
        session.add(
            FunnelTemplateStage(
                template_id=template.id,
                stage_key=stage_def.key,
                label=stage_def.label,
                order_index=stage_def.order_index,
                is_terminal=stage_def.is_terminal,
            )
        )
    await session.flush()

    await audit(
        session, action="create_funnel_template", entity_type="funnel_template",
        entity_id=template.id, after={"name": template.name},
        actor_user_id=actor_user_id, company_id=company_id,
    )
    return template


async def rename_template(
    session: AsyncSession, template_id: UUID, company_id: UUID, name: str, actor_user_id: UUID
) -> FunnelTemplate:
    template = await _get_owned_template(session, template_id, company_id)
    if not name or not name.strip():
        raise ValidationError("Название шаблона не может быть пустым")
    before = {"name": template.name}
    template.name = name.strip()[:60]
    await session.flush()
    await audit(
        session, action="rename_funnel_template", entity_type="funnel_template",
        entity_id=template.id, before=before, after={"name": template.name},
        actor_user_id=actor_user_id, company_id=company_id,
    )
    return template


async def delete_template(
    session: AsyncSession, template_id: UUID, company_id: UUID, actor_user_id: UUID
) -> None:
    template = await _get_owned_template(session, template_id, company_id)
    before = {"name": template.name}
    await session.delete(template)  # каскад снимет этапы
    await session.flush()
    await audit(
        session, action="delete_funnel_template", entity_type="funnel_template",
        entity_id=template_id, before=before, after=None,
        actor_user_id=actor_user_id, company_id=company_id,
    )


async def list_template_stages(
    session: AsyncSession, template_id: UUID, company_id: UUID
) -> list[FunnelTemplateStage]:
    await _get_owned_template(session, template_id, company_id)  # проверка владения
    result = await session.execute(
        select(FunnelTemplateStage)
        .where(FunnelTemplateStage.template_id == template_id)
        .order_by(FunnelTemplateStage.order_index)
    )
    return list(result.scalars().all())


async def add_template_stage(
    session: AsyncSession, template_id: UUID, company_id: UUID, data, actor_user_id: UUID
) -> FunnelTemplateStage:
    await _get_owned_template(session, template_id, company_id)
    if not data.label or not data.label.strip():
        raise ValidationError("label не может быть пустым")
    if not re.match(r"^[a-z0-9_]+$", data.stage_key) or len(data.stage_key) > 20:
        raise ValidationError("stage_key должен содержать только [a-z0-9_] и быть не длиннее 20 символов")
    existing = await session.execute(
        select(FunnelTemplateStage).where(
            FunnelTemplateStage.template_id == template_id,
            FunnelTemplateStage.stage_key == data.stage_key,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"Этап с ключом '{data.stage_key}' уже существует")
    stage = FunnelTemplateStage(
        template_id=template_id,
        stage_key=data.stage_key,
        label=data.label.strip()[:60],
        order_index=data.order_index or 0,
        is_terminal=data.is_terminal or False,
    )
    session.add(stage)
    await session.flush()
    await audit(
        session, action="add_template_stage", entity_type="funnel_template_stage",
        entity_id=stage.id, after={"stage_key": stage.stage_key, "label": stage.label},
        actor_user_id=actor_user_id, company_id=company_id,
    )
    return stage


async def rename_template_stage(
    session: AsyncSession, template_id: UUID, stage_key: str, company_id: UUID, data, actor_user_id: UUID
) -> FunnelTemplateStage:
    await _get_owned_template(session, template_id, company_id)
    result = await session.execute(
        select(FunnelTemplateStage).where(
            FunnelTemplateStage.template_id == template_id,
            FunnelTemplateStage.stage_key == stage_key,
        )
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise NotFoundError("Этап шаблона")
    if not data.label or not data.label.strip():
        raise ValidationError("label не может быть пустым")
    before = {"label": stage.label}
    stage.label = data.label.strip()[:60]
    await session.flush()
    await audit(
        session, action="rename_template_stage", entity_type="funnel_template_stage",
        entity_id=stage.id, before=before, after={"label": stage.label},
        actor_user_id=actor_user_id, company_id=company_id,
    )
    return stage


async def delete_template_stage(
    session: AsyncSession, template_id: UUID, stage_key: str, company_id: UUID, actor_user_id: UUID
) -> None:
    await _get_owned_template(session, template_id, company_id)
    if stage_key in PROTECTED_STAGE_KEYS:
        raise ValidationError(f"Защищённый этап '{stage_key}' нельзя удалять")
    result = await session.execute(
        select(FunnelTemplateStage).where(
            FunnelTemplateStage.template_id == template_id,
            FunnelTemplateStage.stage_key == stage_key,
        )
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise NotFoundError("Этап шаблона")
    await session.delete(stage)
    await session.flush()
    await audit(
        session, action="delete_template_stage", entity_type="funnel_template_stage",
        entity_id=stage.id, before={"stage_key": stage_key}, after=None,
        actor_user_id=actor_user_id, company_id=company_id,
    )


async def reorder_template_stages(
    session: AsyncSession, template_id: UUID, company_id: UUID, order: list[str], actor_user_id: UUID
) -> None:
    await _get_owned_template(session, template_id, company_id)
    if not order:
        raise ValidationError("Список порядка не может быть пустым")
    result = await session.execute(
        select(FunnelTemplateStage).where(FunnelTemplateStage.template_id == template_id)
    )
    stages = {s.stage_key: s for s in result.scalars().all()}
    for stage_key in order:
        if stage_key not in stages:
            raise ValidationError(f"Этап '{stage_key}' не найден")
    for new_index, stage_key in enumerate(order, start=1):
        stages[stage_key].order_index = new_index
    await session.flush()
    await audit(
        session, action="reorder_template_stages", entity_type="funnel_template_stage",
        entity_id=None, before=None, after={"order": order},
        actor_user_id=actor_user_id, company_id=company_id,
    )
