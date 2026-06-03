import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.core.security import get_password_hash
from app.database import AsyncSessionLocal
from app.models import Company, GlafiraSettings, RejectReason, User, CompanyDefaultStage, FunnelTemplate, FunnelTemplateStage, SurveyTemplate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ADMIN_EMAIL = "admin@dclouds.ru"
ADMIN_PASSWORD = "Glafira2026!"


REJECT_REASONS_COMPANY = [
    "Несоответствие опыта",
    "Несоответствие навыков",
    "Не прошёл интервью",
    "Не прошёл СБ",
    "Завышенные ожидания по ЗП",
]

REJECT_REASONS_CANDIDATE = [
    "Не вышел на связь",
    "Не устроила ЗП",
    "Принял другой оффер",
    "Не устроил график",
    "Слишком далеко от дома",
]

# Системные (защищённые) причины — по одной на сторону, нельзя удалить (инвариант непустоты).
SYSTEM_REJECT_REASONS = {
    "company": "Несоответствие опыта",
    "candidate": "Не вышел на связь",
}


async def seed_company(session: AsyncSession) -> None:
    company_id = uuid.UUID(settings.DEFAULT_COMPANY_ID)
    existing = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()

    if existing:
        logger.info("Company already exists: %s", existing.name)
        return

    session.add(Company(id=company_id, name="Глафира Demo"))
    logger.info("Created company: Глафира Demo")


async def seed_admin_user(session: AsyncSession) -> None:
    existing = (
        await session.execute(select(User).where(User.email == ADMIN_EMAIL))
    ).scalar_one_or_none()

    if existing:
        logger.info("Admin user already exists: %s", existing.email)
        return

    session.add(
        User(
            company_id=uuid.UUID(settings.DEFAULT_COMPANY_ID),
            email=ADMIN_EMAIL,
            password_hash=get_password_hash(ADMIN_PASSWORD),
            full_name="Анна Седова",
            role="admin",
            position="Старший рекрутёр",
        )
    )
    logger.info("Created admin user: %s", ADMIN_EMAIL)


async def seed_reject_reasons(session: AsyncSession) -> None:
    company_id = uuid.UUID(settings.DEFAULT_COMPANY_ID)

    for side, labels in (("company", REJECT_REASONS_COMPANY), ("candidate", REJECT_REASONS_CANDIDATE)):
        for idx, label in enumerate(labels, start=1):
            is_system = label == SYSTEM_REJECT_REASONS.get(side)
            existing = (
                await session.execute(
                    select(RejectReason).where(
                        RejectReason.company_id == company_id,
                        RejectReason.side == side,
                        RejectReason.label == label,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                # Идемпотентно подтягиваем флаг системности на уже посеянных причинах.
                if is_system and not existing.is_system:
                    existing.is_system = True
                continue
            session.add(
                RejectReason(
                    company_id=company_id,
                    side=side,
                    label=label,
                    order_index=idx,
                    is_system=is_system,
                )
            )

    logger.info("Reject reasons ensured (%d company / %d candidate)", len(REJECT_REASONS_COMPANY), len(REJECT_REASONS_CANDIDATE))


async def seed_glafira_settings(session: AsyncSession) -> None:
    company_id = uuid.UUID(settings.DEFAULT_COMPANY_ID)
    existing = (
        await session.execute(select(GlafiraSettings).where(GlafiraSettings.company_id == company_id))
    ).scalar_one_or_none()

    if existing:
        logger.info("Glafira settings already exist for company %s", company_id)
        return

    session.add(
        GlafiraSettings(
            company_id=company_id,
            tone="friendly",
            use_informal=True,
            emoji_level="moderate",
            auto_reject_below=30,
            auto_select_above=80,
            days_no_response=7,
            stop_words={},
            default_mode="A",
        )
    )
    logger.info("Created default Glafira settings")


async def seed_company_default_stages(session: AsyncSession) -> None:
    """Create default stages for company from core/stages.py STAGES"""
    from app.core.stages import STAGES

    company_id = uuid.UUID(settings.DEFAULT_COMPANY_ID)

    # Check if any stages exist
    existing = (
        await session.execute(
            select(CompanyDefaultStage).where(CompanyDefaultStage.company_id == company_id).limit(1)
        )
    ).scalar_one_or_none()

    if existing:
        logger.info("Company default stages already exist for company %s", company_id)
        return

    # Create stages from STAGES definition
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

    logger.info("Created %d default stages for company", len(STAGES))


# Доп. пресеты воронок (кроме «По умолчанию») для формы вакансии. (stage_key, label, is_terminal)
FUNNEL_TEMPLATE_SEEDS = [
    ("Массовый подбор · короткая", [
        ("response", "Отклик", False),
        ("selected", "Отобран", False),
        ("interview", "Интервью", False),
        ("hired", "Нанят", True),
        ("rejected", "Отказ", True),
    ]),
    ("Техническая · с тестовым", [
        ("response", "Отклик", False),
        ("selected", "Отобран", False),
        ("test", "Тест", False),
        ("tech_interview", "Техническое интервью", False),
        ("team_meet", "Встреча с командой", False),
        ("offer", "Оффер", False),
        ("hired", "Нанят", True),
        ("rejected", "Отказ", True),
    ]),
    ("Продажи · 4 этапа", [
        ("response", "Отклик", False),
        ("screening", "Скрининг", False),
        ("roleplay", "Ролевая игра", False),
        ("hired", "Нанят", True),
        ("rejected", "Отказ", True),
    ]),
]


async def seed_funnel_templates(session: AsyncSession) -> None:
    """Доп. шаблоны воронок (Массовый/Технический/Продажи). Идемпотентно (по наличию)."""
    company_id = uuid.UUID(settings.DEFAULT_COMPANY_ID)
    existing = (
        await session.execute(
            select(FunnelTemplate).where(FunnelTemplate.company_id == company_id).limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        logger.info("Funnel templates already exist for company %s", company_id)
        return

    for t_idx, (name, stages) in enumerate(FUNNEL_TEMPLATE_SEEDS, start=1):
        template = FunnelTemplate(company_id=company_id, name=name, order_index=t_idx)
        session.add(template)
        await session.flush()
        for s_idx, (key, label, terminal) in enumerate(stages, start=1):
            session.add(
                FunnelTemplateStage(
                    template_id=template.id,
                    stage_key=key,
                    label=label,
                    order_index=s_idx,
                    is_terminal=terminal,
                )
            )
    logger.info("Created %d funnel templates for company", len(FUNNEL_TEMPLATE_SEEDS))


# Дефолтные шаблоны пульс-опросов адаптации (HR-каденция день 7 / 30 / 90).
# Вопросы — по методике онбординг-замеров (самочувствие, role clarity, выплаты,
# руководитель, автономия, retention/eNPS, открытые ответы). scale — человекочитаемая
# подсказка шкалы. Структура вопроса: {id, text, goal, scale, enabled, optional?}.
SURVEY_TEMPLATE_SEEDS = [
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


async def seed_survey_templates(session: AsyncSession) -> None:
    """Дефолтные шаблоны пульс-опросов адаптации (день 7/30/90). Идемпотентно (по наличию)."""
    company_id = uuid.UUID(settings.DEFAULT_COMPANY_ID)
    existing = (
        await session.execute(
            select(SurveyTemplate).where(SurveyTemplate.company_id == company_id).limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        logger.info("Survey templates already exist for company %s", company_id)
        return

    for tpl in SURVEY_TEMPLATE_SEEDS:
        session.add(
            SurveyTemplate(
                company_id=company_id,
                name=tpl["name"],
                trigger_day=tpl["trigger_day"],
                interval_days=None,
                channels={"telegram": True},
                questions=tpl["questions"],
                is_enabled=True,
            )
        )
    logger.info("Created %d survey templates for company", len(SURVEY_TEMPLATE_SEEDS))


async def main() -> None:
    logger.info("Seeding database")

    async with AsyncSessionLocal() as session:
        try:
            await seed_company(session)
            await session.flush()
            await seed_admin_user(session)
            await seed_reject_reasons(session)
            await seed_glafira_settings(session)
            await seed_company_default_stages(session)
            await seed_funnel_templates(session)
            await seed_survey_templates(session)
            await session.commit()
            logger.info("Seed completed")
        except Exception:
            await session.rollback()
            logger.exception("Seed failed")
            raise


if __name__ == "__main__":
    asyncio.run(main())