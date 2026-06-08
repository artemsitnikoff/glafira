import argparse
import asyncio
import logging
import os
import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.core.security import get_password_hash
from app.database import AsyncSessionLocal
from app.models import Company, User
from app.seed import (
    seed_reject_reasons,
    seed_glafira_settings,
    seed_company_default_stages,
    seed_funnel_templates,
    seed_survey_templates,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


class ProvisionError(Exception):
    """Error during company provisioning"""
    pass


async def provision_company(
    session: AsyncSession,
    *,
    name: str,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
    admin_position: str = "Администратор",
) -> tuple[Company, User]:
    """
    Provision a new company tenant with admin user and default settings.

    Args:
        session: Database session
        name: Company name
        admin_email: Admin user email
        admin_password: Admin user password
        admin_full_name: Admin user full name
        admin_position: Admin user position

    Returns:
        Tuple of (company, admin_user)

    Raises:
        ProvisionError: If email is already taken
    """
    # Check if email is already taken
    existing_user = (
        await session.execute(select(User).where(User.email == admin_email))
    ).scalar_one_or_none()

    if existing_user:
        raise ProvisionError(f"Email {admin_email} is already taken by another user")

    # Create new company with explicit UUID
    company = Company(
        id=uuid.uuid4(),
        name=name
    )
    session.add(company)
    await session.flush()

    # Create admin user with explicit company_id (CRITICAL: prevents falling into default company)
    admin_user = User(
        company_id=company.id,  # EXPLICIT company_id - this fixes the security vulnerability
        email=admin_email,
        password_hash=get_password_hash(admin_password),
        full_name=admin_full_name,
        role="admin",
        position=admin_position,
    )
    session.add(admin_user)
    await session.flush()

    # Initialize company defaults with the new company_id
    await seed_reject_reasons(session, company_id=company.id)
    await seed_glafira_settings(session, company_id=company.id)
    await seed_company_default_stages(session, company_id=company.id)
    await seed_funnel_templates(session, company_id=company.id)
    await seed_survey_templates(session, company_id=company.id)

    logger.info(
        "Provisioned company: %s (id=%s), admin: %s",
        company.name,
        company.id,
        admin_user.email
    )

    return company, admin_user


async def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a new company tenant")
    parser.add_argument("--name", required=True, help="Company name")
    parser.add_argument("--admin-email", required=True, help="Admin user email")
    parser.add_argument("--admin-name", required=True, help="Admin user full name")
    parser.add_argument("--admin-position", default="Администратор", help="Admin user position")
    parser.add_argument("--admin-password", help="Admin user password (optional, will be generated if not provided)")

    args = parser.parse_args()

    # Determine password
    admin_password = args.admin_password
    if not admin_password:
        admin_password = os.getenv("PROVISION_ADMIN_PASSWORD")
    if not admin_password:
        admin_password = secrets.token_urlsafe(12)

    async with AsyncSessionLocal() as session:
        try:
            company, admin_user = await provision_company(
                session,
                name=args.name,
                admin_email=args.admin_email,
                admin_password=admin_password,
                admin_full_name=args.admin_name,
                admin_position=args.admin_position,
            )
            await session.commit()

            logger.info("Company provisioning completed successfully")

            # Print credentials for safe storage (NOT logged)
            print("\n" + "="*60)
            print("NEW COMPANY PROVISIONED - SAVE THESE CREDENTIALS SECURELY")
            print("="*60)
            print(f"Company ID: {company.id}")
            print(f"Company Name: {company.name}")
            print(f"Admin Email: {admin_user.email}")
            print(f"Admin Password: {admin_password}")
            print("="*60)
            print("Store these credentials in a secure location!")
            print("="*60)

        except Exception as e:
            await session.rollback()
            logger.error("Company provisioning failed: %s", str(e))
            raise


if __name__ == "__main__":
    asyncio.run(main())