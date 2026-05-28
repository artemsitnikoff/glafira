import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.core.security import get_password_hash
from app.database import AsyncSessionLocal
from app.models import Company, GlafiraSettings, RejectReason, User

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
                continue
            session.add(
                RejectReason(
                    company_id=company_id,
                    side=side,
                    label=label,
                    order_index=idx,
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
            stop_words=[],
            default_mode="A",
        )
    )
    logger.info("Created default Glafira settings")


async def main() -> None:
    logger.info("Seeding database")

    async with AsyncSessionLocal() as session:
        try:
            await seed_company(session)
            await session.flush()
            await seed_admin_user(session)
            await seed_reject_reasons(session)
            await seed_glafira_settings(session)
            await session.commit()
            logger.info("Seed completed")
        except Exception:
            await session.rollback()
            logger.exception("Seed failed")
            raise


if __name__ == "__main__":
    asyncio.run(main())