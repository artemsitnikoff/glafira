"""Сервис для генерации и управления планами адаптации"""

from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...models import PulsePlanItem
from ...core.errors import NotFoundError
from ...schemas.pulse import PlanItemUpdate
from ...services.audit import audit
from .prompts import PLAN_GEN_SYSTEM, PLAN_GEN_USER_TEMPLATE


DEFAULT_PLAN_TEMPLATE = [
    {'phase': 'welcome', 'title': 'Знакомство с командой', 'deadline_day': 1, 'responsible': 'manager'},
    {'phase': 'welcome', 'title': 'Получение доступов', 'deadline_day': 2, 'responsible': 'hr'},
    {'phase': 'welcome', 'title': 'Изучение продукта', 'deadline_day': 7, 'responsible': 'employee'},
    {'phase': 'month1', 'title': 'Первая встреча 1:1', 'deadline_day': 7, 'responsible': 'manager'},
    {'phase': 'month1', 'title': 'Промежуточная оценка', 'deadline_day': 30, 'responsible': 'hr'},
]

VALID_PHASES = {'welcome', 'month1', 'month2', 'month3'}
VALID_RESPONSIBLE = {'hr', 'manager', 'employee'}


async def generate_plan_items(
    session: AsyncSession,
    *,
    employee_id: UUID,
    position: str | None,
    department: str | None,
    probation_days: int,
    company_id: UUID,
) -> list[PulsePlanItem]:
    """Генерирует план адаптации через Glafira или использует fallback шаблон"""

    items = []

    # Попытка через Glafira
    try:
        from app.services.glafira.client import call_json
        from app.services.settings.glafira import get_company_openrouter_key

        # Резолвим API-ключ компании для LLM
        api_key = await get_company_openrouter_key(session, company_id)

        user_prompt = PLAN_GEN_USER_TEMPLATE.format(
            position=position or "не указана",
            department=department or "не указан",
            probation_days=probation_days
        )

        response = await call_json(system=PLAN_GEN_SYSTEM, user=user_prompt, api_key=api_key)
        ai_items = response.get('items', [])

        # Валидация каждого элемента
        for item in ai_items:
            if (
                isinstance(item, dict) and
                item.get('phase') in VALID_PHASES and
                item.get('responsible') in VALID_RESPONSIBLE and
                item.get('title')
            ):
                items.append(item)

        if not items:
            raise ValueError("Empty or invalid AI response")

    except Exception:
        # Fallback на статический шаблон
        items = DEFAULT_PLAN_TEMPLATE.copy()

    # Создание объектов PulsePlanItem
    plan_items = []
    for i, item in enumerate(items):
        plan_item = PulsePlanItem(
            company_id=company_id,
            employee_id=employee_id,
            phase=item['phase'],
            title=item['title'],
            deadline_day=item.get('deadline_day'),
            responsible=item['responsible'],
            order_index=i,
        )
        session.add(plan_item)
        plan_items.append(plan_item)

    await session.flush()
    return plan_items


async def patch_plan_item(
    session: AsyncSession,
    *,
    item_id: UUID,
    data: PlanItemUpdate,
    company_id: UUID,
    actor_user_id: UUID,
) -> PulsePlanItem:
    """Обновляет пункт плана адаптации"""

    # Find plan item
    query = select(PulsePlanItem).where(
        PulsePlanItem.id == item_id,
        PulsePlanItem.company_id == company_id
    )
    result = await session.execute(query)
    plan_item = result.scalar_one_or_none()

    if not plan_item:
        raise NotFoundError("Пункт плана")

    # Prepare update data
    update_data = {}
    if data.is_done is not None:
        update_data['is_done'] = data.is_done
        if data.is_done:
            update_data['done_at'] = datetime.now(timezone.utc)
        else:
            update_data['done_at'] = None

    if update_data:
        # Update plan item
        update_stmt = update(PulsePlanItem).where(
            PulsePlanItem.id == item_id
        ).values(**update_data)

        await session.execute(update_stmt)

        # Audit (serialize datetime for JSON)
        audit_after = {}
        for k, v in update_data.items():
            if isinstance(v, datetime):
                audit_after[k] = v.isoformat()
            else:
                audit_after[k] = v

        await audit(
            session,
            action="plan_item_updated",
            entity_type="pulse_plan_item",
            entity_id=item_id,
            before={"is_done": plan_item.is_done},
            after=audit_after,
            actor_user_id=actor_user_id,
            company_id=company_id,
        )

        await session.flush()

    # Return updated item
    updated_result = await session.execute(
        select(PulsePlanItem).where(PulsePlanItem.id == item_id)
    )
    return updated_result.scalar_one()