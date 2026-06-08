import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.models import (
    Company, User, RejectReason, GlafiraSettings, CompanyDefaultStage,
    FunnelTemplate, SurveyTemplate, Vacancy, Candidate
)
from app.provision_company import provision_company, ProvisionError
from app.core.stages import STAGES


@pytest.mark.asyncio
async def test_provision_company_creates_new_company(db_session: AsyncSession):
    """Test basic company provisioning"""
    company, admin = await provision_company(
        db_session,
        name="ООО Тест",
        admin_email="test@example.com",
        admin_password="TestPassword123",
        admin_full_name="Тестовый Администратор",
        admin_position="CEO"
    )

    # Verify company created
    assert company.name == "ООО Тест"
    assert company.id != uuid.UUID(settings.DEFAULT_COMPANY_ID)

    # Verify admin user created
    assert admin.email == "test@example.com"
    assert admin.full_name == "Тестовый Администратор"
    assert admin.role == "admin"
    assert admin.position == "CEO"

    # CRITICAL TEST: Verify admin is in correct company (not default)
    assert admin.company_id == company.id
    assert admin.company_id != uuid.UUID(settings.DEFAULT_COMPANY_ID)


@pytest.mark.asyncio
async def test_provision_company_initializes_defaults(db_session: AsyncSession):
    """Test that company defaults are properly initialized and scoped"""
    company, admin = await provision_company(
        db_session,
        name="ООО Тест2",
        admin_email="test2@example.com",
        admin_password="TestPassword123",
        admin_full_name="Администратор2"
    )

    # Verify company default stages created
    stages = (
        await db_session.execute(
            select(CompanyDefaultStage).where(CompanyDefaultStage.company_id == company.id)
        )
    ).scalars().all()
    assert len(stages) == len(STAGES)

    # Verify reject reasons created
    reject_reasons = (
        await db_session.execute(
            select(RejectReason).where(RejectReason.company_id == company.id)
        )
    ).scalars().all()
    assert len(reject_reasons) > 0

    # Verify Glafira settings created
    glafira_settings = (
        await db_session.execute(
            select(GlafiraSettings).where(GlafiraSettings.company_id == company.id)
        )
    ).scalar_one_or_none()
    assert glafira_settings is not None

    # Verify funnel templates created
    funnel_templates = (
        await db_session.execute(
            select(FunnelTemplate).where(FunnelTemplate.company_id == company.id)
        )
    ).scalars().all()
    assert len(funnel_templates) > 0

    # Verify survey templates created
    survey_templates = (
        await db_session.execute(
            select(SurveyTemplate).where(SurveyTemplate.company_id == company.id)
        )
    ).scalars().all()
    assert len(survey_templates) > 0


@pytest.mark.asyncio
async def test_provision_company_email_conflict(db_session: AsyncSession, admin_user: User):
    """Test that provisioning fails when email is already taken"""

    with pytest.raises(ProvisionError) as exc_info:
        await provision_company(
            db_session,
            name="ООО Конфликт",
            admin_email=admin_user.email,  # Use existing email
            admin_password="TestPassword123",
            admin_full_name="Дублированный Админ"
        )

    assert "already taken" in str(exc_info.value)

    # Verify no company was created
    companies = (
        await db_session.execute(select(Company).where(Company.name == "ООО Конфликт"))
    ).scalars().all()
    assert len(companies) == 0


@pytest.mark.asyncio
async def test_provision_company_clean_start(db_session: AsyncSession):
    """Test that new company starts with zero vacancies and candidates"""
    company, admin = await provision_company(
        db_session,
        name="Чистая Компания",
        admin_email="clean@example.com",
        admin_password="TestPassword123",
        admin_full_name="Чистый Админ"
    )

    # Verify no vacancies
    vacancies = (
        await db_session.execute(
            select(Vacancy).where(Vacancy.company_id == company.id)
        )
    ).scalars().all()
    assert len(vacancies) == 0

    # Verify no candidates
    candidates = (
        await db_session.execute(
            select(Candidate).where(Candidate.company_id == company.id)
        )
    ).scalars().all()
    assert len(candidates) == 0


@pytest.mark.asyncio
async def test_provision_company_defaults_isolation(db_session: AsyncSession, admin_user: User):
    """Test that defaults are properly isolated between companies"""

    # Create new company
    company, admin = await provision_company(
        db_session,
        name="Изолированная Компания",
        admin_email="isolated@example.com",
        admin_password="TestPassword123",
        admin_full_name="Изолированный Админ"
    )

    # Get stages for new company
    new_company_stages = (
        await db_session.execute(
            select(CompanyDefaultStage).where(CompanyDefaultStage.company_id == company.id)
        )
    ).scalars().all()

    # Get stages for existing company
    existing_company_stages = (
        await db_session.execute(
            select(CompanyDefaultStage).where(CompanyDefaultStage.company_id == admin_user.company_id)
        )
    ).scalars().all()

    # Verify isolation: new company stages don't include existing company stages
    new_stage_ids = {stage.id for stage in new_company_stages}
    existing_stage_ids = {stage.id for stage in existing_company_stages}

    assert new_stage_ids.isdisjoint(existing_stage_ids)
    assert len(new_company_stages) == len(STAGES)

    # Verify new company can't see existing company reject reasons
    new_reject_reasons = (
        await db_session.execute(
            select(RejectReason).where(RejectReason.company_id == company.id)
        )
    ).scalars().all()

    existing_reject_reasons = (
        await db_session.execute(
            select(RejectReason).where(RejectReason.company_id == admin_user.company_id)
        )
    ).scalars().all()

    new_reason_ids = {reason.id for reason in new_reject_reasons}
    existing_reason_ids = {reason.id for reason in existing_reject_reasons}

    assert new_reason_ids.isdisjoint(existing_reason_ids)


@pytest.mark.asyncio
async def test_provision_company_default_position(db_session: AsyncSession):
    """Test default admin position"""
    company, admin = await provision_company(
        db_session,
        name="ООО Дефолт",
        admin_email="default@example.com",
        admin_password="TestPassword123",
        admin_full_name="Дефолтный Админ"
        # admin_position not provided - should default to "Администратор"
    )

    assert admin.position == "Администратор"