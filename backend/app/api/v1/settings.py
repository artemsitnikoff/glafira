from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...schemas.base import MessageResult
from ...schemas.candidate import TagOut
from ...schemas.settings import (
    ProfileOut,
    ProfileUpdate,
    PasswordChange,
    GlafiraSettingsOut,
    GlafiraSettingsUpdate,
    RejectReasonOut,
    RejectReasonCreate,
    RejectReasonUpdate,
    EmailTemplateOut,
    EmailTemplateCreate,
    EmailTemplateUpdate,
    SurveyTemplateOut,
    SurveyTemplateCreate,
    SurveyTemplateUpdate,
    IntegrationOut,
    IntegrationUpdate,
    BillingOut,
)
from ...services.settings import (
    profile,
    glafira,
    reject_reasons,
    email_templates,
    survey_templates,
    integrations,
    billing,
)
from ...services import candidate as candidate_service

router = APIRouter()


# Profile endpoints
@router.get("/profile", response_model=ProfileOut)
async def get_profile(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user profile"""
    user = await profile.get_profile(session, current_user.id)
    return ProfileOut.model_validate(user)


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(
    data: ProfileUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update current user profile"""
    user = await profile.update_profile(session, current_user.id, data, company_id)
    await session.commit()
    return ProfileOut.model_validate(user)


@router.post("/profile/password", response_model=MessageResult)
async def change_password(
    data: PasswordChange,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Change user password"""
    await profile.change_password(
        session, current_user, data.current_password, data.new_password, data.new_password_confirm, company_id
    )
    await session.commit()
    return {"message": "Пароль успешно изменён"}


# Glafira Settings endpoints
@router.get("/glafira", response_model=GlafiraSettingsOut)
async def get_glafira_settings(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Get Glafira settings"""
    settings_obj = await glafira.get_glafira_settings(session, company_id)
    return GlafiraSettingsOut.model_validate(settings_obj)


@router.patch("/glafira", response_model=GlafiraSettingsOut)
async def update_glafira_settings(
    data: GlafiraSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update Glafira settings"""
    settings_obj = await glafira.update_glafira_settings(session, company_id, data, current_user.id)
    await session.commit()
    return GlafiraSettingsOut.model_validate(settings_obj)


# Reject Reasons endpoints
@router.get("/reject-reasons", response_model=list[RejectReasonOut])
async def list_reject_reasons(
    side: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """List reject reasons"""
    reasons = await reject_reasons.list_reject_reasons(session, company_id, side, include_inactive)
    return [RejectReasonOut.model_validate(reason) for reason in reasons]


@router.post("/reject-reasons", response_model=RejectReasonOut, status_code=201)
async def create_reject_reason(
    data: RejectReasonCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Create new reject reason"""
    reason = await reject_reasons.create_reject_reason(session, company_id, data, current_user.id)
    await session.commit()
    return RejectReasonOut.model_validate(reason)


@router.patch("/reject-reasons/{reason_id}", response_model=RejectReasonOut)
async def update_reject_reason(
    reason_id: UUID,
    data: RejectReasonUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update reject reason"""
    reason = await reject_reasons.update_reject_reason(session, reason_id, company_id, data, current_user.id)
    await session.commit()
    return RejectReasonOut.model_validate(reason)


@router.delete("/reject-reasons/{reason_id}", response_model=MessageResult)
async def delete_reject_reason(
    reason_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Delete reject reason (soft delete)"""
    await reject_reasons.delete_reject_reason(session, reason_id, company_id, current_user.id)
    await session.commit()
    return {"message": "Причина отказа удалена"}


# Email Templates endpoints
@router.get("/email-templates", response_model=list[EmailTemplateOut])
async def list_email_templates(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """List email templates"""
    templates = await email_templates.list_email_templates(session, company_id)
    return [EmailTemplateOut.model_validate(template) for template in templates]


@router.get("/email-templates/{template_id}", response_model=EmailTemplateOut)
async def get_email_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Get email template by ID"""
    template = await email_templates.get_email_template(session, template_id, company_id)
    return EmailTemplateOut.model_validate(template)


@router.post("/email-templates", response_model=EmailTemplateOut, status_code=201)
async def create_email_template(
    data: EmailTemplateCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Create new email template"""
    template = await email_templates.create_email_template(session, company_id, data, current_user.id)
    await session.commit()
    return EmailTemplateOut.model_validate(template)


@router.patch("/email-templates/{template_id}", response_model=EmailTemplateOut)
async def update_email_template(
    template_id: UUID,
    data: EmailTemplateUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update email template"""
    template = await email_templates.update_email_template(session, template_id, company_id, data, current_user.id)
    await session.commit()
    return EmailTemplateOut.model_validate(template)


@router.delete("/email-templates/{template_id}", response_model=MessageResult)
async def delete_email_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Delete email template"""
    await email_templates.delete_email_template(session, template_id, company_id, current_user.id)
    await session.commit()
    return {"message": "Email-шаблон удалён"}


# Survey Templates endpoints
@router.get("/survey-templates", response_model=list[SurveyTemplateOut])
async def list_survey_templates(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """List survey templates"""
    templates = await survey_templates.list_survey_templates(session, company_id)
    return [SurveyTemplateOut.model_validate(template) for template in templates]


@router.get("/survey-templates/{template_id}", response_model=SurveyTemplateOut)
async def get_survey_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Get survey template by ID"""
    template = await survey_templates.get_survey_template(session, template_id, company_id)
    return SurveyTemplateOut.model_validate(template)


@router.post("/survey-templates", response_model=SurveyTemplateOut, status_code=201)
async def create_survey_template(
    data: SurveyTemplateCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Create new survey template"""
    template = await survey_templates.create_survey_template(session, company_id, data, current_user.id)
    await session.commit()
    return SurveyTemplateOut.model_validate(template)


@router.patch("/survey-templates/{template_id}", response_model=SurveyTemplateOut)
async def update_survey_template(
    template_id: UUID,
    data: SurveyTemplateUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update survey template"""
    template = await survey_templates.update_survey_template(session, template_id, company_id, data, current_user.id)
    await session.commit()
    return SurveyTemplateOut.model_validate(template)


@router.delete("/survey-templates/{template_id}", response_model=MessageResult)
async def delete_survey_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Delete survey template"""
    await survey_templates.delete_survey_template(session, template_id, company_id, current_user.id)
    await session.commit()
    return {"message": "Survey-шаблон удалён"}


# Integrations endpoints
@router.get("/integrations", response_model=list[IntegrationOut])
async def list_integrations(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """List integrations"""
    integration_list = await integrations.list_integrations(session, company_id)
    return [IntegrationOut.model_validate(integration) for integration in integration_list]


@router.patch("/integrations/{provider}", response_model=IntegrationOut)
async def update_integration(
    provider: str,
    data: IntegrationUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update integration"""
    integration = await integrations.update_integration(session, provider, company_id, data, current_user.id)
    await session.commit()
    return IntegrationOut.model_validate(integration)


# Billing endpoint
@router.get("/billing", response_model=BillingOut)
async def get_billing(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Get billing information"""
    billing_data = await billing.get_billing(session, company_id)
    return BillingOut.model_validate(billing_data)


# Tags endpoint
@router.get("/tags", response_model=list[TagOut])
async def list_tags(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Get all tags for the company"""
    tags = await candidate_service.list_company_tags(session, company_id)
    return [TagOut.model_validate(tag) for tag in tags]