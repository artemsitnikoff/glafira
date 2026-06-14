from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...schemas.base import MessageResult
from ...schemas.candidate import TagOut, TagManageOut, TagCreate, TagUpdate
from ...schemas.settings import (
    ProfileOut,
    ProfileUpdate,
    PasswordChange,
    GlafiraSettingsOut,
    GlafiraSettingsUpdate,
    RejectReasonOut,
    RejectReasonCreate,
    RejectReasonUpdate,
    RejectReasonReorder,
    EmailTemplateOut,
    EmailTemplateCreate,
    EmailTemplateUpdate,
    SurveyTemplateOut,
    SurveyTemplateCreate,
    SurveyTemplateUpdate,
    IntegrationOut,
    IntegrationUpdate,
    BillingOut,
    CompanyDefaultStageOut,
    CompanyDefaultStageCreate,
    CompanyDefaultStageUpdate,
    CompanyDefaultStageReorder,
    FunnelTemplateOut,
    FunnelTemplateCreate,
    FunnelTemplateUpdate,
    AiModelSettingsOut,
    AiModelUpdate,
    AiModelOption,
)
from ...services.settings import (
    profile,
    glafira,
    reject_reasons,
    email_templates,
    survey_templates,
    integrations,
    billing,
    default_funnel,
    funnel_templates as funnel_templates_svc,
    tags as tags_svc,
)
from ...services.glafira.models import ALLOWED_LLM_MODELS, ALLOWED_MODEL_VALUES
from ...core.errors import ValidationError, ForbiddenError
from ...services.audit import audit
from ...models import GlafiraSettings
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
    """Сменить свой пароль.

    История: раньше эндпоинт был отключён (501) — старая форма авто-сабмитила пароль
    вместе с «Сохранить профиль», и autofill менеджера паролей молча перезаписывал пароль
    админа → лок-ауты (см. audit_log, серии change_password парами). Теперь форма ОТДЕЛЬНАЯ
    (модалка, autocomplete=new-password, явный сабмит, НЕ привязана к «Сохранить профиль»),
    поэтому эндпоинт включён. Неверный текущий пароль → 400 (НЕ 401: иначе фронтовый
    axios-интерсептор уйдёт в refresh/logout)."""
    await profile.change_password(
        session,
        current_user,
        current_password=data.current_password,
        new_password=data.new_password,
        new_password_confirm=data.new_password_confirm,
        company_id=company_id,
    )
    await session.commit()
    return MessageResult(message="Пароль изменён")


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


@router.put("/reject-reasons/reorder", response_model=MessageResult)
async def reorder_reject_reasons(
    data: RejectReasonReorder,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Reorder reject reasons by side"""
    await reject_reasons.reorder_reject_reasons(session, company_id, data.side, data.reason_ids, current_user.id)
    await session.commit()
    return {"message": "Причины отказа переупорядочены"}


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


@router.post("/survey-templates/defaults", response_model=list[SurveyTemplateOut])
async def provision_default_survey_templates(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Создать стандартные шаблоны опросов адаптации (день 7/30/90), если их ещё нет.
    Идемпотентно — повторный вызов вернёт уже существующие, не дублируя."""
    templates = await survey_templates.provision_default_survey_templates(session, company_id, current_user.id)
    await session.commit()
    return [SurveyTemplateOut.model_validate(t) for t in templates]


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


# Tags endpoints
@router.get("/tags", response_model=list[TagManageOut])
async def list_tags(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Список тегов компании с числом использований."""
    return await tags_svc.list_tags_with_counts(session, company_id)


@router.post("/tags", response_model=TagManageOut, status_code=201)
async def create_tag(
    data: TagCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Создать тег."""
    tag = await tags_svc.create_tag(
        session, company_id, current_user.id, name=data.name, color=data.color
    )
    await session.commit()
    return await tags_svc.get_tag_manage(session, company_id, tag.id)


@router.patch("/tags/{tag_id}", response_model=TagManageOut)
async def update_tag(
    tag_id: UUID,
    data: TagUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Переименовать тег / сменить цвет."""
    await tags_svc.update_tag(
        session, company_id, current_user.id, tag_id, name=data.name, color=data.color
    )
    await session.commit()
    return await tags_svc.get_tag_manage(session, company_id, tag_id)


@router.delete("/tags/{tag_id}", response_model=MessageResult)
async def delete_tag(
    tag_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Удалить тег (снимается со всех кандидатов)."""
    await tags_svc.delete_tag(session, company_id, current_user.id, tag_id)
    await session.commit()
    return {"message": "Тег удалён"}


# Company Default Funnel endpoints
@router.get("/default-funnel", response_model=list[CompanyDefaultStageOut])
async def get_default_funnel(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Get company default funnel stages.

    Гарантирует инвариант непустоты: если у компании нет дефолт-воронки (0 строк),
    она провижинится из core STAGES (с защищёнными этапами) — «пустого дефолта» не существует.
    """
    from ...core.stages import STAGES
    stages = await default_funnel.ensure_default_stages(session, company_id)
    result = []
    for stage in stages:
        # Add color from STAGES (собираем Pydantic ДО commit — после commit ORM-атрибуты истекают)
        color = STAGES.get(stage.stage_key, type('obj', (object,), {"color": "#9AA3AE"})()).color
        stage_data = CompanyDefaultStageOut.model_validate(stage)
        stage_data.color = color
        result.append(stage_data)
    # Персистим авто-провижининг, если он был (no-op, если этапы уже существовали)
    await session.commit()
    return result


@router.post("/default-funnel", response_model=CompanyDefaultStageOut, status_code=201)
async def create_default_stage(
    data: CompanyDefaultStageCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Create new default funnel stage"""
    stage = await default_funnel.create_default_stage(session, company_id, data, current_user.id)
    await session.commit()

    # Add color from STAGES
    from ...core.stages import STAGES
    color = STAGES.get(stage.stage_key, type('obj', (object,), {"color": "#9AA3AE"})()).color
    stage_data = CompanyDefaultStageOut.model_validate(stage)
    stage_data.color = color
    return stage_data


@router.patch("/default-funnel/{stage_key}", response_model=CompanyDefaultStageOut)
async def update_default_stage(
    stage_key: str,
    data: CompanyDefaultStageUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update default funnel stage (only label)"""
    stage = await default_funnel.update_default_stage(session, stage_key, company_id, data, current_user.id)
    await session.commit()

    # Add color from STAGES
    from ...core.stages import STAGES
    color = STAGES.get(stage.stage_key, type('obj', (object,), {"color": "#9AA3AE"})()).color
    stage_data = CompanyDefaultStageOut.model_validate(stage)
    stage_data.color = color
    return stage_data


@router.delete("/default-funnel/{stage_key}", response_model=MessageResult)
async def delete_default_stage(
    stage_key: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Delete default funnel stage (if not protected)"""
    await default_funnel.delete_default_stage(session, stage_key, company_id, current_user.id)
    await session.commit()
    return {"message": "Этап удален"}


@router.put("/default-funnel/reorder", response_model=MessageResult)
async def reorder_default_stages(
    data: CompanyDefaultStageReorder,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Reorder default funnel stages"""
    await default_funnel.reorder_default_stages(session, company_id, data, current_user.id)
    await session.commit()
    return {"message": "Этапы переупорядочены"}


# ---- Настраиваемые шаблоны воронок (пресеты формы вакансии) ----
# «По умолчанию» здесь НЕ отдаётся — это /default-funnel; форма добавляет его сама.

def _template_stage_color(stage_key: str) -> str:
    from ...core.stages import STAGES
    s = STAGES.get(stage_key)
    return s.color if s else "#9AA3AE"


@router.get("/funnel-templates", response_model=list[FunnelTemplateOut])
async def list_funnel_templates(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Список доп. шаблонов воронок компании (без «По умолчанию»)."""
    templates = await funnel_templates_svc.list_templates(session, company_id)
    return [FunnelTemplateOut.model_validate(t) for t in templates]


@router.post("/funnel-templates", response_model=FunnelTemplateOut, status_code=201)
async def create_funnel_template(
    data: FunnelTemplateCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Создать шаблон (наполняется базовыми этапами)."""
    t = await funnel_templates_svc.create_template(session, company_id, data.name, current_user.id)
    out = FunnelTemplateOut.model_validate(t)
    await session.commit()
    return out


@router.patch("/funnel-templates/{template_id}", response_model=FunnelTemplateOut)
async def rename_funnel_template(
    template_id: UUID,
    data: FunnelTemplateUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Переименовать шаблон."""
    t = await funnel_templates_svc.rename_template(session, template_id, company_id, data.name, current_user.id)
    out = FunnelTemplateOut.model_validate(t)
    await session.commit()
    return out


@router.delete("/funnel-templates/{template_id}", response_model=MessageResult)
async def delete_funnel_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Удалить шаблон (с этапами, каскад)."""
    await funnel_templates_svc.delete_template(session, template_id, company_id, current_user.id)
    await session.commit()
    return {"message": "Шаблон удалён"}


@router.get("/funnel-templates/{template_id}/stages", response_model=list[CompanyDefaultStageOut])
async def get_funnel_template_stages(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Этапы шаблона."""
    stages = await funnel_templates_svc.list_template_stages(session, template_id, company_id)
    result = []
    for s in stages:
        out = CompanyDefaultStageOut.model_validate(s)
        out.color = _template_stage_color(s.stage_key)
        result.append(out)
    return result


@router.post("/funnel-templates/{template_id}/stages", response_model=CompanyDefaultStageOut, status_code=201)
async def add_funnel_template_stage(
    template_id: UUID,
    data: CompanyDefaultStageCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Добавить этап в шаблон."""
    s = await funnel_templates_svc.add_template_stage(session, template_id, company_id, data, current_user.id)
    out = CompanyDefaultStageOut.model_validate(s)
    out.color = _template_stage_color(s.stage_key)
    await session.commit()
    return out


@router.patch("/funnel-templates/{template_id}/stages/{stage_key}", response_model=CompanyDefaultStageOut)
async def rename_funnel_template_stage(
    template_id: UUID,
    stage_key: str,
    data: CompanyDefaultStageUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Переименовать этап шаблона (только label)."""
    s = await funnel_templates_svc.rename_template_stage(session, template_id, stage_key, company_id, data, current_user.id)
    out = CompanyDefaultStageOut.model_validate(s)
    out.color = _template_stage_color(s.stage_key)
    await session.commit()
    return out


@router.delete("/funnel-templates/{template_id}/stages/{stage_key}", response_model=MessageResult)
async def delete_funnel_template_stage(
    template_id: UUID,
    stage_key: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Удалить этап шаблона (защищённые нельзя)."""
    await funnel_templates_svc.delete_template_stage(session, template_id, stage_key, company_id, current_user.id)
    await session.commit()
    return {"message": "Этап удалён"}


@router.put("/funnel-templates/{template_id}/stages/reorder", response_model=MessageResult)
async def reorder_funnel_template_stages(
    template_id: UUID,
    data: CompanyDefaultStageReorder,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Переупорядочить этапы шаблона."""
    await funnel_templates_svc.reorder_template_stages(session, template_id, company_id, data.order, current_user.id)
    await session.commit()
    return {"message": "Этапы переупорядочены"}


# AI Model endpoints
@router.get("/ai-model", response_model=AiModelSettingsOut)
async def get_ai_model_settings(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Get AI model settings.

    RBAC: admin/recruiter могут читать (manager - следует общему паттерну settings)
    """
    # Проверяем RBAC - менеджеры к настройкам не имеют доступа
    if current_user.role == "manager":
        raise ForbiddenError("Доступ к настройкам AI-модели запрещён")

    # Получаем текущую модель для компании
    current_model = await glafira.get_company_llm_model(session, company_id)

    # Проверяем наличие API-ключа OpenRouter
    gs = await glafira.get_glafira_settings(session, company_id)
    has_openrouter_key = bool(gs.openrouter_api_key)

    return AiModelSettingsOut(
        current=current_model,
        options=[AiModelOption(**model) for model in ALLOWED_LLM_MODELS],
        has_openrouter_key=has_openrouter_key
    )


@router.patch("/ai-model", response_model=AiModelSettingsOut)
async def update_ai_model_settings(
    data: AiModelUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Update AI model settings.

    RBAC: admin only - только админ может менять модель оценки
    """
    # Проверяем RBAC - только админ
    if current_user.role != "admin":
        raise ForbiddenError("Только администратор может изменять AI-модель")

    # Валидация: model должна быть в белом списке
    if data.model not in ALLOWED_MODEL_VALUES:
        raise ValidationError("Недопустимая модель. Разрешённые: " + ", ".join(ALLOWED_MODEL_VALUES))

    # Получаем текущую настройку для audit
    settings_obj = await glafira.get_glafira_settings(session, company_id)
    old_model = settings_obj.llm_model
    had_key_before = bool(settings_obj.openrouter_api_key)

    # Обновляем модель
    settings_obj.llm_model = data.model

    # Обновляем API-ключ OpenRouter если передан
    key_updated = False
    if data.openrouter_api_key and data.openrouter_api_key.strip():
        from ...services.settings.crypto import encrypt_text
        settings_obj.openrouter_api_key = encrypt_text(data.openrouter_api_key.strip())
        key_updated = True

    await session.flush()

    # Audit log
    audit_after = {"llm_model": data.model}
    if key_updated:
        audit_after["openrouter_key_set"] = True

    await audit(
        session,
        action="update_ai_model",
        entity_type="glafira_settings",
        entity_id=settings_obj.id,
        before={"llm_model": old_model, "had_openrouter_key": had_key_before},
        after=audit_after,
        actor_user_id=current_user.id,
        actor_type="human",
        company_id=company_id,
    )

    await session.commit()

    # Получаем обновлённую модель и статус ключа
    current_model = await glafira.get_company_llm_model(session, company_id)
    updated_gs = await glafira.get_glafira_settings(session, company_id)
    has_openrouter_key = bool(updated_gs.openrouter_api_key)

    return AiModelSettingsOut(
        current=current_model,
        options=[AiModelOption(**model) for model in ALLOWED_LLM_MODELS],
        has_openrouter_key=has_openrouter_key
    )