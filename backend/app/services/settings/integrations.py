from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from ...models import Integration
from ...core.errors import NotFoundError, ValidationError
from ...services.audit import audit
from .crypto import encrypt_config, mask_config


async def list_integrations(session: AsyncSession, company_id: UUID) -> list[Integration]:
    """List integrations for company with masked config"""
    result = await session.execute(
        select(Integration)
        .where(Integration.company_id == company_id)
        .order_by(Integration.provider)
    )
    integrations = list(result.scalars().all())

    # Create response objects with masked config (don't mutate ORM objects)
    response_integrations = []
    for integration in integrations:
        response_integration = Integration(
            id=integration.id,
            company_id=integration.company_id,
            provider=integration.provider,
            status=integration.status,
            config=mask_config(integration.config),
            created_at=integration.created_at,
            updated_at=integration.updated_at
        )
        response_integrations.append(response_integration)

    return response_integrations


async def update_integration(
    session: AsyncSession, provider: str, company_id: UUID, data, actor_user_id: UUID
) -> Integration:
    """Update or create integration"""
    # Get existing integration or create new
    result = await session.execute(
        select(Integration)
        .where(Integration.provider == provider)
        .where(Integration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    is_new = integration is None
    if is_new:
        integration = Integration(
            company_id=company_id,
            provider=provider,
            config={},
        )
        session.add(integration)

    # Store original values for audit
    before = {
        "status": integration.status,
        "config_keys": list(integration.config.keys()) if integration.config else [],
    }

    # Update status
    if data.status is not None:
        if data.status not in ("connected", "disconnected"):
            raise ValidationError("status должен быть 'connected' или 'disconnected'")
        integration.status = data.status

    # Update config with encryption
    if data.config is not None:
        try:
            encrypted_config = encrypt_config(data.config)
            integration.config = encrypted_config
        except ValidationError:
            # Re-raise with clear message about FERNET_KEY
            raise

    await session.flush()

    # Audit log (don't log sensitive values)
    after = {
        "status": integration.status,
        "config_keys": list(integration.config.keys()) if integration.config else [],
    }

    action = "create_integration" if is_new else "update_integration"

    await audit(
        session,
        action=action,
        entity_type="integration",
        entity_id=integration.id,
        before=before if not is_new else None,
        after=after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    # Create response object with masked config (don't mutate ORM object)
    response_integration = Integration(
        id=integration.id,
        company_id=integration.company_id,
        provider=integration.provider,
        status=integration.status,
        config=mask_config(integration.config),
        created_at=integration.created_at,
        updated_at=integration.updated_at
    )

    return response_integration