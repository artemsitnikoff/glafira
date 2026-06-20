"""Сервис OAuth-интеграции Авито Работа (client_credentials per-company).

Авито Job API использует client_credentials — нет браузерного флоу.
Каждая компания хранит свой client_id/secret (Fernet), токен кэшируется
и рефрешится автоматически при истечении.
"""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models.avito_integration import AvitoIntegration
from ....core.errors import ValidationError
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from . import client as avito_client

logger = logging.getLogger(__name__)

# Запас до истечения токена — рефрешить заранее (секунды)
_TOKEN_REFRESH_BUFFER_SEC = 60


async def save_config(
    session: AsyncSession,
    company_id: UUID,
    client_id: str,
    client_secret: str,
    user_id: UUID,
    avito_user_id: str | None = None,
) -> None:
    """Сохранить client_id/secret компании в Авито (Fernet-шифрование).

    Upsert AvitoIntegration. При сохранении новых credentials — сбрасываем
    кэш access_token (потребует рефреша при следующем poll).

    audit: фиксируем факт подключения (НЕ значения credentials).

    Raises:
        ValidationError: если client_id/secret пустые.
    """
    if not client_id or not client_secret:
        raise ValidationError("client_id и client_secret Авито обязательны")

    result = await session.execute(
        select(AvitoIntegration).where(AvitoIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        integration = AvitoIntegration(company_id=company_id)
        session.add(integration)

    integration.client_id = encrypt_text(client_id)
    integration.client_secret = encrypt_text(client_secret)
    # Сброс кэша токена — новые credentials
    integration.access_token = None
    integration.expires_at = None
    integration.connected_by_user_id = user_id
    if avito_user_id is not None:
        integration.avito_user_id = avito_user_id or None

    await session.flush()

    await audit(
        session,
        action="avito_connected",
        entity_type="integration",
        entity_id=integration.id,
        after={"provider": "avito", "action": "credentials_saved"},
        actor_user_id=user_id,
        company_id=company_id,
    )


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус интеграции Авито для компании.

    Returns: {connected: bool, avito_user_id: str|None}
    """
    result = await session.execute(
        select(AvitoIntegration).where(AvitoIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.client_id or not integration.client_secret:
        return {
            "connected": False,
            "avito_user_id": None,
        }

    return {
        "connected": True,
        "avito_user_id": integration.avito_user_id,
    }


async def get_valid_access_token(session: AsyncSession, company_id: UUID) -> tuple[str, str | None]:
    """Получить (или рефрешить) access_token для компании.

    Логика client_credentials (НЕ браузерный флоу):
    1. Загрузить AvitoIntegration компании.
    2. Если access_token валиден (expires_at - buffer > now) → вернуть из кэша.
    3. Иначе: получить НОВЫЙ токен через client.get_access_token(client_id, client_secret),
       сохранить (Fernet) + expires_at, вернуть.

    Returns: (access_token, avito_user_id|None) — avito_user_id для X-Employee-Of.

    Raises:
        ValidationError: нет client_id/secret (не подключено), ошибка Авито.
    """
    result = await session.execute(
        select(AvitoIntegration).where(AvitoIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.client_id or not integration.client_secret:
        raise ValidationError(
            "Авито не подключён: укажите client_id и client_secret в Настройки → Интеграции"
        )

    now = datetime.now(timezone.utc)

    # Проверить кэш токена
    if integration.access_token and integration.expires_at:
        expires_at = integration.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now < expires_at - timedelta(seconds=_TOKEN_REFRESH_BUFFER_SEC):
            # Токен валиден
            return decrypt_text(integration.access_token), integration.avito_user_id

    # Нужен рефреш
    logger.info("[avito] рефреш client_credentials токена company=%s", company_id)
    try:
        client_id = decrypt_text(integration.client_id)
        client_secret = decrypt_text(integration.client_secret)
        token_data = await avito_client.get_access_token(client_id, client_secret)
    except ValidationError:
        raise
    except ValueError as exc:
        # Ошибка Авито (402/429/4xx) → честная ValidationError
        err_str = str(exc)
        if "402" in err_str:
            raise ValidationError(
                "Авито вернул ошибку 402 при получении токена. "
                "Проверьте подписку/доступ к Job API."
            ) from exc
        raise ValidationError(
            f"Ошибка получения токена Авито: {exc}"
        ) from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise ValidationError("Авито не вернул access_token в ответе на client_credentials")

    expires_in = token_data.get("expires_in")
    expires_at_new: datetime | None = None
    if expires_in:
        try:
            expires_at_new = now + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            pass

    # Сохранить кэш (Fernet)
    integration.access_token = encrypt_text(access_token)
    integration.expires_at = expires_at_new
    await session.flush()

    return access_token, integration.avito_user_id


async def link_avito_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    avito_vacancy_id: str,
    company_id: UUID,
    user_id: UUID,
) -> None:
    """Привязать вакансию Глафиры к вакансии Авито (avito_vacancy_id). Company-scoped.

    Raises:
        NotFoundError: вакансия не найдена в рамках компании.
    """
    from ....core.errors import NotFoundError, ConflictError
    from ....models import Vacancy

    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
        )
    )
    vacancy = result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    # Один avito_vacancy_id — не привязывать к двум вакансиям компании
    # (иначе отклики этой вакансии Авито уедут не в ту воронку: vacancy_map last-wins).
    dup = await session.execute(
        select(Vacancy.id).where(
            Vacancy.company_id == company_id,
            Vacancy.avito_vacancy_id == avito_vacancy_id,
            Vacancy.id != vacancy_id,
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise ConflictError("Эта вакансия Авито уже привязана к другой вакансии Глафиры")

    vacancy.avito_vacancy_id = avito_vacancy_id

    await audit(
        session,
        action="avito_vacancy_linked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"avito_vacancy_id": avito_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id,
    )


async def unlink_avito_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    company_id: UUID,
    user_id: UUID,
) -> None:
    """Отвязать вакансию Глафиры от Авито.

    Raises:
        NotFoundError: вакансия не найдена в рамках компании.
    """
    from ....core.errors import NotFoundError
    from ....models import Vacancy

    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
        )
    )
    vacancy = result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    old_id = vacancy.avito_vacancy_id
    vacancy.avito_vacancy_id = None

    await audit(
        session,
        action="avito_vacancy_unlinked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        before={"avito_vacancy_id": old_id},
        after={"avito_vacancy_id": None},
        actor_user_id=user_id,
        company_id=company_id,
    )


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID) -> None:
    """Обнулить credentials и кэш токена (запись остаётся)."""
    result = await session.execute(
        select(AvitoIntegration).where(AvitoIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    if integration is not None:
        integration.client_id = None
        integration.client_secret = None
        integration.access_token = None
        integration.expires_at = None
        integration.avito_user_id = None
        integration.connected_by_user_id = None
        await session.flush()

    await audit(
        session,
        action="avito_disconnected",
        entity_type="integration",
        entity_id=integration.id if integration else None,
        after={"provider": "avito"},
        actor_user_id=user_id,
        company_id=company_id,
    )
