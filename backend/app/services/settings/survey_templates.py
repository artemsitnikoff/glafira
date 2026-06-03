from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from ...models import SurveyTemplate
from ...core.errors import NotFoundError, ValidationError
from ...services.audit import audit


# Дефолтные шаблоны пульс-опросов адаптации (HR-каденция день 7 / 30 / 90).
# Единый источник правды: используется и сидом (app/seed.py), и провижном из UI.
# Вопрос: {id, text, goal, scale, enabled, optional?}. scale — человекочитаемая шкала.
DEFAULT_SURVEY_TEMPLATES = [
    {
        "name": "Первая неделя — реальность vs ожидания",
        "trigger_day": 7,
        "questions": [
            {"id": "q1", "text": "Как ты себя чувствуешь после первой недели?", "goal": "общее самочувствие", "scale": "😡 😞 😐 🙂 😄", "enabled": True},
            {"id": "q2", "text": "Понятно ли, что от тебя ждут на этой неделе?", "goal": "понимание роли", "scale": "1 · 2 · 3 · 4 · 5", "enabled": True},
            {"id": "q3", "text": "Получил(а) всё необходимое для работы — доступы, оборудование, инструктаж?", "goal": "онбординг и доступы", "scale": "Да / Нет", "enabled": True},
            {"id": "q4", "text": "Есть ли человек, к которому можно подойти с любым вопросом?", "goal": "поддержка и адаптация в команде", "scale": "Да / Нет", "enabled": True},
            {"id": "q5", "text": "Понимаешь ли, как твоя работа связана с целями команды?", "goal": "смысл и вовлечённость", "scale": "1 · 2 · 3 · 4 · 5", "enabled": True},
            {"id": "q6", "text": "Что сделало бы твою первую неделю лучше?", "goal": "открытый ответ · триггер-слова", "scale": "📝 текст", "enabled": True, "optional": True},
        ],
    },
    {
        "name": "Первый месяц — пик ухода",
        "trigger_day": 30,
        "questions": [
            {"id": "q1", "text": "Насколько ты доволен(на) работой за последний месяц?", "goal": "общая удовлетворённость", "scale": "😡 😞 😐 🙂 😄", "enabled": True},
            {"id": "q2", "text": "Оцени своего руководителя по поддержке и обратной связи.", "goal": "оценка руководителя · маршрутизация при ≤2", "scale": "1 · 2 · 3 · 4 · 5", "enabled": True},
            {"id": "q3", "text": "Зарплата за прошлый месяц получена в срок и в полном объёме?", "goal": "выплаты вовремя · критичный сигнал при «Нет»", "scale": "Да / Нет", "enabled": True},
            {"id": "q4", "text": "Хватает ли тебе самостоятельности в принятии решений?", "goal": "автономия", "scale": "1 · 2 · 3 · 4 · 5", "enabled": True},
            {"id": "q5", "text": "Что больше всего мешает тебе работать сейчас?", "goal": "открытый ответ · триггер-слова", "scale": "📝 текст", "enabled": True, "optional": False},
        ],
    },
    {
        "name": "90 дней — решение остаться",
        "trigger_day": 90,
        "questions": [
            {"id": "q1", "text": "Насколько вероятно, что ты останешься в компании на следующие 6 месяцев?", "goal": "намерение остаться", "scale": "1 · 2 · 3 · 4 · 5", "enabled": True},
            {"id": "q2", "text": "Насколько вероятно, что порекомендуешь работу здесь другу или знакомому?", "goal": "eNPS", "scale": "0–10 (eNPS)", "enabled": True},
            {"id": "q3", "text": "Соответствует ли работа тому, что обещали на этапе найма?", "goal": "соответствие ожиданиям", "scale": "1 · 2 · 3 · 4 · 5", "enabled": True},
            {"id": "q4", "text": "Видишь ли ты для себя возможности роста через 6–12 месяцев?", "goal": "перспективы роста · драйвер удержания", "scale": "Да / Нет", "enabled": True},
            {"id": "q5", "text": "Что бы ты изменил(а) в первые 90 дней, если бы мог(ла)?", "goal": "открытый ответ", "scale": "📝 текст", "enabled": True, "optional": False},
        ],
    },
]


async def provision_default_survey_templates(session: AsyncSession, company_id: UUID, actor_user_id: UUID) -> list[SurveyTemplate]:
    """Создать стандартные шаблоны опросов адаптации (день 7/30/90), если их ещё нет.

    Идемпотентно: если у компании уже есть шаблоны — НИЧЕГО не создаёт, возвращает текущие.
    """
    existing = await list_survey_templates(session, company_id)
    if existing:
        return existing

    created: list[SurveyTemplate] = []
    for tpl in DEFAULT_SURVEY_TEMPLATES:
        t = SurveyTemplate(
            company_id=company_id,
            name=tpl["name"],
            trigger_day=tpl["trigger_day"],
            interval_days=None,
            channels={"telegram": True},
            questions=tpl["questions"],
            is_enabled=True,
        )
        session.add(t)
        created.append(t)
    await session.flush()

    await audit(
        session,
        action="provision_default_survey_templates",
        entity_type="survey_template",
        entity_id=created[0].id,
        after={"count": len(created)},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )
    return created


async def list_survey_templates(session: AsyncSession, company_id: UUID) -> list[SurveyTemplate]:
    """List survey templates for company"""
    result = await session.execute(
        select(SurveyTemplate)
        .where(SurveyTemplate.company_id == company_id)
        # По дню запуска (день 7 → 30 → 90), затем по имени; null trigger_day — в конец.
        .order_by(SurveyTemplate.trigger_day.asc().nulls_last(), SurveyTemplate.name)
    )
    return list(result.scalars().all())


async def get_survey_template(session: AsyncSession, template_id: UUID, company_id: UUID) -> SurveyTemplate:
    """Get survey template by ID"""
    result = await session.execute(
        select(SurveyTemplate)
        .where(SurveyTemplate.id == template_id)
        .where(SurveyTemplate.company_id == company_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise NotFoundError("Шаблон опроса")

    return template


async def create_survey_template(
    session: AsyncSession, company_id: UUID, data, actor_user_id: UUID
) -> SurveyTemplate:
    """Create new survey template"""
    if not data.name or not data.name.strip():
        raise ValidationError("name не может быть пустым")

    if not data.questions:
        raise ValidationError("questions не может быть пустым")

    if not data.channels:
        raise ValidationError("channels не может быть пустым")

    template = SurveyTemplate(
        company_id=company_id,
        name=data.name.strip(),
        trigger_day=data.trigger_day,
        interval_days=data.interval_days,
        channels=data.channels,
        questions=data.questions,
        is_enabled=data.is_enabled if data.is_enabled is not None else True,
    )

    session.add(template)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="create_survey_template",
        entity_type="survey_template",
        entity_id=template.id,
        after={
            "name": template.name,
            "trigger_day": template.trigger_day,
            "interval_days": template.interval_days,
            "is_enabled": template.is_enabled,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return template


async def update_survey_template(
    session: AsyncSession, template_id: UUID, company_id: UUID, data, actor_user_id: UUID
) -> SurveyTemplate:
    """Update survey template"""
    template = await get_survey_template(session, template_id, company_id)

    # Store original values for audit
    before = {
        "name": template.name,
        "trigger_day": template.trigger_day,
        "interval_days": template.interval_days,
        "channels": template.channels,
        "questions": template.questions,
        "is_enabled": template.is_enabled,
    }

    # Update fields
    if data.name is not None:
        if not data.name.strip():
            raise ValidationError("name не может быть пустым")
        template.name = data.name.strip()

    if data.trigger_day is not None:
        template.trigger_day = data.trigger_day

    if data.interval_days is not None:
        template.interval_days = data.interval_days

    if data.channels is not None:
        if not data.channels:
            raise ValidationError("channels не может быть пустым")
        template.channels = data.channels

    if data.questions is not None:
        if not data.questions:
            raise ValidationError("questions не может быть пустым")
        template.questions = data.questions

    if data.is_enabled is not None:
        template.is_enabled = data.is_enabled

    await session.flush()

    # Audit log
    after = {
        "name": template.name,
        "trigger_day": template.trigger_day,
        "interval_days": template.interval_days,
        "channels": template.channels,
        "questions": template.questions,
        "is_enabled": template.is_enabled,
    }

    await audit(
        session,
        action="update_survey_template",
        entity_type="survey_template",
        entity_id=template.id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return template


async def delete_survey_template(
    session: AsyncSession, template_id: UUID, company_id: UUID, actor_user_id: UUID
) -> None:
    """Delete survey template"""
    template = await get_survey_template(session, template_id, company_id)

    # Store original values for audit
    before = {
        "name": template.name,
        "trigger_day": template.trigger_day,
        "interval_days": template.interval_days,
        "is_enabled": template.is_enabled,
    }

    # Hard delete
    await session.delete(template)
    await session.flush()

    # Audit log
    await audit(
        session,
        action="survey_template_delete",
        entity_type="survey_template",
        entity_id=template_id,
        before=before,
        after=None,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )