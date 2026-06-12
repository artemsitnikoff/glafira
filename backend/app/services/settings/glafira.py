from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from ...models import GlafiraSettings
from ...core.errors import ValidationError
from ...services.audit import audit
from ...config import settings
from ..glafira.models import ALLOWED_MODEL_VALUES, DEFAULT_MODEL


async def get_glafira_settings(session: AsyncSession, company_id: UUID) -> GlafiraSettings:
    """Get Glafira settings for company, auto-create if doesn't exist"""
    result = await session.execute(
        select(GlafiraSettings).where(GlafiraSettings.company_id == company_id)
    )
    settings_obj = result.scalar_one_or_none()

    if not settings_obj:
        # Auto-create with defaults
        settings_obj = GlafiraSettings(company_id=company_id)
        session.add(settings_obj)
        await session.flush()

    return settings_obj


async def get_company_llm_model(session: AsyncSession, company_id: UUID) -> str:
    """
    Получить LLM-модель для оценки резюме конкретной компании.

    Логика fallback:
    1. Если у компании настроена llm_model И она в белом списке → её
    2. Иначе → env GLAFIRA_MODEL
    3. Если и env пуст → дефолт 'anthropic/claude-sonnet-4.6'

    Company-scoped, всегда возвращает валидную модель.
    """
    glafira_settings = await get_glafira_settings(session, company_id)

    # Проверяем company-настройку
    if (glafira_settings.llm_model and
        glafira_settings.llm_model in ALLOWED_MODEL_VALUES):
        return glafira_settings.llm_model

    # Fallback на env
    env_model = settings.GLAFIRA_MODEL
    if env_model and env_model in ALLOWED_MODEL_VALUES:
        return env_model

    # Финальный fallback
    return DEFAULT_MODEL


async def update_glafira_settings(
    session: AsyncSession, company_id: UUID, data, actor_user_id: UUID
) -> GlafiraSettings:
    """Update Glafira settings"""
    settings_obj = await get_glafira_settings(session, company_id)

    # Validation: auto_reject_below < auto_select_above
    auto_reject = data.auto_reject_below if data.auto_reject_below is not None else settings_obj.auto_reject_below
    auto_select = data.auto_select_above if data.auto_select_above is not None else settings_obj.auto_select_above

    if auto_reject is not None and auto_select is not None and auto_reject >= auto_select:
        raise ValidationError("auto_reject_below должен быть меньше auto_select_above")

    # Validate ranges
    if data.auto_reject_below is not None and not (0 <= data.auto_reject_below <= 100):
        raise ValidationError("auto_reject_below должен быть от 0 до 100")

    if data.auto_select_above is not None and not (0 <= data.auto_select_above <= 100):
        raise ValidationError("auto_select_above должен быть от 0 до 100")

    if data.days_no_response is not None and not (0 < data.days_no_response <= 90):
        raise ValidationError("days_no_response должен быть от 1 до 90")

    if data.turnover_source is not None and data.turnover_source not in ("none", "bitrix24"):
        raise ValidationError("turnover_source должен быть 'none' или 'bitrix24'")

    # Store original values for audit
    before = {
        "tone": settings_obj.tone,
        "use_informal": settings_obj.use_informal,
        "emoji_level": settings_obj.emoji_level,
        "auto_reject_below": settings_obj.auto_reject_below,
        "auto_select_above": settings_obj.auto_select_above,
        "days_no_response": settings_obj.days_no_response,
        "stop_words": settings_obj.stop_words,
        "default_mode": settings_obj.default_mode,
        "turnover_source": settings_obj.turnover_source,
        "default_rejection_text": settings_obj.default_rejection_text,
    }

    # Update fields
    if data.tone is not None:
        settings_obj.tone = data.tone
    if data.use_informal is not None:
        settings_obj.use_informal = data.use_informal
    if data.emoji_level is not None:
        settings_obj.emoji_level = data.emoji_level
    if data.auto_reject_below is not None:
        settings_obj.auto_reject_below = data.auto_reject_below
    if data.auto_select_above is not None:
        settings_obj.auto_select_above = data.auto_select_above
    if data.days_no_response is not None:
        settings_obj.days_no_response = data.days_no_response
    if data.stop_words is not None:
        settings_obj.stop_words = data.stop_words
    if data.default_mode is not None:
        settings_obj.default_mode = data.default_mode
    if data.turnover_source is not None:
        settings_obj.turnover_source = data.turnover_source
    if data.default_rejection_text is not None:
        settings_obj.default_rejection_text = data.default_rejection_text

    await session.flush()
    await session.refresh(settings_obj)

    # Audit log
    after = {
        "tone": settings_obj.tone,
        "use_informal": settings_obj.use_informal,
        "emoji_level": settings_obj.emoji_level,
        "auto_reject_below": settings_obj.auto_reject_below,
        "auto_select_above": settings_obj.auto_select_above,
        "days_no_response": settings_obj.days_no_response,
        "stop_words": settings_obj.stop_words,
        "default_mode": settings_obj.default_mode,
        "turnover_source": settings_obj.turnover_source,
        "default_rejection_text": settings_obj.default_rejection_text,
    }

    await audit(
        session,
        action="update_glafira_settings",
        entity_type="glafira_settings",
        entity_id=settings_obj.id,
        before=before,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return settings_obj