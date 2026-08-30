"""Сервис для работы с hh.ru интеграцией"""

import secrets
from datetime import datetime, timezone, timedelta, date
from uuid import UUID
from typing import Optional

from sqlalchemy import select, delete, text
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import StaleDataError, ObjectDeletedError
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import (
    HhIntegration, HhOauthState, UserHhIntegration, Vacancy, Application, Candidate,
    CandidateExperience, CandidateSkill, CandidateEducation, Message,
    Document, Event,
)
from ....models.settings import GlafiraSettings
from ....config import settings
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....services.chat_log import log_chat
from ....services.company_display import resolve_company_display_name
from ....services.storage import storage_service
from ....core.errors import ValidationError, NotFoundError
from ....services.phone import normalize_phone
from ....services.candidate_dedup import find_duplicate_candidates
from ....services.photo_proxy import build_photo_proxy_url
from ....schemas.vacancy import VacancyCreate
from ....services.vacancy import create_vacancy
from . import client as hh_client

import logging

logger = logging.getLogger(__name__)


def _hh_log(msg: str) -> None:
    """Персистентный журнал синхронизации откликов hh (общий том, cat-абельный).
    Пишет ОТКУДА взяли кандидата и что с резюме. Best-effort — НЕ ронять импорт."""
    try:
        path = getattr(settings, "HH_SYNC_LOG_PATH", "") or ""
        if not path:
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{ts}Z {msg}\n")
    except Exception:
        pass


def _resolve_app_creds(integration: Optional["HhIntegration"] = None) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Ключ приложения Глафиры (client_id, client_secret, redirect_uri).

    Источник правды — env (.env на VPS): один OAuth-app Глафиры авторизует любого
    работодателя, в UI ничего вводить не надо. Legacy DB-колонки (client_id/secret/
    redirect_uri в hh_integrations) остаются СТРАХОВКОЙ для арендаторов, подключённых
    до перехода на env — если env пуст, берём из них. Возвращает (client_id, client_secret, redirect_uri).
    """
    client_id = settings.HH_CLIENT_ID or (integration.client_id if integration else None)
    redirect_uri = settings.HH_REDIRECT_URI or (integration.redirect_uri if integration else None)
    if settings.HH_CLIENT_SECRET:
        client_secret = settings.HH_CLIENT_SECRET
    elif integration and integration.client_secret:
        client_secret = decrypt_text(integration.client_secret)
    else:
        client_secret = None
    return client_id, client_secret, redirect_uri


def _hh_phone(contacts) -> Optional[str]:
    """Телефон из контактов hh-резюме (если hh их не скрыл)."""
    for c in contacts or []:
        if (c.get("type") or {}).get("id") in ("cell", "home", "work"):
            v = c.get("value")
            if isinstance(v, dict):
                return v.get("formatted") or v.get("number")
            if isinstance(v, str):
                return v
    return None


def _hh_email(contacts) -> Optional[str]:
    """Email из контактов hh-резюме (если не скрыт)."""
    for c in contacts or []:
        if (c.get("type") or {}).get("id") == "email":
            v = c.get("value")
            if isinstance(v, str):
                return v
    return None


def _hh_period(start, end) -> Optional[str]:
    """Период работы строкой из start/end (формат hh 'YYYY-MM-DD' | None)."""
    if not start and not end:
        return None
    s = (start or "")[:7] if start else "?"
    e = (end or "")[:7] if end else "по наст. время"
    return f"{s} — {e}"


def build_candidate_resume_sections(
    candidate_id: UUID,
    company_id: UUID,
    resume: dict,
) -> list:
    """Строит список ORM-объектов секций резюме из hh-резюме.

    Возвращает CandidateExperience / CandidateSkill / CandidateEducation без
    добавления в сессию — вызывающий сам делает session.add(row).

    Используется совместно с import_response (через рефакторинг) и
    smart_search (take_selected / invite_selected) для заполнения карточки.
    Пустые position / skill / institution пропускаются (не создают строк).
    """
    rows: list = []

    for idx, exp in enumerate(resume.get("experience") or []):
        pos = (exp.get("position") or "").strip()
        if not pos:
            continue
        rows.append(CandidateExperience(
            company_id=company_id,
            candidate_id=candidate_id,
            position=pos[:255],
            company=((exp.get("company") or "")[:255] or None),
            period=_hh_period(exp.get("start"), exp.get("end")),
            description=(exp.get("description") or None),
            order_index=idx,
        ))

    for idx, sk in enumerate(resume.get("skill_set") or []):
        s = str(sk).strip()
        if s:
            rows.append(CandidateSkill(
                company_id=company_id,
                candidate_id=candidate_id,
                skill=s[:120],
                order_index=idx,
            ))

    for idx, ed in enumerate((resume.get("education") or {}).get("primary") or []):
        inst = (ed.get("name") or ed.get("organization") or "").strip()
        if not inst:
            continue
        rows.append(CandidateEducation(
            company_id=company_id,
            candidate_id=candidate_id,
            institution=inst[:255],
            specialty=((ed.get("organization") or ed.get("result") or "")[:255] or None),
            years=(str(ed.get("year"))[:40] if ed.get("year") else None),
            order_index=idx,
        ))

    return rows


async def get_integration(session: AsyncSession, company_id: UUID) -> Optional[HhIntegration]:
    """Получает интеграцию hh.ru для компании"""
    result = await session.execute(
        select(HhIntegration).where(HhIntegration.company_id == company_id)
    )
    return result.scalar_one_or_none()


async def save_config(session: AsyncSession, company_id: UUID, user_id: UUID, client_id: str, client_secret: str, redirect_uri: str) -> HhIntegration:
    """
    Сохраняет конфигурацию hh.ru для компании

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя
        client_id: ID приложения hh.ru
        client_secret: секрет приложения hh.ru
        redirect_uri: redirect URI приложения hh.ru

    Returns:
        HhIntegration: созданная/обновленная интеграция

    Raises:
        ValidationError: при пустых credentials
    """
    # Валидация
    if not client_id or not client_secret or not redirect_uri:
        raise ValidationError("Все поля обязательны: client_id, client_secret, redirect_uri")

    # Проверяем существующую интеграцию
    existing = await get_integration(session, company_id)

    # Шифруем client_secret
    encrypted_secret = encrypt_text(client_secret)

    if existing:
        # Обновляем существующую конфигурацию
        old_client_id = existing.client_id
        existing.client_id = client_id
        existing.client_secret = encrypted_secret
        existing.redirect_uri = redirect_uri

        # Если client_id изменился, обнуляем токены (токены от другого приложения)
        if old_client_id != client_id:
            existing.access_token = None
            existing.refresh_token = None
            existing.expires_at = None
            existing.hh_employer_id = None

        integration = existing
    else:
        # Создаем новую
        integration = HhIntegration(
            company_id=company_id,
            client_id=client_id,
            client_secret=encrypted_secret,
            redirect_uri=redirect_uri
        )
        session.add(integration)

    await session.commit()

    # Записываем в аудит
    await audit(
        session,
        action="hh_config_saved",
        entity_type="hh_integration",
        entity_id=integration.id,
        after={
            "client_id": client_id,
            "redirect_uri": redirect_uri
        },
        actor_user_id=user_id,
        company_id=company_id
    )
    await session.commit()

    return integration


async def start_oauth(session: AsyncSession, company_id: UUID, user_id: UUID, kind: str = "company") -> str:
    """
    Начинает OAuth flow, создает state запись и возвращает authorize URL

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя
        kind: 'company' (общий токен работодателя → hh_integrations) или 'personal'
              (персональный токен рекрутёра → user_hh_integrations). Пишется в state;
              callback (complete_oauth) по нему маршрутизирует. company_id/user_id
              берутся ИЗ state (не из куки) — OAuth-безопасность.

    Returns:
        str: URL для редиректа в браузер

    Raises:
        ValidationError: при отсутствии конфигурации
    """
    # Ключ приложения Глафиры — из env (.env), legacy DB-колонки как страховка.
    # Один OAuth-app авторизует любого работодателя — вводить ничего не нужно.
    integration = await get_integration(session, company_id)
    client_id, _, redirect_uri = _resolve_app_creds(integration)
    if not client_id or not redirect_uri:
        raise ValidationError("hh.ru не настроен: задайте ключ приложения в .env (HH_CLIENT_ID/HH_REDIRECT_URI)")

    # Генерируем уникальный state
    state = secrets.token_urlsafe(32)

    # Чистим истёкшие OAuth-state этой компании (иначе брошенные «Подключить»
    # без callback копятся в hh_oauth_states навсегда)
    now_dt = datetime.now(timezone.utc)
    await session.execute(
        delete(HhOauthState).where(
            HhOauthState.company_id == company_id,
            HhOauthState.expires_at < now_dt,
        )
    )

    # Создаем запись state (expires через 10 минут)
    expires_at = now_dt + timedelta(minutes=10)

    oauth_state = HhOauthState(
        state=state,
        company_id=company_id,
        user_id=user_id,
        kind=kind,
        expires_at=expires_at
    )

    session.add(oauth_state)
    await session.commit()

    # Строим authorize URL ключом приложения Глафиры (env, fallback на legacy DB)
    authorize_url = hh_client.build_authorize_url(state, client_id, redirect_uri)

    return authorize_url


async def complete_oauth(session: AsyncSession, code: str, state: str) -> HhIntegration:
    """
    Завершает OAuth flow, обменивает код на токены и создает/обновляет интеграцию

    Args:
        session: DB session
        code: authorization code от hh.ru
        state: state для проверки CSRF

    Returns:
        HhIntegration: созданная/обновленная интеграция

    Raises:
        ValidationError: при невалидном state или ошибке API
    """
    # Находим state запись
    result = await session.execute(
        select(HhOauthState).where(HhOauthState.state == state)
    )
    oauth_state = result.scalar_one_or_none()

    if not oauth_state:
        raise ValidationError("Невалидный или истекший state")

    # Проверяем срок действия
    if datetime.now(timezone.utc) > oauth_state.expires_at:
        # Удаляем истекший state
        await session.delete(oauth_state)
        await session.commit()
        raise ValidationError("Истекший state")

    # Персональный флоу рекрутёра → отдельная ветка (токен в user_hh_integrations).
    # kind берётся ИЗ state (не из куки). None/'company' (дефолт) → общий флоу ниже,
    # который остаётся байт-в-байт прежним — company-flow не сломан.
    if (oauth_state.kind or "company") == "personal":
        return await _complete_oauth_personal(session, oauth_state, code)

    company_id = oauth_state.company_id
    user_id = oauth_state.user_id

    try:
        # Ключ приложения Глафиры — env (.env), fallback на legacy DB-колонки.
        integration_config = await get_integration(session, company_id)
        client_id, client_secret, redirect_uri = _resolve_app_creds(integration_config)
        if not client_id or not client_secret or not redirect_uri:
            raise ValidationError("hh.ru не настроен: задайте ключ приложения в .env")

        # Обмениваем код на токены
        token_data = await hh_client.exchange_code(
            code,
            client_id,
            client_secret,
            redirect_uri
        )

        # Получаем информацию о пользователе
        me_data = await hh_client.get_me(token_data["access_token"])

        # Извлекаем employer_id
        hh_employer_id = None
        if "employer" in me_data and me_data["employer"] and "id" in me_data["employer"]:
            hh_employer_id = str(me_data["employer"]["id"])

        # Вычисляем время истечения токена
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

        # Шифруем токены
        encrypted_access = encrypt_text(token_data["access_token"])
        encrypted_refresh = encrypt_text(token_data["refresh_token"])

        # Строка интеграции хранит ТОЛЬКО токены работодателя (ключ приложения — в env).
        # Создаём при первом подключении, иначе обновляем.
        integration_config = await get_integration(session, company_id)
        if integration_config:
            integration_config.access_token = encrypted_access
            integration_config.refresh_token = encrypted_refresh
            integration_config.expires_at = expires_at
            integration_config.hh_employer_id = hh_employer_id
            integration_config.connected_by_user_id = user_id
            integration = integration_config
        else:
            integration = HhIntegration(
                company_id=company_id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                hh_employer_id=hh_employer_id,
                connected_by_user_id=user_id,
            )
            session.add(integration)
            await session.flush()

        # Удаляем использованный state
        await session.delete(oauth_state)

        # Сохраняем изменения
        await session.commit()

        # Записываем в аудит
        if user_id:
            await audit(
                session,
                action="hh_connected",
                entity_type="hh_integration",
                entity_id=integration.id,
                after={"hh_employer_id": hh_employer_id},
                actor_user_id=user_id,
                company_id=company_id
            )
            await session.commit()  # audit() добавляет запись после основного commit — персистим её

        return integration

    except Exception:
        # Гасим state при ошибке. НО удаляем его ТОЛЬКО если он ещё в сессии/persistent:
        # на успешном пути state уже удалён-и-закоммичен (стал detached), и повторный
        # delete detached-объекта поднял бы ВТОРИЧНОЕ исключение, замаскировав исходное
        # (и оставив connect без audit-строки). Сам delete/commit оборачиваем, чтобы
        # вторичный сбой не затирал первичную ошибку — её и пробрасываем bare raise.
        try:
            if oauth_state in session:
                await session.delete(oauth_state)
                await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass
        raise


# ===========================================================================
# ПЕРСОНАЛЬНЫЙ hh-токен рекрутёра (user_hh_integrations)
# ---------------------------------------------------------------------------
# Общий компанийный HhIntegration ОСТАЁТСЯ (фон/кроны/отклики/фолбэк). Персональный
# токен рекрутёра нужен для интерактивных операций (просмотр резюме/чат/поиск), чтобы
# суточный лимит hh и атрибуция действий были ПЕРСОНАЛЬНЫМИ, а не общими на компанию.
# ФАЗА 2 (готово): ИНТЕРАКТИВНЫЕ вызовы (просмотр резюме/чат/поиск/умный подбор/
# автоподбор) маршрутизированы на get_hh_token_for_user(user_id=инициатор) — квота
# и атрибуция персональны. get_valid_access_token НЕ тронут: на нём остаются фон/
# кроны/отклики/фолбэк (poll_*, sync_company_rejections, auto_qa, публичная запись
# на интервью, а также bulk-оценка Автоподбора в отдельном воркере — без юзера).
# ===========================================================================


async def get_user_integration(
    session: AsyncSession, company_id: UUID, user_id: UUID
) -> Optional[UserHhIntegration]:
    """Персональная hh-интеграция пользователя (строго company-scoped, §2.3).

    Скоуп по company_id + user_id — defense-in-depth: персональный токен юзера компании A
    не должен возвращаться при запросе от компании B.
    """
    result = await session.execute(
        select(UserHhIntegration).where(
            UserHhIntegration.user_id == user_id,
            UserHhIntegration.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


async def _complete_oauth_personal(
    session: AsyncSession, oauth_state: HhOauthState, code: str
) -> UserHhIntegration:
    """Завершение ПЕРСОНАЛЬНОГО OAuth-флоу: токен → user_hh_integrations для state.user_id.

    company_id/user_id берутся ИЗ state (не из куки — callback публичный).
    Ключ приложения Глафиры — env (.env), fallback на legacy DB-колонки компанийной
    HhIntegration (тот же OAuth-app). Токены шифруются Fernet, как в company-флоу.
    Upsert по UNIQUE(user_id): существующую строку обновляем, иначе создаём.
    """
    company_id = oauth_state.company_id
    user_id = oauth_state.user_id

    try:
        if not user_id:
            raise ValidationError("Персональное подключение hh.ru требует пользователя в state")

        # Ключ приложения — env, fallback на legacy DB-колонки компанийной интеграции.
        company_integration = await get_integration(session, company_id)
        client_id, client_secret, redirect_uri = _resolve_app_creds(company_integration)
        if not client_id or not client_secret or not redirect_uri:
            raise ValidationError("hh.ru не настроен: задайте ключ приложения в .env")

        # Обмениваем код на токены
        token_data = await hh_client.exchange_code(code, client_id, client_secret, redirect_uri)

        # Информация о менеджере/работодателе
        me_data = await hh_client.get_me(token_data["access_token"])
        hh_employer_id = None
        if isinstance(me_data.get("employer"), dict) and me_data["employer"].get("id"):
            hh_employer_id = str(me_data["employer"]["id"])
        # id менеджера-рекрутёра на hh (идентифицирует конкретного пользователя)
        hh_manager_id = None
        if isinstance(me_data.get("manager"), dict) and me_data["manager"].get("id"):
            hh_manager_id = str(me_data["manager"]["id"])
        elif me_data.get("id"):
            hh_manager_id = str(me_data["id"])

        # === Гард работодателя: личный аккаунт ДОЛЖЕН быть тем же работодателем ===
        # Личный токен рекрутёра работает под тем же employer'ом, что и общий аккаунт
        # компании — иначе рекрутёр подключил бы ЧУЖОЙ hh-аккаунт (другой работодатель),
        # и его интерактивные действия ушли бы мимо квоты/атрибуции компании. company_integration
        # (общий hh компании) получен выше для creds; его hh_employer_id — эталон.
        company_employer_id = company_integration.hh_employer_id if company_integration else None
        if not company_integration or not company_employer_id:
            raise ValidationError("Сначала подключите общий аккаунт hh компании")
        if not hh_employer_id or str(hh_employer_id) != str(company_employer_id):
            raise ValidationError(
                "Подключите аккаунт вашей компании на hh — этот аккаунт относится к другому работодателю"
            )

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
        encrypted_access = encrypt_text(token_data["access_token"])
        encrypted_refresh = encrypt_text(token_data["refresh_token"])

        # Upsert по user_id (UNIQUE). Скоуп company_id — юзер один в своей компании.
        integration = await get_user_integration(session, company_id, user_id)
        if integration:
            integration.access_token = encrypted_access
            integration.refresh_token = encrypted_refresh
            integration.expires_at = expires_at
            integration.hh_employer_id = hh_employer_id
            integration.hh_manager_id = hh_manager_id
            integration.connected_at = datetime.now(timezone.utc)
        else:
            integration = UserHhIntegration(
                company_id=company_id,
                user_id=user_id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                hh_employer_id=hh_employer_id,
                hh_manager_id=hh_manager_id,
                connected_at=datetime.now(timezone.utc),
            )
            session.add(integration)
            await session.flush()

        # Использованный state удаляем
        await session.delete(oauth_state)
        await session.commit()

        # Аудит (§2.2) — изменяющее действие
        await audit(
            session,
            action="hh_personal_connected",
            entity_type="user_hh_integration",
            entity_id=integration.id,
            after={"hh_employer_id": hh_employer_id, "hh_manager_id": hh_manager_id},
            actor_user_id=user_id,
            company_id=company_id,
        )
        await session.commit()

        return integration

    except Exception:
        # Гасим state ТОЛЬКО если он ещё в сессии/persistent. На успешном пути state уже
        # удалён-и-закоммичен (detached) — повторный delete поднял бы ВТОРИЧНОЕ исключение,
        # замаскировав исходное (и оставив connect без audit). delete/commit обёрнуты,
        # чтобы вторичный сбой не затирал первичную ошибку — её пробрасываем bare raise.
        try:
            if oauth_state in session:
                await session.delete(oauth_state)
                await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass
        raise


async def _get_valid_personal_token(
    session: AsyncSession, company_id: UUID, user_id: UUID
) -> Optional[str]:
    """Валидный персональный access-токен пользователя (с авто-рефрешем), или None.

    None — если персональной интеграции нет / токен обнулён (→ вызывающий уходит на
    общий токен). Рефреш сериализуется FOR UPDATE на строке user_hh_integrations
    (по образцу get_valid_access_token, но per-user). Рефреш ключом приложения Глафиры
    (env, fallback legacy DB-колонки компанийной интеграции). Сбой рефреша существующего
    токена → ValidationError (НЕ маскируем молчаливым откатом на общий).
    """
    integration = await get_user_integration(session, company_id, user_id)
    if not integration:
        return None
    if not integration.access_token or not integration.expires_at:
        return None

    now = datetime.now(timezone.utc)
    if now < integration.expires_at - timedelta(minutes=5):
        return decrypt_text(integration.access_token)

    # Токен истёк/истекает — рефреш под блокировкой строки (сериализуем гонку воркеров).
    # ⚠️ Гонка с disconnect_personal: строку user_hh_integrations мог удалить конкурентный
    # процесс между нашим чтением и рефрешем → refresh(with_for_update) поднимет ошибку
    # об исчезнувшей/detached-строке. В этом случае чисто уходим на общий токен (None):
    # get_hh_token_for_user подхватит и вернёт компанийный. Прочие ошибки НЕ глотаем.
    try:
        await session.refresh(integration, with_for_update=True)
    except (StaleDataError, ObjectDeletedError, InvalidRequestError):
        return None
    now = datetime.now(timezone.utc)
    # Пока ждали блокировку — сосед мог обновить. Перепроверяем.
    if integration.access_token and integration.expires_at and now < integration.expires_at - timedelta(minutes=5):
        await session.commit()
        return decrypt_text(integration.access_token)

    try:
        company_integration = await get_integration(session, company_id)
        client_id, client_secret, _ = _resolve_app_creds(company_integration)
        if not client_id or not client_secret:
            raise ValidationError("hh.ru не настроен: задайте ключ приложения в .env")

        current_refresh = decrypt_text(integration.refresh_token)
        token_data = await hh_client.refresh_tokens(current_refresh, client_id, client_secret)

        integration.access_token = encrypt_text(token_data["access_token"])
        integration.refresh_token = encrypt_text(token_data["refresh_token"])
        integration.expires_at = now + timedelta(seconds=token_data["expires_in"])
        await session.commit()

        return token_data["access_token"]
    except Exception as e:
        raise ValidationError(f"Не удалось обновить персональный токен hh.ru: {e}")


async def get_hh_token_for_user(
    session: AsyncSession, *, company_id: UUID, user_id: Optional[UUID] = None
) -> Optional[str]:
    """Селектор токена для ИНТЕРАКТИВНЫХ операций рекрутёра.

    Приоритет: персональный валидный токен пользователя (user_hh_integrations, рефреш
    per-user под FOR UPDATE), ИНАЧЕ общий компанийный токен (get_valid_access_token).

    ⚠️ user_id=None — инициатора НЕТ (фон/крон/вызов без юзерского контекста): персональный
    токен НЕ ищем, сразу общий компанийный (= прежнее поведение get_valid_access_token, но
    без исключения: None вместо raise). Это позволяет единообразно звать селектор и в
    интерактивных, и в «общих» путях: есть user_id → личный с фолбэком, нет → общий.

    ⚠️ get_valid_access_token НЕ тронут — на нём висят фон/кроны/отклики. Фолбэк
    ловит его бизнес-ошибки (NotFoundError/ValidationError) и возвращает None, если
    у компании тоже нет валидного общего токена — вызывающий покажет честную ошибку.
    """
    # Персональный токен (если есть инициатор и он подключён). Ошибка рефреша СВОЕГО
    # токена пробрасывается — молчаливый уход на общий токен вернул бы ту самую проблему
    # (общий лимит/атрибуция). ⚠️ Исчерпание квоты просмотров (500/сут) НЕ детектируется
    # здесь: селектор отдаёт валидный личный токен, а лимит вскрывается уже на просмотре
    # (get_resume_by_id → ValidationError «квота») — по ней вызывающий останавливается,
    # НЕ уходя молча на общий (иначе выжжём и его). TODO: явный детект исчерпания личной
    # квоты на просмотрах, когда формат 429/лимит-ответа hh будет однозначно пиниться.
    if user_id is not None:
        personal = await _get_valid_personal_token(session, company_id, user_id)
        if personal:
            return personal

    # Своего нет (или инициатора нет) → общий компанийный токен (фон/кроны используют его же).
    try:
        return await get_valid_access_token(session, company_id)
    except (NotFoundError, ValidationError):
        return None


# ---------------------------------------------------------------------------
# Каскад квоты ПРОСМОТРОВ резюме: личные 500/сут кончились → добираем из общего
# ---------------------------------------------------------------------------

def _is_resume_view_limit_error(exc: Exception) -> bool:
    """Best-effort: это ответ hh «исчерпан суточный лимит просмотров резюме» (429)?

    Строим детектор ТОЛЬКО из того, что код УЖЕ знает про формат ошибки, чтобы не
    гадать:
    - hh_client.get_resume_by_id при HTTP 429 поднимает ValidationError с текстом
      «Превышена квота просмотров резюме hh.ru» → ключевое слово «квота»;
    - auto_search.get_auto_candidate_detail ре-оборачивает это в «Превышен суточный
      лимит просмотров резюме hh» → ключевое «лимит просмотров»;
    - если сырой статус утечёт строкой — ловим «429».

    ⚠️ КОНСЕРВАТИВНО: обычный 403 «нет платного доступа к базе резюме» СЮДА НЕ ПОПАДАЕТ
    (его текст — «Ошибка получения резюме hh.ru: ... 403 Forbidden», без «квота»/«лимит
    просмотров»/«429») — иначе платный/квотный сбой доступа молча уехал бы на общий
    аккаунт. При сомнении НЕ матчим → поведение деградирует к «остановиться» (безопасно).
    # TODO: пиннить точную сигнатуру лимит-ответа hh на живом токене (тело/код 429 —
    #       429 vs 403 «no access» иногда неотличимы без разбора JSON-ошибки hh).
    """
    msg = str(exc).lower()
    return ("квота" in msg) or ("лимит просмотров" in msg) or ("429" in msg)


def _view_quota_exhausted_today(integration: "UserHhIntegration") -> bool:
    """Личная суточная квота просмотров уже помечена исчерпанной СЕГОДНЯ (UTC)?

    Метка живёт до конца суток UTC: на следующий день сравнение по дате даёт False →
    личный токен снова первичен (квота hh обнуляется посуточно)."""
    ts = getattr(integration, "daily_view_exhausted_at", None)
    if not ts:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


async def _mark_personal_view_exhausted(
    session: AsyncSession,
    integration: "UserHhIntegration",
    *,
    company_id: UUID,
    user_id: UUID,
) -> None:
    """Помечает личную интеграцию «квота просмотров исчерпана сегодня» + audit-спилл (§2.2).

    Токены/секреты НЕ логируем и НЕ кладём в audit — только факт спилла и id интеграции."""
    integration.daily_view_exhausted_at = datetime.now(timezone.utc)
    await session.commit()
    logger.warning(
        "[hh] личная квота просмотров резюме исчерпана — спилл на общий токен "
        "company=%s user=%s integration=%s",
        company_id, user_id, integration.id,
    )
    await audit(
        session,
        action="hh_personal_view_quota_spill",
        entity_type="user_hh_integration",
        entity_id=integration.id,
        actor_user_id=user_id,
        company_id=company_id,
    )
    await session.commit()


async def view_resume_with_cascade(
    session: AsyncSession,
    *,
    company_id: UUID,
    user_id: Optional[UUID],
    resume_id: str,
    **kwargs,
) -> dict:
    """Просмотр ПОЛНОГО резюме hh (get_resume_by_id) с КАСКАДОМ суточной квоты просмотров.

    Порядок:
    1) ЛИЧНЫЙ токен рекрутёра — но ТОЛЬКО если инициатор задан И его личная квота НЕ
       помечена исчерпанной сегодня (иначе бессмысленно бить в заведомо выжженный токен).
       При лимите просмотров личный помечается исчерпанным (audit-спилл) → шаг 2.
       При ЛЮБОЙ иной ошибке (403 «нет доступа», сеть, 404) — пробрасываем, НЕ маскируем.
    2) ОБЩИЙ компанийный токен (get_valid_access_token). При лимите И тут → честная
       ValidationError «Дневной лимит просмотров резюме hh исчерпан — и на личном, и на
       общем аккаунте».
    Нет ни одного токена → ValidationError «hh.ru не подключён».

    ⚠️ Каскад — ТОЛЬКО для ПРОСМОТРОВ резюме (квота 500/сут). Открытие КОНТАКТА (take_*,
    платный пул) сюда НЕ заводить: молчаливый перенос платного действия на общий аккаунт
    недопустим. **kwargs прозрачно пробрасываются в hh_client.get_resume_by_id.
    """
    # --- Шаг 1: личный токен (если инициатор есть и квота не выжжена сегодня) ---
    personal_token: Optional[str] = None
    integration: Optional[UserHhIntegration] = None
    if user_id is not None:
        integration = await get_user_integration(session, company_id, user_id)
        if integration is not None and not _view_quota_exhausted_today(integration):
            personal_token = await _get_valid_personal_token(session, company_id, user_id)

    if personal_token:
        try:
            return await hh_client.get_resume_by_id(personal_token, resume_id, **kwargs)
        except Exception as exc:
            if not _is_resume_view_limit_error(exc):
                raise  # 403/сеть/404 и пр. — не маскируем, отдаём вызывающему
            # Лимит просмотров личного токена → метка + audit-спилл, дальше общий токен.
            if integration is not None:
                await _mark_personal_view_exhausted(
                    session, integration, company_id=company_id, user_id=user_id
                )

    # --- Шаг 2: общий компанийный токен ---
    try:
        company_token: Optional[str] = await get_valid_access_token(session, company_id)
    except (NotFoundError, ValidationError):
        company_token = None

    if not company_token:
        raise ValidationError("hh.ru не подключён")

    try:
        return await hh_client.get_resume_by_id(company_token, resume_id, **kwargs)
    except Exception as exc:
        if _is_resume_view_limit_error(exc):
            raise ValidationError(
                "Дневной лимит просмотров резюме hh исчерпан — и на личном, и на общем аккаунте"
            )
        raise


async def spill_personal_view_quota(
    session: AsyncSession, *, company_id: UUID, user_id: Optional[UUID]
) -> Optional[str]:
    """Помечает личную квоту просмотров исчерпанной (если личная интеграция есть) и
    возвращает ОБЩИЙ компанийный токен для добора остатка прогона (или None, если общего нет).

    Для ГОРЯЧЕГО bulk-цикла умного подбора (_run_search_inner), где реструктурировать
    каждый просмотр под view_resume_with_cascade нельзя (не ломаем горячий путь): при
    лимит-ошибке личного токена достаточно ОДИН раз пометить личный выжженным (audit-спилл)
    и переключить локальную переменную токена на общий на остаток прогона.
    """
    if user_id is not None:
        integration = await get_user_integration(session, company_id, user_id)
        if integration is not None and not _view_quota_exhausted_today(integration):
            await _mark_personal_view_exhausted(
                session, integration, company_id=company_id, user_id=user_id
            )
    try:
        return await get_valid_access_token(session, company_id)
    except (NotFoundError, ValidationError):
        return None


async def disconnect_personal(session: AsyncSession, company_id: UUID, user_id: UUID) -> None:
    """Отключает ПЕРСОНАЛЬНЫЙ hh-токен пользователя (удаляет строку целиком).

    После удаления get_hh_token_for_user уходит на общий компанийный токен (фолбэк).

    Raises:
        NotFoundError: если персональной интеграции нет.
    """
    integration = await get_user_integration(session, company_id, user_id)
    if not integration:
        raise NotFoundError("Персональная интеграция hh.ru не найдена")

    integration_id = integration.id
    await session.delete(integration)
    await session.commit()

    await audit(
        session,
        action="hh_personal_disconnected",
        entity_type="user_hh_integration",
        entity_id=integration_id,
        actor_user_id=user_id,
        company_id=company_id,
    )
    await session.commit()


async def get_personal_status(session: AsyncSession, company_id: UUID, user_id: UUID) -> dict:
    """Статус персонального hh-подключения текущего пользователя (без секретов)."""
    integration = await get_user_integration(session, company_id, user_id)
    return {
        "connected": bool(integration and integration.access_token),
        "hh_employer_id": integration.hh_employer_id if integration else None,
        "hh_manager_id": integration.hh_manager_id if integration else None,
        "expires_at": integration.expires_at if integration else None,
        "connected_at": integration.connected_at if integration else None,
    }


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID):
    """
    Отключает интеграцию hh.ru (обнуляет токены, оставляет config)

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя

    Raises:
        NotFoundError: если интеграция не найдена
    """
    integration = await get_integration(session, company_id)

    if not integration:
        raise NotFoundError("Интеграция hh.ru не найдена")

    # Обнуляем токены и employer_id, но оставляем config (client_id, client_secret, redirect_uri)
    integration.access_token = None
    integration.refresh_token = None
    integration.expires_at = None
    integration.hh_employer_id = None

    await session.commit()

    # Записываем в аудит
    await audit(
        session,
        action="hh_disconnected",
        entity_type="hh_integration",
        entity_id=integration.id,
        actor_user_id=user_id,
        company_id=company_id
    )
    await session.commit()  # audit() после обновления — персистим audit-запись


async def get_valid_access_token(session: AsyncSession, company_id: UUID) -> str:
    """
    Получает валидный access token, обновляя при необходимости

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        str: валидный access token

    Raises:
        NotFoundError: если интеграция не найдена
        ValidationError: при ошибке обновления токенов
    """
    integration = await get_integration(session, company_id)

    if not integration:
        raise NotFoundError("Интеграция hh.ru не найдена")

    # Конфиг (client_id/secret) сохранён, но OAuth не пройден (или после disconnect) →
    # access_token/expires_at = None. Без этого guard `expires_at - timedelta` даёт
    # TypeError → необработанный 500. Отдаём чистую бизнес-ошибку (инв.6).
    if not integration.access_token or not integration.expires_at:
        raise ValidationError("hh.ru не подключён: пройдите OAuth-авторизацию")

    # Проверяем срок действия токена (с запасом 5 минут)
    now = datetime.now(timezone.utc)
    expires_soon = integration.expires_at - timedelta(minutes=5)

    if now >= expires_soon:
        # Сериализуем конкурентный рефреш: блокируем строку интеграции (FOR UPDATE),
        # чтобы параллельные потребители (cron-джобы + фоновые задачи + запросы) не
        # дёргали refresh_tokens одновременно одним и тем же ротируемым refresh-токеном.
        await session.refresh(integration, with_for_update=True)
        now = datetime.now(timezone.utc)
        # Пока ждали блокировку — сосед мог уже обновить токен. Перепроверяем.
        if integration.access_token and integration.expires_at and now < integration.expires_at - timedelta(minutes=5):
            await session.commit()  # освобождаем блокировку, отдаём свежий токен соседа
            return decrypt_text(integration.access_token)
        # Токен всё ещё истёк/истекает (блокировку держим мы) — обновляем.
        try:
            # Refresh ключом приложения Глафиры: env (.env), fallback на legacy DB-колонки
            # (тот же app, что подключал работодателя).
            client_id, client_secret, _ = _resolve_app_creds(integration)
            if not client_id or not client_secret:
                raise ValidationError("hh.ru не настроен: задайте ключ приложения в .env")

            current_refresh = decrypt_text(integration.refresh_token)

            token_data = await hh_client.refresh_tokens(
                current_refresh,
                client_id,
                client_secret
            )

            # Обновляем токены
            integration.access_token = encrypt_text(token_data["access_token"])
            integration.refresh_token = encrypt_text(token_data["refresh_token"])
            integration.expires_at = now + timedelta(seconds=token_data["expires_in"])

            await session.commit()

            return token_data["access_token"]

        except Exception as e:
            raise ValidationError(f"Не удалось обновить токены hh.ru: {e}")

    else:
        # Токен еще валидный
        return decrypt_text(integration.access_token)


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """
    Получает статус интеграции hh.ru

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        dict: статус интеграции
    """
    # Ключ приложения — env (.env), fallback на legacy DB. «Настроено» = ключ есть
    # на сервере; работодателю достаточно нажать «Подключить» (ничего не вводя).
    integration = await get_integration(session, company_id)
    client_id, _, redirect_uri = _resolve_app_creds(integration)

    client_id_masked = None
    if client_id:
        client_id_masked = ("••••" + client_id[-4:]) if len(client_id) > 4 else "••••"

    return {
        "configured": bool(client_id and redirect_uri),
        "connected": bool(integration and integration.access_token),
        "redirect_uri": redirect_uri,
        "client_id_masked": client_id_masked,
        "hh_employer_id": integration.hh_employer_id if integration else None,
        "expires_at": integration.expires_at if integration else None,
    }


async def list_hh_vacancies(session: AsyncSession, company_id: UUID) -> list[dict]:
    """
    Получает список вакансий с hh.ru

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        list: упрощённый список вакансий [{id, name, area}, ...]

    Raises:
        ValidationError: если hh не подключён или ошибка API
    """
    integration = await get_integration(session, company_id)
    if not integration:
        raise ValidationError("Интеграция hh.ru не подключена")

    if not integration.hh_employer_id:
        raise ValidationError("Отсутствует hh_employer_id в интеграции")

    access_token = await get_valid_access_token(session, company_id)

    # Получаем set уже привязанных hh_vacancy_id для компании (одним запросом, не N+1)
    linked_rows = await session.execute(
        text(
            "SELECT hh_vacancy_id FROM vacancies "
            "WHERE company_id = :company_id AND hh_vacancy_id IS NOT NULL"
        ),
        {"company_id": str(company_id)}
    )
    linked_ids: set[str] = {str(row[0]) for row in linked_rows}

    # Получаем все страницы (начинаем с первой)
    all_items = []
    page = 0

    # Кап страниц (2000 вакансий при per_page=50) — защита от аномального pages в ответе hh.
    while page < 40:
        data = await hh_client.get_employer_vacancies(
            access_token, integration.hh_employer_id, page=page, per_page=50
        )

        items = data.get("items", [])
        if not items:
            break

        all_items.extend(items)

        # Проверяем, есть ли ещё страницы
        if page >= data.get("pages", 1) - 1:
            break

        page += 1

    # Возвращаем упрощённый список с признаком привязки
    result = []
    for item in all_items:
        hh_id = str(item["id"])
        result.append({
            "id": hh_id,
            "name": item.get("name", ""),
            "area": item.get("area", {}).get("name") if item.get("area") else None,
            "linked": hh_id in linked_ids,
        })

    return result


async def import_hh_vacancies(
    session: AsyncSession,
    company_id: UUID,
    actor_user_id: UUID,
    hh_vacancy_ids: list[str] | None = None,
) -> dict:
    """Импортирует вакансии с hh.ru в Глафиру и привязывает по hh_vacancy_id.

    Соискателей НЕ импортирует — только создаёт вакансию и привязывает,
    чтобы cron-джоб poll_hh_responses начал забирать отклики.

    Args:
        session: DB session
        company_id: ID компании
        actor_user_id: ID пользователя-импортёра (станет ответственным в team)
        hh_vacancy_ids: конкретные hh-id для импорта; None = все активные у работодателя

    Returns:
        dict: {created, skipped, failed, created_names, errors}

    Raises:
        ValidationError: если hh не подключён или ошибка получения токена
    """
    token = await get_valid_access_token(session, company_id)

    # Одним запросом: set уже привязанных hh_vacancy_id компании
    linked_rows = await session.execute(
        text(
            "SELECT hh_vacancy_id FROM vacancies "
            "WHERE company_id = :company_id AND hh_vacancy_id IS NOT NULL"
        ),
        {"company_id": str(company_id)}
    )
    already_linked: set[str] = {str(row[0]) for row in linked_rows}

    # Целевые ID: переданные явно ИЛИ все с hh
    if hh_vacancy_ids is not None:
        target_ids = [vid for vid in hh_vacancy_ids if vid not in already_linked]
        skipped = len(hh_vacancy_ids) - len(target_ids)
    else:
        # Получаем все вакансии работодателя пагинацией
        integration = await get_integration(session, company_id)
        if not integration or not integration.hh_employer_id:
            raise ValidationError("hh.ru не подключён или отсутствует hh_employer_id")

        all_hh_ids: list[str] = []
        skipped = 0
        page = 0
        # Кап страниц (2000 вакансий при per_page=50) — защита от аномального pages в ответе hh.
        while page < 40:
            data = await hh_client.get_employer_vacancies(
                token, integration.hh_employer_id, page=page, per_page=50
            )
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                hid = str(item["id"])
                if hid not in already_linked:
                    all_hh_ids.append(hid)
                else:
                    skipped += 1  # реально попавшиеся в листинге и уже привязанные
            if page >= data.get("pages", 1) - 1:
                break
            page += 1

        target_ids = all_hh_ids

    created = 0
    failed = 0
    created_names: list[str] = []
    errors: list[str] = []

    for hh_id in target_ids:
        try:
            full = await hh_client.get_vacancy_by_id(token, hh_id)
            if full is None:
                errors.append(f"hh_id={hh_id}: не удалось получить данные вакансии")
                failed += 1
                continue

            vac_name = (full.get("name") or "").strip()
            if not vac_name:
                errors.append(f"hh_id={hh_id}: пустое название вакансии, пропущено")
                failed += 1
                continue

            # Зарплата
            salary = full.get("salary") or {}
            sal_from: int | None = salary.get("from") if salary else None
            sal_to: int | None = salary.get("to") if salary else None
            currency = (salary.get("currency") or "RUB") if salary else "RUB"
            if currency == "RUR":
                currency = "RUB"

            # Занятость
            employment = full.get("employment") or {}
            employment_type: str | None = (employment.get("id") or None) if employment else None

            # Город
            area = full.get("area") or {}
            city: str | None = (area.get("name") or None) if area else None

            # Описание (HTML как есть)
            description: str | None = full.get("description") or None

            vacancy_data = VacancyCreate(
                name=vac_name,
                city=city,
                description=description,
                salary_from=int(sal_from) if sal_from is not None else None,
                salary_to=int(sal_to) if sal_to is not None else None,
                currency=currency,
                employment_type=employment_type,
                team=[actor_user_id],
            )

            # Каждая вакансия изолирована через savepoint
            async with session.begin_nested():
                vacancy = await create_vacancy(session, vacancy_data, company_id, actor_user_id)
                vacancy.hh_vacancy_id = hh_id
                vacancy.external_source = "hh"
                vacancy.external_id = hh_id
                await session.flush()

                await audit(
                    session,
                    action="hh_vacancy_linked",
                    entity_type="vacancy",
                    entity_id=vacancy.id,
                    after={"hh_vacancy_id": hh_id, "source": "import"},
                    actor_user_id=actor_user_id,
                    company_id=company_id,
                )

            await session.commit()
            created += 1
            created_names.append(vac_name)
            logger.info("[hh] import_hh_vacancies: создана вакансия '%s' hh_id=%s", vac_name, hh_id)

        except Exception as exc:
            # Сбой одной вакансии не валит остальные
            await session.rollback()
            err_msg = f"hh_id={hh_id}: {exc}"
            errors.append(err_msg[:200])
            failed += 1
            logger.warning("[hh] import_hh_vacancies: ошибка hh_id=%s exc=%s", hh_id, exc)

    return {
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "created_names": created_names,
        "errors": errors,
    }


async def link_vacancy(session: AsyncSession, vacancy_id: UUID, hh_vacancy_id: str, company_id: UUID, user_id: UUID):
    """
    Привязывает вакансию Глафиры к вакансии hh.ru

    Args:
        session: DB session
        vacancy_id: ID вакансии в Глафире
        hh_vacancy_id: ID вакансии на hh.ru
        company_id: ID компании
        user_id: ID пользователя

    Raises:
        NotFoundError: если вакансия не найдена
        ValidationError: при ошибках валидации
    """
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id
        )
    )
    vacancy = result.scalar_one_or_none()

    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    vacancy.hh_vacancy_id = hh_vacancy_id

    # Запись в аудит
    await audit(
        session,
        action="hh_vacancy_linked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"hh_vacancy_id": hh_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id
    )


async def unlink_vacancy(session: AsyncSession, vacancy_id: UUID, company_id: UUID, user_id: UUID):
    """
    Отвязывает вакансию Глафиры от hh.ru

    Args:
        session: DB session
        vacancy_id: ID вакансии в Глафире
        company_id: ID компании
        user_id: ID пользователя

    Raises:
        NotFoundError: если вакансия не найдена
    """
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id
        )
    )
    vacancy = result.scalar_one_or_none()

    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    old_hh_vacancy_id = vacancy.hh_vacancy_id
    vacancy.hh_vacancy_id = None

    # Запись в аудит
    await audit(
        session,
        action="hh_vacancy_unlinked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"hh_vacancy_id": None},
        before={"hh_vacancy_id": old_hh_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id
    )


async def publish_vacancy_to_hh(session: AsyncSession, vacancy_id: UUID, company_id: UUID, user_id: UUID) -> str:
    """
    Публикует вакансию Глафиры на hh.ru

    ⚠️  НЕ проверено без реального токена hh.ru
    ⚠️  Требует маппинга города → hh area_id (TODO)

    Args:
        session: DB session
        vacancy_id: ID вакансии в Глафире
        company_id: ID компании
        user_id: ID пользователя

    Returns:
        str: hh_vacancy_id созданной вакансии

    Raises:
        NotFoundError: если вакансия не найдена
        ValidationError: при ошибках валидации или отсутствии маппинга
    """
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id
        )
    )
    vacancy = result.scalar_one_or_none()

    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    access_token = await get_valid_access_token(session, company_id)

    # Собираем payload из данных вакансии
    payload = {
        "name": vacancy.name,
        "description": vacancy.description or "",
    }

    # Зарплата
    if vacancy.salary_from or vacancy.salary_to:
        salary = {}
        if vacancy.salary_from:
            salary["from"] = vacancy.salary_from
        if vacancy.salary_to:
            salary["to"] = vacancy.salary_to
        salary["currency"] = vacancy.currency
        payload["salary"] = salary

    # Город (требует маппинга)
    if vacancy.city:
        # TODO: маппинг город → hh area_id
        raise ValidationError(f"Требуется маппинг города '{vacancy.city}' в hh area_id")

    # TODO: обязательные поля hh.ru (type, professional_roles, employment, schedule)
    # Точный состав зависит от менеджера/региона и не проверен без реального токена

    # Публикуем вакансию
    result = await hh_client.publish_vacancy(access_token, payload)

    hh_vacancy_id = str(result.get("id"))
    if not hh_vacancy_id:
        raise ValidationError("hh.ru не вернул id созданной вакансии")

    # Сохраняем связь
    vacancy.hh_vacancy_id = hh_vacancy_id

    # Запись в аудит
    await audit(
        session,
        action="hh_vacancy_published",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"hh_vacancy_id": hh_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id
    )

    return hh_vacancy_id


async def save_hh_resume_document(
    session: AsyncSession,
    company_id: UUID,
    candidate: "Candidate",
    full_resume: dict,
    access_token: str,
    actor_user_id=None,
) -> bool:
    """Скачивает PDF резюме с hh и сохраняет его в раздел «Документы» кандидата.

    Best-effort: не кидает исключений наружу. Возвращает True если документ создан.

    Дедупликация:
    - Если у кандидата уже есть Document с source='hh' → пропуск (не дублируем при повторном поллинге).
    - Если candidate.extra['hh_resume_file_saved'] == True → пропуск (флаг для быстрой проверки без JOIN).

    Лимит: 10 МБ (download_resume_file вернёт None при превышении).
    Файл назван «Резюме hh — {ФИО}.pdf», source='hh'.
    """
    try:
        # 1. Флаг быстрой проверки
        if (candidate.extra or {}).get("hh_resume_file_saved"):
            return False

        # 2. URL PDF из поля download
        pdf_url = ((full_resume.get("download") or {}).get("pdf") or {}).get("url")
        if not pdf_url:
            return False

        # 3. Дедуп по БД (Document с source='hh' для этого кандидата)
        existing_doc = (await session.execute(
            select(Document).where(
                Document.candidate_id == candidate.id,
                Document.company_id == company_id,
                Document.source == "hh",
            ).limit(1)
        )).scalar_one_or_none()
        if existing_doc is not None:
            return False

        # 4. Скачиваем PDF (best-effort)
        content = await hh_client.download_resume_file(access_token, pdf_url)
        if content is None:
            return False

        # 5. Безопасное имя файла (убираем / и переводы строк, обрезаем до 255)
        full_name = (candidate.full_name or "кандидат").replace("/", "_").replace("\n", " ").replace("\r", "")
        raw_filename = f"Резюме hh — {full_name}.pdf"
        filename = raw_filename[:255]

        # 6. Сохраняем в storage
        storage_path = await storage_service.save(
            content,
            company_id=company_id,
            candidate_id=candidate.id,
            filename=filename,
        )

        # 7. Запись Document
        now = datetime.now(timezone.utc)
        document = Document(
            company_id=company_id,
            candidate_id=candidate.id,
            filename=filename,
            file_type="pdf",
            size_bytes=len(content),
            storage_path=storage_path,
            source="hh",
            uploaded_by=actor_user_id,
            created_at=now,
        )
        session.add(document)

        # 8. Event для ленты «Все действия» (по паттерну upload_document)
        session.add(Event(
            company_id=company_id,
            type="document",
            actor_type="system",
            actor_user_id=actor_user_id,
            text=f"Загружен файл: {filename}",
            candidate_id=candidate.id,
        ))

        # 9. Флаг + resume_id на кандидате (JSONB переприсваиваем для dirty-tracking)
        resume_id_val = str(full_resume.get("id") or "")
        candidate.extra = {
            **(candidate.extra or {}),
            "hh_resume_file_saved": True,
            **({"hh_resume_id": resume_id_val} if resume_id_val else {}),
        }

        logger.info(
            "[hh] PDF резюме сохранён: candidate_id=%s filename=%s size=%d",
            candidate.id, filename, len(content),
        )
        return True

    except Exception as exc:
        logger.warning("[hh] save_hh_resume_document: ошибка candidate_id=%s exc=%s", candidate.id, exc)
        return False


async def import_response(session: AsyncSession, company_id: UUID, vacancy: "Vacancy", item: dict, access_token: str = None) -> str:
    """Импорт ИЛИ обновление одного отклика hh. Возвращает 'created' | 'updated'.

    Существующий (по hh_negotiation_id) НЕ пропускается — обновляем данные кандидата
    и пересоздаём опыт/навыки/образование. Этап существующей заявки НЕ трогаем.
    Краткое резюме из списка откликов УРЕЗАНО — догружаем ПОЛНОЕ по resume.url
    (опыт с описанием, возраст, образование, контакты — если hh их открыл).
    """
    nid = str(item["id"])

    # --- Полное резюме (догрузка по url; краткое из списка откликов неполное) ---
    resume = item.get("resume") or {}
    resume_url = resume.get("url")
    # Источник данных резюме — для журнала: полное догружено / упали на урезанное (почему).
    resume_source = "short"  # 'full' | 'short' | 'short(no_token)' | 'short(no_url)'
    fetch_error: str | None = None
    if not access_token:
        resume_source = "short(no_token)"
    elif not resume_url:
        resume_source = "short(no_url)"
    else:
        try:
            full = await hh_client.get_resume(access_token, resume_url)
            if isinstance(full, dict):
                resume = full
                resume_source = "full"
        except Exception as e:
            # НЕ глушим молча: фикс главной причины «пустых кандидатов» — при сбое
            # догрузки остаёмся на урезанном резюме, но пишем ПОЧЕМУ (в лог ниже).
            fetch_error = str(e)[:150]
            logger.warning("[hh_sync] догрузка резюме %s не удалась: %s", resume_url, e)

    # --- Маппинг резюме hh → поля кандидата ---
    first_name = (resume.get("first_name") or "").strip()
    last_name = (resume.get("last_name") or "").strip()
    middle_name = (resume.get("middle_name") or "").strip() or None
    title = (resume.get("title") or "").strip() or None
    city = (resume.get("area") or {}).get("name")
    gender = (resume.get("gender") or {}).get("id")  # 'male' | 'female'

    # Возраст → birth_date (hh даёт birth_date 'YYYY-MM-DD' или age числом)
    birth_date = None
    bd = resume.get("birth_date")
    if bd:
        try:
            birth_date = date.fromisoformat(str(bd)[:10])
        except (ValueError, TypeError):
            birth_date = None
    elif isinstance(resume.get("age"), int):
        try:
            birth_date = date(date.today().year - resume["age"], 1, 1)
        except (ValueError, TypeError):
            birth_date = None

    salary = resume.get("salary") or {}
    salary_amount = salary.get("amount")
    salary_currency = salary.get("currency") or "RUB"
    if salary_currency == "RUR":
        salary_currency = "RUB"

    phone = _hh_phone(resume.get("contact"))
    email = _hh_email(resume.get("contact"))

    experiences = resume.get("experience") or []
    last_position, last_company, last_period = title, None, None
    if experiences:
        e0 = experiences[0]
        last_position = (e0.get("position") or title)
        last_company = e0.get("company")
        last_period = _hh_period(e0.get("start"), e0.get("end"))

    rt_parts = []
    if title:
        rt_parts.append(f"Желаемая должность: {title}")
    if resume.get("skills"):
        rt_parts.append(str(resume.get("skills")))
    resume_text = "\n\n".join(rt_parts) or None
    resume_id = (str(resume.get("id"))[:120] if resume.get("id") else None)
    # Публичная ссылка на резюме на hh.ru (для перехода рекрутёром). alternate_url —
    # каноничная веб-страница резюме; fallback — собрать из id.
    resume_alt_url = resume.get("alternate_url") or (
        f"https://hh.ru/resume/{resume.get('id')}" if resume.get("id") else None
    )

    state_id = (item.get("state") or {}).get("id") or "response"
    # Любая коллекция discard_* (by_employer/by_applicant/no_interaction/
    # vacancy_closed/to_other_vacancy) — это завершённый/отклонённый отклик → «Отказ».
    stage = "rejected" if str(state_id).startswith("discard") else "response"

    # --- Существующая заявка по hh_negotiation_id? (create-or-update / re-poll) ---
    existing = (await session.execute(
        select(Application).where(
            Application.hh_negotiation_id == nid,
            Application.company_id == company_id,
        )
    )).scalar_one_or_none()

    # Флаги резолва кандидата:
    #   is_new           — создан НОВЫЙ Candidate (нет ни заявки по nid, ни дедуп-матча).
    #   reused_via_dedup — взят СУЩЕСТВУЮЩИЙ кандидат НЕ по nid (по resume_id или phone/email).
    #                      Для него бережём данные: скаляры только в пустое, источник и
    #                      секции резюме не трогаем (мог прийти из talantix/потока/вручную).
    is_new = False
    reused_via_dedup = False

    if existing:
        # Тот же отклик уже импортирован — обновляем данные кандидата (re-poll).
        candidate = await session.get(Candidate, existing.candidate_id)
        if candidate is None:
            # Заявка есть, а кандидат пропал (каскад/ручное удаление) — восстанавливаем.
            candidate = Candidate(company_id=company_id, source="hh", first_name="Неизвестно", last_name="")
            session.add(candidate)
            is_new = True
    else:
        # Нового nid ещё нет. Прежде чем плодить карточку — 3-уровневый дедуп (как у Habr):
        #   a) по resume_id (external_source='hh', external_id=resume_id);
        #   b) по телефону/email (тот же человек мог прийти из другого источника);
        #   c) иначе — новый кандидат.
        candidate = None
        if resume_id:
            candidate = (await session.execute(
                select(Candidate).where(
                    Candidate.company_id == company_id,
                    Candidate.external_source == "hh",
                    Candidate.external_id == resume_id,
                    Candidate.deleted_at.is_(None),
                )
            )).scalars().first()
        if candidate is None and (phone or email):
            duplicates = await find_duplicate_candidates(session, company_id, phone, email)
            if duplicates:
                candidate = duplicates[0]
        if candidate is not None:
            reused_via_dedup = True  # существующий кандидат НЕ по nid — бережём его данные
        else:
            candidate = Candidate(company_id=company_id, source="hh", first_name="Неизвестно", last_name="")
            session.add(candidate)
            is_new = True

    # ФИО — всегда fill-non-empty (не затираем непустым пустым) для обеих политик.
    candidate.first_name = first_name or candidate.first_name or "Неизвестно"
    candidate.last_name = last_name or candidate.last_name or ""

    if reused_via_dedup:
        # Дедуп-матч существующего кандидата (НЕ по nid): бережём его данные —
        # скаляры пишем ТОЛЬКО в пустое; источник и external_* НЕ трогаем (мог быть
        # talantix/поток/manual); секции резюме ниже тоже не трогаем.
        if middle_name and not candidate.middle_name:
            candidate.middle_name = middle_name
        if city and not candidate.city:
            candidate.city = city[:120]
        if gender and not candidate.gender:
            candidate.gender = gender[:10]
        if birth_date and not candidate.birth_date:
            candidate.birth_date = birth_date
        if phone and not candidate.phone:
            candidate.phone = normalize_phone(phone) or phone[:20]
        if email and not candidate.email:
            candidate.email = email[:255]
        if isinstance(salary_amount, int) and not candidate.salary_from:
            candidate.salary_expectation = salary_amount
            candidate.salary_from = salary_amount
            candidate.salary_to = salary_amount
            if salary_currency:
                candidate.currency = str(salary_currency)[:3]
        if last_position and not candidate.last_position:
            candidate.last_position = last_position[:255]
        if last_company and not candidate.last_company:
            candidate.last_company = last_company[:255]
        if last_period and not candidate.last_period:
            candidate.last_period = last_period[:120]
        if resume_text and not candidate.resume_text:
            candidate.resume_text = resume_text
        if resume_alt_url and not candidate.source_url:
            candidate.source_url = resume_alt_url[:500]
    else:
        # is_new ИЛИ re-poll(nid): текущее поведение точь-в-точь — скаляры перезаписываются,
        # источник помечается hh.
        if middle_name:
            candidate.middle_name = middle_name
        if city:
            candidate.city = city[:120]
        if gender:
            candidate.gender = gender[:10]
        if birth_date:
            candidate.birth_date = birth_date
        if phone:
            candidate.phone = normalize_phone(phone) or phone[:20]
        if email:
            candidate.email = email[:255]
        if isinstance(salary_amount, int):
            candidate.salary_expectation = salary_amount
            candidate.salary_from = salary_amount
            candidate.salary_to = salary_amount
        if salary_currency:
            candidate.currency = str(salary_currency)[:3]
        if last_position:
            candidate.last_position = last_position[:255]
        if last_company:
            candidate.last_company = last_company[:255]
        if last_period:
            candidate.last_period = last_period[:120]
        if resume_text:
            candidate.resume_text = resume_text
        candidate.source = "hh"
        candidate.external_source = "hh"
        if resume_id:
            candidate.external_id = resume_id
        # Ссылка на резюме hh.ru — заполняем при импорте (не затираем пустым)
        if resume_alt_url:
            candidate.source_url = resume_alt_url[:500]
    await session.flush()

    # Опыт/навыки/образование:
    #   reused_via_dedup → НЕ трогаем вовсе (бережём резюме существующего кандидата);
    #   re-poll(nid)     → delete+add (пересоздаём от свежего резюме);
    #   новый кандидат   → add (пусто было).
    if reused_via_dedup:
        pass
    else:
        if not is_new:
            await session.execute(delete(CandidateExperience).where(CandidateExperience.candidate_id == candidate.id))
            await session.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id))
            await session.execute(delete(CandidateEducation).where(CandidateEducation.candidate_id == candidate.id))
        for row in build_candidate_resume_sections(candidate.id, company_id, resume):
            session.add(row)

    # Заявка: решение заказчика «одна строка на вакансию, этап не трогать».
    now = datetime.now(timezone.utc)
    chat_id_str = str(item.get("chat_id")) if item.get("chat_id") is not None else None

    if existing is not None:
        # Re-poll того же отклика → заявка та же, этап НЕ трогаем.
        application = existing
        await session.flush()
        result = "updated"
    else:
        # Новый nid. Если это ПЕРЕИСПОЛЬЗОВАННЫЙ кандидат и у него уже есть заявка на
        # ЭТОЙ вакансии — вторую НЕ создаём (иначе тот же человек = N строк в воронке).
        same_vac_app = None
        if not is_new:
            same_vac_app = (await session.execute(
                select(Application).where(
                    Application.company_id == company_id,
                    Application.candidate_id == candidate.id,
                    Application.vacancy_id == vacancy.id,
                )
            )).scalars().first()

        if same_vac_app is not None:
            # ВАРИАНТ 1: переиспользуем существующую заявку на этой вакансии.
            # Этап / hh_negotiation_id / hh_chat_id НЕ меняем.
            application = same_vac_app
            # Запоминаем nid в кандидате, чтобы поллер НЕ передёргивал резюме каждый крон
            # (переприсваиваем dict целиком — для dirty-tracking JSONB).
            seen = list((candidate.extra or {}).get("hh_seen_nids") or [])
            if nid not in seen:
                seen.append(nid)
                candidate.extra = {**(candidate.extra or {}), "hh_seen_nids": seen}
            await session.flush()
            result = "updated"  # поллер спец-обрабатывает только 'created'
        else:
            # Новый кандидат ЛИБО существующий на ДРУГОЙ вакансии → создаём заявку.
            application = Application(
                company_id=company_id, candidate_id=candidate.id, vacancy_id=vacancy.id,
                stage=stage, hh_negotiation_id=nid, hh_chat_id=chat_id_str,
                # Импортирован из discard-коллекции = УЖЕ отклонён на hh → сразу synced,
                # чтобы cron не пытался повторно отклонять (вернёт wrong_state).
                hh_discard_synced_at=(now if stage == "rejected" else None),
                created_at=now, selected_at=now,
            )
            session.add(application)
            try:
                # Savepoint: при гонке откатывается ТОЛЬКО этот INSERT, а не вся сессия.
                # poll коммитит батч целиком — голый session.rollback() сметал бы уже
                # импортированных в этом прогоне кандидатов/секции/audit_log.
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                # Параллельный крон/клик успел INSERT раньше. После отката savepoint
                # неудавшийся объект восстановлен в session.new — убираем его, иначе
                # autoflush на ближайшем select пере-вставит его → снова IntegrityError.
                if application in session:
                    session.expunge(application)
                existing_race = (await session.execute(
                    select(Application).where(
                        Application.hh_negotiation_id == nid,
                        Application.company_id == company_id,
                    )
                )).scalar_one_or_none()
                if existing_race is None:
                    raise  # непредвиденная ошибка целостности — пробрасываем
                application = existing_race
            result = "created"

    # Единообразно пишем hh_resume_id + photo_url в extra (JSONB переприсваиваем
    # для dirty-tracking). Фото берём из УЖЕ полученного резюме — доп. сетевых
    # вызовов НЕТ; прокси-URL заполнит аватар в воронке/пуле/карточке.
    _photo_url = build_photo_proxy_url(resume.get("photo"))
    if reused_via_dedup:
        # Бережём extra существующего кандидата: hh_resume_id/photo_url добавляем
        # ТОЛЬКО если их ещё нет (не перетираем данные talantix/потока). При этом
        # hh_seen_nids (мог быть записан выше) сохраняется как база словаря.
        _cur_extra = candidate.extra or {}
        _patch = {}
        if resume_id and not _cur_extra.get("hh_resume_id"):
            _patch["hh_resume_id"] = resume_id
        if _photo_url and not _cur_extra.get("photo_url"):
            _patch["photo_url"] = _photo_url
        if _patch:
            candidate.extra = {**_cur_extra, **_patch}
    elif resume_id or _photo_url:
        candidate.extra = {
            **(candidate.extra or {}),
            **({"hh_resume_id": resume_id} if resume_id else {}),
            **({"photo_url": _photo_url} if _photo_url else {}),
        }

    # Best-effort скачивание PDF резюме hh в раздел «Документы» кандидата.
    # Не блокирует импорт — save_hh_resume_document ловит все исключения внутри.
    if access_token:
        await save_hh_resume_document(
            session=session,
            company_id=company_id,
            candidate=candidate,
            full_resume=resume,
            access_token=access_token,
        )

    await audit(
        session,
        action=("hh_response_imported" if result == "created" else "hh_response_updated"),
        entity_type="application",
        entity_id=application.id,
        after={"candidate_name": f"{first_name} {last_name}".strip(), "hh_negotiation_id": nid, "stage": stage},
        actor_type="system",
        actor_user_id=None,
        company_id=company_id,
    )

    # Журнал: ОТКУДА взяли + что с резюме. Пустой = ни опыта, ни навыков, ни должности
    # (такой уйдёт в скоринг как 0/bad — по логу видно, что виноват урезанный/недогруженный
    # резюме, а не сам кандидат). Причина обычно — fetch_error догрузки (см. resume_source).
    is_empty = not experiences and not resume.get("skills") and not title
    _hh_log(
        f"{result} nid={nid} resume_id={resume_id} "
        f'вакансия="{getattr(vacancy, "name", "") or ""}" этап={stage} '
        f'имя="{(first_name + " " + last_name).strip() or "—"}" резюме={resume_source}'
        f"{(' fetch_error=' + fetch_error) if fetch_error else ''}"
        f"{' ⚠ПУСТОЙ' if is_empty else ''}"
    )
    return result


async def poll_responses_now(session: AsyncSession, company_id: UUID) -> dict:
    """Ручной забор откликов с hh.ru для привязанных АКТИВНЫХ вакансий компании.

    Тот же импорт, что cron-джоб poll_hh_responses, но по запросу из UI (мгновенно).
    Требует подключённого hh + ПЛАТНОГО доступа работодателя (negotiations).
    """
    integration = await get_integration(session, company_id)
    if not integration or not integration.hh_employer_id:
        raise ValidationError("hh.ru не подключён")

    access_token = await get_valid_access_token(session, company_id)

    # По кнопке опрашиваем ВСЕ привязанные вакансии (любой ATS-статус): hh-публикация
    # может быть активна, даже если вакансия в ATS закрыта/в архиве — отклики всё
    # равно нужно забрать. (Авто-cron — только active, чтобы не дёргать лишнее.)
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.company_id == company_id,
            Vacancy.hh_vacancy_id.isnot(None),
        )
    )
    vacancies = result.scalars().all()

    # Инкрементально: полное резюме (дорогой GET по url) тянем ТОЛЬКО для НОВЫХ
    # откликов. Заранее берём set уже импортированных hh_negotiation_id компании —
    # известные пропускаем без фетча резюме. Это и есть «грузить только новых»
    # (раньше резюме передёргивалось по каждому отклику каждый прогон).
    existing_rows = await session.execute(
        select(Application.hh_negotiation_id).where(
            Application.company_id == company_id,
            Application.hh_negotiation_id.isnot(None),
        )
    )
    existing_nids = {str(r[0]) for r in existing_rows if r[0] is not None}

    # Плюс nid, «свёрнутые» в существующую заявку той же вакансии (дедуп, ВАРИАНТ 1):
    # они НЕ висят на Application.hh_negotiation_id (заявка одна, nid другой), а лежат в
    # candidate.extra['hh_seen_nids']. Без этого поллер каждый крон снова тянул бы их
    # резюме (дорогой GET) и звал import_response. Строго company-scoped.
    seen_rows = await session.execute(
        select(Candidate.extra).where(
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
            Candidate.extra.has_key("hh_seen_nids"),  # JSONB ? оператор
        )
    )
    for (ex,) in seen_rows:
        for x in (ex.get("hh_seen_nids") or []):
            existing_nids.add(str(x))

    # Диагностику возвращаем В ОТВЕТЕ (а не в логи — кастомный logger.info может не
    # выводиться в docker logs, если root-логгер не на INFO). По каждой вакансии:
    # сколько откликов вернул hh (found), сколько импортировано, и ошибка hh если была.
    # Забираем коллекции «Отклик» (неразобранные → этап «Отклик») и «Отказ»
    # (отклонённые на hh → этап «Отказ»). Этап для каждого item определяет
    # import_response по item.state.id.
    # Забираем «Отклик» (неразобранные) + «Приглашённые» (phone_interview — кого
    # пригласил работодатель, в т.ч. через Умный подбор; на нашей стороне = этап «Отклик»,
    # дедуп по hh_negotiation_id → без дублей) + все коллекции отказа hh.
    # consider/interview/offer/hired НЕ трогаем (продвинутые на hh — их этап определяет
    # рекрутёр, не импорт).
    wanted = (
        "response",
        "phone_interview",
        "discard_by_employer", "discard_by_applicant", "discard_no_interaction",
        "discard_vacancy_closed", "discard_to_other_vacancy",
    )

    stats = {"imported": 0, "updated": 0, "skipped": 0, "vacancies": len(vacancies), "details": []}
    for vacancy in vacancies:
        vstat = {
            "name": vacancy.name,
            "status": vacancy.status,
            "hh_id": vacancy.hh_vacancy_id,
            "found": 0,
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "by_collection": {},
            "all_collections": {},
            "error": None,
        }
        try:
            collections = await hh_client.get_negotiation_collections(access_token, vacancy.hh_vacancy_id)
            # Диагностика: ВСЕ коллекции hh (id→count) — чтобы увидеть, как называется
            # коллекция «Отказ» (она может быть не 'discard').
            vstat["all_collections"] = {str(c.get("id")): c.get("count") for c in collections}
            for coll in collections:
                cid = coll.get("id")
                if cid not in wanted:
                    continue
                url = coll.get("url")
                if not url:
                    vstat["by_collection"][cid] = coll.get("count") or 0
                    continue
                coll_found = None
                page = 0
                while True:
                    data = await hh_client.get_collection_page(access_token, url, page=page, per_page=50)
                    if coll_found is None:
                        # реальное число откликов коллекции (а не coll.count, которого может не быть)
                        coll_found = data.get("found")
                        if coll_found is None:
                            coll_found = coll.get("count")
                        vstat["by_collection"][cid] = coll_found or 0
                        vstat["found"] += coll_found or 0
                    items = data.get("items", []) or []
                    if not items:
                        break
                    # Собираем map hh_negotiation_id → chat_id для бэкфилла существующих
                    nid_to_chat_id = {}
                    for item in items:
                        nid = str(item.get("id"))
                        chat_id = item.get("chat_id")
                        if nid and chat_id is not None:
                            nid_to_chat_id[nid] = str(chat_id)

                    # Бэкфилл chat_id для существующих Applications с пустым hh_chat_id
                    if nid_to_chat_id:
                        existing_apps_result = await session.execute(
                            select(Application).where(
                                Application.company_id == company_id,
                                Application.hh_negotiation_id.in_(list(nid_to_chat_id.keys())),
                                Application.hh_chat_id.is_(None)
                            )
                        )
                        existing_apps = existing_apps_result.scalars().all()
                        for app in existing_apps:
                            if app.hh_negotiation_id in nid_to_chat_id:
                                app.hh_chat_id = nid_to_chat_id[app.hh_negotiation_id]

                    for item in items:
                        nid = str(item.get("id"))
                        # Уже импортирован → пропускаем БЕЗ фетча резюме (только новые грузим).
                        if nid in existing_nids:
                            stats["skipped"] += 1
                            vstat["skipped"] += 1
                            continue
                        try:
                            res = await import_response(session, company_id, vacancy, item, access_token=access_token)
                            if res == "created":
                                stats["imported"] += 1
                                vstat["imported"] += 1
                                existing_nids.add(nid)
                            elif res == "updated":
                                stats["updated"] += 1
                                vstat["updated"] += 1
                            else:
                                stats["skipped"] += 1
                        except Exception as imp_err:
                            # Реальный сбой импорта отклика — логируем, чтобы отличать от
                            # штатного пропуска (иначе ночной cron мог тихо ничего не импортить)
                            logger.warning("[hh] сбой импорта отклика nid=%s: %s", nid, imp_err)
                            stats["skipped"] += 1
                    if page >= (data.get("pages", 1) or 1) - 1:
                        break
                    page += 1
        except Exception as e:
            vstat["error"] = getattr(e, "message", None) or str(e)
        stats["details"].append(vstat)

    return stats


def build_polite_rejection_text(vacancy_name: str = "", company_name: str = "") -> str:
    """Встроенный вежливый текст отказа (fallback), названный по вакансии и компании.

    ⚠️ Это ТОЛЬКО fallback. Кастомный `vacancy.rejection_text` и
    `glafira_settings.default_rejection_text` — текст РЕКРУТЁРА, его не трогаем и
    ничем не дополняем (см. `resolve_rejection_text`).

    Без vacancy_name/company_name (напр. вакансия не найдена) деградирует к прежней
    обезличенной формулировке — пустых «кавычек-дырок» кандидату не уходит.
    """
    if vacancy_name and company_name:
        opening = (
            f"Благодарим за интерес к вакансии «{vacancy_name}» компании «{company_name}» "
            f"и время, уделённое отклику."
        )
    elif vacancy_name:
        opening = f"Благодарим за интерес к вакансии «{vacancy_name}» и время, уделённое отклику."
    elif company_name:
        opening = (
            f"Благодарим за интерес к вакансии компании «{company_name}» "
            f"и время, уделённое отклику."
        )
    else:
        opening = "Благодарим за интерес к нашей вакансии и время, уделённое отклику."
    return (
        f"Здравствуйте! {opening} "
        "К сожалению, по итогам рассмотрения мы приняли решение не продолжать общение по этой позиции. "
        "Это не оценка вас как специалиста — на данном этапе мы остановились на другой кандидатуре. "
        "Желаем успехов в поиске работы и будем рады видеть ваш отклик на наши будущие вакансии!"
    )


# Обезличенный вариант встроенного текста (без вакансии/компании) — деградация,
# когда вакансию определить не удалось.
POLITE_REJECTION_TEXT = build_polite_rejection_text()


async def resolve_rejection_text(session: AsyncSession, company_id: UUID, vacancy_id: UUID) -> str:
    """
    Возвращает настраиваемый текст отказа с приоритетом:
    1. vacancy.rejection_text (непустой) — текст рекрутёра, отдаём КАК ЕСТЬ
    2. glafira_settings.default_rejection_text (непустой) — тоже текст рекрутёра, КАК ЕСТЬ
    3. встроенный fallback — с названием вакансии и компании (заказчик → арендатор)
    """
    # Вакансия целиком: нужны rejection_text (приоритет 1), name и client_id (fallback).
    vacancy = (await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id
        )
    )).scalar_one_or_none()

    vacancy_rejection_text = vacancy.rejection_text if vacancy else None
    if vacancy_rejection_text and vacancy_rejection_text.strip():
        return vacancy_rejection_text.strip()

    # Получаем текст из настроек компании
    settings_result = await session.execute(
        select(GlafiraSettings.default_rejection_text).where(
            GlafiraSettings.company_id == company_id
        )
    )
    default_rejection_text = settings_result.scalar_one_or_none()

    if default_rejection_text and default_rejection_text.strip():
        return default_rejection_text.strip()

    # Fallback на встроенный текст — с вакансией и компанией.
    company_name = await resolve_company_display_name(session, company_id, vacancy)
    return build_polite_rejection_text(vacancy.name if vacancy else "", company_name)


async def sync_company_rejections(session: AsyncSession, company_id: UUID, limit: int = 20) -> dict:
    """
    Синхронизирует отказы hh-кандидатов: отклоняет на hh.ru + отправляет вежливое сообщение

    Обрабатывает Applications со stage='rejected', у которых есть hh_negotiation_id
    и ещё не установлен флаг hh_discard_synced_at (не синхронизированы с hh).

    Args:
        session: DB session
        company_id: ID компании
        limit: максимальное количество отказов за проход (по умолчанию 20)

    Returns:
        dict: статистика {discarded, failed, skipped_no_token}

    Raises:
        NotFoundError: если интеграция hh.ru не найдена
    """
    stats = {"discarded": 0, "already_discarded": 0, "failed": 0, "skipped_no_token": 0}

    try:
        # Проверяем доступность токена
        access_token = await get_valid_access_token(session, company_id)
    except (NotFoundError, ValidationError):
        logger.warning(f"Компания {company_id}: нет валидного токена hh.ru для синхронизации отказов")
        stats["skipped_no_token"] = -1  # Индикатор отсутствия токена
        return stats

    # Выбираем hh-кандидатов, которых отклонили, но ещё не синхронизировали с hh
    stmt = (
        select(Application, Candidate)
        .join(Candidate)
        .where(
            Application.company_id == company_id,
            Application.stage == "rejected",
            Application.hh_negotiation_id.isnot(None),
            Application.hh_discard_synced_at.is_(None),
            Candidate.deleted_at.is_(None)
        )
        .limit(limit)
    )

    result = await session.execute(stmt)
    applications_with_candidates = result.fetchall()

    logger.info(f"Компания {company_id}: найдено {len(applications_with_candidates)} отклонённых hh-кандидатов для синхронизации")

    for app, candidate in applications_with_candidates:
        try:
            # 1. Резолв chat_id (лениво, если не установлен)
            chat_id = app.hh_chat_id
            if not chat_id:
                try:
                    nego_data = await hh_client.get_negotiation(access_token, app.hh_negotiation_id)
                    chat_id = nego_data.get("chat_id")
                    if chat_id:
                        app.hh_chat_id = chat_id
                        await session.flush()  # Сохраним chat_id сразу
                except Exception as e:
                    logger.warning(f"Не удалось получить chat_id для отклика {app.hh_negotiation_id}: {e}")

            logger.info(
                f"[reject] {candidate.full_name} • nego={app.hh_negotiation_id} "
                f"vac_id={app.vacancy_id} chat_id={chat_id or '—'}: обрабатываю отказ на hh"
            )

            # 2. Отклоняем на hh.ru
            try:
                discarded_now = await hh_client.discard_negotiation(access_token, app.hh_negotiation_id)
            except Exception as e:
                # Транзиентная ошибка (нет прав/сеть) — НЕ помечаем synced, ретрай.
                log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard НЕ выполнен: {e}")
                stats["failed"] += 1
                logger.error(f"Ошибка отказа hh отклика {app.hh_negotiation_id}: {e}")
                continue

            # discard вернул 403 wrong_state — это НЕ всегда «уже готово». Узнаём
            # реальное состояние отклика на hh, чтобы не пометить активного как
            # синхронизированного (баг прошлой версии).
            if not discarded_now:
                emp_state = "?"
                actions_dbg = ""
                try:
                    nego = await hh_client.get_negotiation(access_token, app.hh_negotiation_id)
                    emp_state = str((nego.get("employer_state") or {}).get("id") or nego.get("state") or "?")
                    actions_dbg = ", ".join(
                        f"{a.get('id')}={'on' if a.get('enabled') else 'off'}"
                        for a in (nego.get("actions") or []) if isinstance(a, dict)
                    )
                except Exception as e:
                    logger.warning(f"Не удалось получить состояние отклика {app.hh_negotiation_id}: {e}")

                if emp_state.startswith("discard"):
                    # Реально уже в отказе на hh → синк не нужен, сообщение не шлём.
                    app.hh_discard_synced_at = datetime.now(timezone.utc)
                    await session.commit()
                    log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • уже в отказе на hh (state={emp_state})")
                    logger.info(f"[reject] {candidate.full_name} • nego={app.hh_negotiation_id}: уже в отказе на hh (state={emp_state}) → synced, письмо не шлём")
                    stats["already_discarded"] += 1
                elif "discard_by_employer" not in actions_dbg:
                    # hh НЕ предлагает discard_by_employer (пустой actions[] — вакансия
                    # закрыта / резюме соискателя скрыто). Статус отклика на hh сменить
                    # НЕЛЬЗЯ ничем. Помечаем synced (ретрай бессмыслен, лог не спамим).
                    app.hh_discard_synced_at = datetime.now(timezone.utc)
                    await session.commit()
                    log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard недоступен (нет действия discard_by_employer, state={emp_state}) — помечаем synced")
                    logger.info(f"discard недоступен для отклика {app.hh_negotiation_id} (state={emp_state}; actions: [{actions_dbg}]) — synced без отказа")
                    stats["already_discarded"] += 1
                else:
                    # discard_by_employer доступен, но вызов вернул False — транзиент/
                    # рассинхрон. НЕ помечаем synced (ретрай на следующем прогоне).
                    await session.commit()  # сохраняем разрешённый chat_id; флаг synced НЕ ставим
                    log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard не прошёл, отклик активен (state={emp_state}); действия hh: [{actions_dbg}]")
                    logger.error(f"discard не прошёл на активном отклике {app.hh_negotiation_id} (state={emp_state}); actions: [{actions_dbg}]")
                    stats["failed"] += 1
                continue

            # discard прошёл (204) → помечаем synced.
            logger.info(f"[reject] {candidate.full_name} • nego={app.hh_negotiation_id}: discard на hh OK (204) → статус «Не подходит»")
            app.hh_discard_synced_at = datetime.now(timezone.utc)
            await session.flush()

            # 3. Отправляем вежливое сообщение (best-effort) — только тем, кого
            #    реально отклонили сейчас И только если на вакансии включён
            #    авто-текст отказа (флаг auto_reject_message; «вежливость» на hh).
            #    Сам discard на hh идёт независимо от флага.
            message_sent = False
            auto_reject_message = (await session.execute(
                select(Vacancy.auto_reject_message).where(
                    Vacancy.id == app.vacancy_id,
                    Vacancy.company_id == company_id,
                )
            )).scalar_one_or_none()
            if not chat_id:
                logger.info(f"[reject] {candidate.full_name} • nego={app.hh_negotiation_id}: письмо НЕ шлём — нет hh-чата (chat_id пуст)")
            elif not auto_reject_message:
                logger.info(f"[reject] {candidate.full_name} • nego={app.hh_negotiation_id}: письмо НЕ шлём — на вакансии выключен auto_reject_message")
            else:
                try:
                    # Получаем настраиваемый текст отказа
                    rejection_text = await resolve_rejection_text(session, company_id, app.vacancy_id)

                    msg_response = await hh_client.send_chat_message(
                        access_token,
                        chat_id,
                        rejection_text
                    )

                    # Сохраняем исходящее сообщение
                    message = Message(
                        company_id=company_id,
                        candidate_id=candidate.id,
                        application_id=app.id,
                        channel="hh",
                        direction="out",
                        sender_type="ai",
                        sender_user_id=None,
                        body=rejection_text,
                        sent_at=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                        external_id=str(msg_response.get("id", ""))
                    )
                    session.add(message)
                    message_sent = True
                    logger.info(f"[reject] {candidate.full_name} • nego={app.hh_negotiation_id}: письмо отправлено в hh-чат {chat_id} (msg={msg_response.get('id')})")

                except Exception as e:
                    # Ошибка отправки сообщения не откатывает discard
                    logger.warning(f"[reject] {candidate.full_name} • nego={app.hh_negotiation_id}: НЕ удалось отправить письмо в чат {chat_id}: {e}")

            # 4. Коммитим каждую application отдельно
            await session.commit()

            # Логируем результат
            if message_sent:
                log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard + вежливое сообщение отправлено")
            else:
                log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard выполнен, сообщение не отправлено")

            stats["discarded"] += 1

        except Exception as e:
            # Откат транзакции для этой application
            await session.rollback()
            stats["failed"] += 1
            logger.error(f"Критическая ошибка синхронизации отказа application {app.id}: {e}")
            continue

    logger.info(
        f"Компания {company_id}: синхронизация отказов завершена. "
        f"Успешно: {stats['discarded']}, Неудачно: {stats['failed']}"
    )

    return stats