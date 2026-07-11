"""Эндпоинты для работы с интеграциями"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ...deps import get_current_user
from ...core.errors import ValidationError, ForbiddenError, AppError

logger = logging.getLogger(__name__)
from ...core.permissions import require_admin, require_settings_read_access
from ...database import get_db
from ...models import User
from ...services.integrations.hh import service as hh_service
from ...services.integrations.smtp import service as smtp_service
from ...services.integrations.bitrix24 import service as b24_service
from ...services.integrations.telegram import service as tg_service
from ...services.integrations.mango import service as mango_service
from ...services.integrations.habr import service as habr_service
from ...services.integrations.habr import sync as habr_sync
from ...services.integrations.habr import client as habr_client_module
from ...services.integrations.avito import service as avito_service
from ...services.integrations.avito import sync as avito_sync
from ...schemas.bitrix24 import BitrixDepartment, BitrixImportCandidate, BitrixImportRequest, BitrixImportResult
from ...config import settings


class SmtpConfigRequest(BaseModel):
    host: str
    port: int
    encryption: str = "tls"
    username: str = ""
    password: str = ""  # пусто = сохранить существующий (пароль write-only)
    from_email: str
    from_name: str = ""
    reply_to: str = ""


class SmtpTestRequest(BaseModel):
    to: str


class B24ConfigRequest(BaseModel):
    webhook_url: str


class TgSendCodeRequest(BaseModel):
    phone: str


class TgConfirmCodeRequest(BaseModel):
    code: str


class TgConfirmPasswordRequest(BaseModel):
    password: str


class TgConnectSessionRequest(BaseModel):
    session: str


class MangoConfigRequest(BaseModel):
    api_key: str | None = None
    api_salt: str | None = None
    vpbx_api_url: str | None = None


class HabrLinkVacancyRequest(BaseModel):
    vacancy_id: str
    habr_vacancy_id: str


class AvitoConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    avito_user_id: str | None = None


class AvitoLinkVacancyRequest(BaseModel):
    vacancy_id: str
    avito_vacancy_id: str


class HhVacanciesImportRequest(BaseModel):
    hh_vacancy_ids: list[str] | None = None


router = APIRouter()


@router.get("/hh/status", dependencies=[Depends(require_settings_read_access)])
async def get_hh_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Получить статус интеграции hh.ru"""
    status = await hh_service.get_status(session, current_user.company_id)
    return status


@router.get("/hh/authorize", dependencies=[Depends(require_admin)])
async def start_hh_authorization(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Начать процесс авторизации hh.ru (возвращает URL для редиректа)"""
    authorize_url = await hh_service.start_oauth(
        session, current_user.company_id, current_user.id
    )

    return {"authorize_url": authorize_url}


@router.get("/hh/callback")
async def hh_oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    session: AsyncSession = Depends(get_db)
):
    """Callback endpoint для OAuth hh.ru (без авторизации, защищен через state)"""
    frontend_base = settings.FRONTEND_BASE_URL

    if error:
        if error == "access_denied":
            return RedirectResponse(url=f"{frontend_base}/settings?tab=integrations&hh=denied")
        else:
            return RedirectResponse(url=f"{frontend_base}/settings?tab=integrations&hh=error")

    if not code or not state:
        return RedirectResponse(url=f"{frontend_base}/settings?tab=integrations&hh=error")

    try:
        await hh_service.complete_oauth(session, code, state)
        return RedirectResponse(url=f"{frontend_base}/settings?tab=integrations&hh=connected")

    except AppError as e:
        # Бизнес-ошибка (невалидный state, не настроен ключ, hh отклонил обмен кода) —
        # ЛОГИРУЕМ и протаскиваем понятный текст на фронт через hh_msg (это браузерный
        # редирект, не 500). Сообщения AppError безопасны для показа.
        logger.warning("hh OAuth callback failed: %s", e.message)
        return RedirectResponse(
            url=f"{frontend_base}/settings?tab=integrations&hh=error&hh_msg={quote(e.message)}"
        )
    except Exception:
        logger.exception("hh OAuth callback: неожиданная ошибка")
        return RedirectResponse(url=f"{frontend_base}/settings?tab=integrations&hh=error")


@router.post("/hh/disconnect", dependencies=[Depends(require_admin)])
async def disconnect_hh(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить интеграцию hh.ru"""
    await hh_service.disconnect(session, current_user.company_id, current_user.id)

    return {"message": "Интеграция hh.ru отключена"}


@router.get("/hh/vacancies", dependencies=[Depends(require_settings_read_access)])
async def list_hh_vacancies(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Получить список вакансий с hh.ru"""
    vacancies = await hh_service.list_hh_vacancies(session, current_user.company_id)
    return vacancies


@router.post("/hh/vacancies/import", dependencies=[Depends(require_admin)])
async def import_hh_vacancies(
    body: HhVacanciesImportRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Импортировать вакансии с hh.ru в Глафиру (создать + привязать hh_vacancy_id).

    Если hh_vacancy_ids не передан — импортируются все активные вакансии работодателя,
    ещё не привязанные в системе.

    Чтение вакансий (GET /vacancies) — БЕСПЛАТНО, суточную квоту не тратит.
    """
    result = await hh_service.import_hh_vacancies(
        session,
        current_user.company_id,
        current_user.id,
        body.hh_vacancy_ids,
    )
    return result


@router.post("/hh/poll-responses", dependencies=[Depends(require_admin)])
async def hh_poll_responses(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Ручной забор откликов с hh.ru (привязанные активные вакансии → этап «Отклик»)."""
    result = await hh_service.poll_responses_now(session, current_user.company_id)
    await session.commit()
    return result


# ---------------------------------------------------------------------------
# SMTP (почтовый сервер компании)
# ---------------------------------------------------------------------------

@router.post("/smtp/config", dependencies=[Depends(require_admin)])
async def save_smtp_config(
    data: SmtpConfigRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Сохранить настройки SMTP. Возвращает обновлённый статус (без пароля)."""
    await smtp_service.save_config(
        session,
        current_user.company_id,
        current_user.id,
        host=data.host,
        port=data.port,
        encryption=data.encryption,
        username=data.username,
        password=data.password,
        from_email=data.from_email,
        from_name=data.from_name,
        reply_to=data.reply_to,
    )
    await session.commit()
    return await smtp_service.get_status(session, current_user.company_id)


@router.get("/smtp/status", dependencies=[Depends(require_settings_read_access)])
async def get_smtp_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Статус SMTP-интеграции (пароль не возвращается)."""
    return await smtp_service.get_status(session, current_user.company_id)


@router.post("/smtp/test", dependencies=[Depends(require_admin)])
async def test_smtp(
    data: SmtpTestRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отправить тестовое письмо через настроенный SMTP."""
    # send_test_email коммитит сам (на обоих путях — успех и сбой),
    # чтобы last_test_* сохранилось даже при ошибке отправки.
    result = await smtp_service.send_test_email(
        session, current_user.company_id, current_user.id, to=data.to
    )
    return result


@router.post("/smtp/disconnect", dependencies=[Depends(require_admin)])
async def disconnect_smtp(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить SMTP (status=disconnected; конфиг остаётся)."""
    await smtp_service.disconnect(session, current_user.company_id, current_user.id)
    await session.commit()
    return {"message": "SMTP отключён"}


# ---------------------------------------------------------------------------
# Битрикс24 (входящий вебхук)
# ---------------------------------------------------------------------------

@router.post("/bitrix24/config", dependencies=[Depends(require_admin)])
async def save_b24_config(
    data: B24ConfigRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Сохранить URL входящего вебхука Битрикс24. Возвращает статус (без секрета)."""
    await b24_service.save_config(
        session, current_user.company_id, current_user.id, webhook_url=data.webhook_url
    )
    await session.commit()
    return await b24_service.get_status(session, current_user.company_id)


@router.get("/bitrix24/status", dependencies=[Depends(require_settings_read_access)])
async def get_b24_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Статус интеграции Битрикс24 (URL вебхука/секрет не возвращаются)."""
    return await b24_service.get_status(session, current_user.company_id)


@router.post("/bitrix24/test", dependencies=[Depends(require_admin)])
async def test_b24(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Проверить подключение к Битрикс24 (реальный вызов user.get)."""
    # test_connection коммитит сам (успех и сбой) — чтобы last_test_* сохранилось.
    return await b24_service.test_connection(
        session, current_user.company_id, current_user.id
    )


@router.get("/bitrix24/users", dependencies=[Depends(require_settings_read_access)])
async def preview_b24_users(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Превью сотрудников с портала (первая страница). Импорт в Глафиру — отдельный этап."""
    return await b24_service.preview_users(session, current_user.company_id)


@router.get("/bitrix24/departments")
async def get_b24_departments(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Список отделов Битрикс24 (admin only)."""
    if current_user.role != "admin":
        raise ForbiddenError("Только администратор может получать список отделов")

    departments = await b24_service.list_departments(session, current_user.company_id)
    return [BitrixDepartment.model_validate(dept) for dept in departments]


@router.get("/bitrix24/import-candidates")
async def get_b24_import_candidates(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Список пользователей Битрикс24 для импорта (с отделами, admin only)."""
    if current_user.role != "admin":
        raise ForbiddenError("Только администратор может получать список пользователей для импорта")

    candidates = await b24_service.get_import_candidates(session, current_user.company_id)
    return [BitrixImportCandidate.model_validate(candidate) for candidate in candidates]


@router.post("/bitrix24/import", response_model=BitrixImportResult)
async def import_b24_users(
    data: BitrixImportRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Импорт пользователей из Битрикс24 (admin only)."""
    if current_user.role != "admin":
        raise ForbiddenError("Только администратор может импортировать пользователей")

    result = await b24_service.import_users(
        session,
        current_user.company_id,
        current_user.id,
        b24_user_ids=data.b24_user_ids,
        role=data.role,
        delivery=data.delivery
    )
    await session.commit()

    return BitrixImportResult.model_validate(result)


@router.post("/bitrix24/import-employees", dependencies=[Depends(require_admin)])
async def import_b24_employees(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Импорт сотрудников из Битрикс24 в таблицу employees (для расчёта Текучки, admin only).

    Идемпотентно (upsert). Возвращает {created, updated, marked_left, total}.
    """
    result = await b24_service.import_employees_from_b24(
        session, current_user.company_id, current_user.id
    )
    await session.commit()
    return result


@router.post("/bitrix24/disconnect", dependencies=[Depends(require_admin)])
async def disconnect_b24(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить Битрикс24 (status=disconnected; конфиг остаётся)."""
    await b24_service.disconnect(session, current_user.company_id, current_user.id)
    await session.commit()
    return {"message": "Битрикс24 отключён"}


# ---------------------------------------------------------------------------
# Битрикс24 — настройки расписания интервью
# ---------------------------------------------------------------------------

class InterviewSlotSettingsRequest(BaseModel):
    work_days: list[int] | None = None   # 1=пн..7=вс
    work_start: str | None = None        # "HH:MM"
    work_end: str | None = None          # "HH:MM"
    duration_min: int | None = None
    step_min: int | None = None
    horizon_days: int | None = None
    lead_hours: int | None = None
    tz: str | None = None
    interview_video_link: str | None = None


_SLOT_DEFAULTS = {
    "work_days": [1, 2, 3, 4, 5],
    "work_start": "10:00",
    "work_end": "18:00",
    "duration_min": 60,
    "step_min": 30,
    "horizon_days": 14,
    "lead_hours": 24,
    "tz": "Europe/Moscow",
    "interview_video_link": "",
}


def _read_slot_settings(cfg: dict) -> dict:
    return {k: cfg.get(k, v) for k, v in _SLOT_DEFAULTS.items()}


@router.get("/bitrix24/schedule-settings", dependencies=[Depends(require_settings_read_access)])
async def get_b24_schedule_settings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Настройки записи на интервью через Б24-календарь."""
    from sqlalchemy import select as sa_select
    from ...models import Integration
    row = (await session.execute(
        sa_select(Integration).where(
            Integration.provider == "bitrix24",
            Integration.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    cfg = (row.config or {}) if row else {}
    return _read_slot_settings(cfg)


@router.patch("/bitrix24/schedule-settings", dependencies=[Depends(require_admin)])
async def patch_b24_schedule_settings(
    data: InterviewSlotSettingsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновляет настройки расписания интервью в integrations.config."""
    from sqlalchemy import select as sa_select
    from ...models import Integration
    from ...services.integrations.bitrix24 import client as b24_client_mod
    from ...services.settings.crypto import decrypt_text

    row = (await session.execute(
        sa_select(Integration).where(
            Integration.provider == "bitrix24",
            Integration.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()

    if not row or not (row.config or {}).get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    # Проверяем scope вебхука (user + calendar)
    webhook_url = decrypt_text(row.config["webhook_url"])
    try:
        await b24_client_mod.get_current_user_b24(webhook_url)
    except AppError as e:
        raise ValidationError(
            f"Вебхуку не хватает прав (user/calendar). Перевыпустите с нужными scope. Детали: {e.message}"
        )

    cfg = dict(row.config)
    update_data = data.model_dump(exclude_none=True)
    for key, val in update_data.items():
        if key in _SLOT_DEFAULTS:
            cfg[key] = val
    row.config = cfg
    await session.flush()
    await session.commit()

    return _read_slot_settings(cfg)


# ---------------------------------------------------------------------------
# Битрикс24 — маппинг b24_user_id для пользователей Глафиры
# ---------------------------------------------------------------------------

class B24UserMapRequest(BaseModel):
    b24_user_id: int | None


@router.patch("/bitrix24/users/{user_id}/b24", dependencies=[Depends(require_admin)])
async def set_b24_user_id(
    user_id: str,
    data: B24UserMapRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Вручную задаёт/сбрасывает b24_user_id для пользователя Глафиры (admin)."""
    from sqlalchemy import select as sa_select
    import uuid as _uuid
    from ...models import User as UserModel

    try:
        uid = _uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise ValidationError("Неверный формат user_id")

    target = (await session.execute(
        sa_select(UserModel).where(
            UserModel.id == uid,
            UserModel.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()

    if not target:
        raise ValidationError("Пользователь не найден")

    target.b24_user_id = data.b24_user_id
    await session.flush()
    await session.commit()
    return {"id": str(target.id), "b24_user_id": target.b24_user_id, "full_name": target.full_name}


@router.post("/bitrix24/users/{user_id}/b24/sync", dependencies=[Depends(require_admin)])
async def sync_b24_user_id(
    user_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Авто-подбор b24_user_id по email пользователя (admin)."""
    from sqlalchemy import select as sa_select
    import uuid as _uuid
    from ...models import User as UserModel, Integration
    from ...services.integrations.bitrix24 import client as b24_client_mod
    from ...services.settings.crypto import decrypt_text

    try:
        uid = _uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise ValidationError("Неверный формат user_id")

    target = (await session.execute(
        sa_select(UserModel).where(
            UserModel.id == uid,
            UserModel.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if not target:
        raise ValidationError("Пользователь не найден")

    b24_row = (await session.execute(
        sa_select(Integration).where(
            Integration.provider == "bitrix24",
            Integration.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if not b24_row or not (b24_row.config or {}).get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    webhook_url = decrypt_text(b24_row.config["webhook_url"])
    b24_user = await b24_client_mod.find_user_by_email(webhook_url, target.email)
    if not b24_user:
        raise ValidationError(f"Пользователь с email {target.email} не найден в Битрикс24")

    b24_id = b24_user.get("ID")
    if not b24_id:
        raise ValidationError("Б24 не вернул ID пользователя")

    target.b24_user_id = int(b24_id)
    await session.flush()
    await session.commit()
    return {"id": str(target.id), "b24_user_id": target.b24_user_id, "full_name": target.full_name}


# ---------------------------------------------------------------------------
# Telegram (user-аккаунт, MTProto) — «писать из-под пользователя»
# ---------------------------------------------------------------------------

@router.get("/telegram/status", dependencies=[Depends(require_settings_read_access)])
async def get_tg_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Статус Telegram-интеграции (сессия/секреты не возвращаются)."""
    return await tg_service.get_status(session, current_user.company_id)


@router.post("/telegram/send-code", dependencies=[Depends(require_admin)])
async def tg_send_code(
    data: TgSendCodeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Шаг 1: запросить код на номер."""
    result = await tg_service.send_code(session, current_user.company_id, current_user.id, phone=data.phone)
    await session.commit()
    return result


@router.post("/telegram/connect-session", dependencies=[Depends(require_admin)])
async def tg_connect_session(
    data: TgConnectSessionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Подключить Telegram готовой строкой сессии (StringSession), минуя код."""
    result = await tg_service.connect_session(session, current_user.company_id, current_user.id, session_string=data.session)
    await session.commit()
    return result


@router.post("/telegram/resend-code", dependencies=[Depends(require_admin)])
async def tg_resend_code(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Повторно запросить код (next_type, обычно App → SMS)."""
    result = await tg_service.resend_code(session, current_user.company_id, current_user.id)
    await session.commit()
    return result


@router.post("/telegram/confirm-code", dependencies=[Depends(require_admin)])
async def tg_confirm_code(
    data: TgConfirmCodeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Шаг 2: ввод кода (может вернуть state='pending_password' при 2FA)."""
    result = await tg_service.confirm_code(session, current_user.company_id, current_user.id, code=data.code)
    await session.commit()
    return result


@router.post("/telegram/confirm-password", dependencies=[Depends(require_admin)])
async def tg_confirm_password(
    data: TgConfirmPasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Шаг 2б: облачный пароль 2FA."""
    result = await tg_service.confirm_password(session, current_user.company_id, current_user.id, password=data.password)
    await session.commit()
    return result


@router.post("/telegram/test", dependencies=[Depends(require_admin)])
async def tg_test(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Тест: отправить сообщение себе («Избранное»)."""
    # send_test коммитит сам (оба пути).
    return await tg_service.send_test(session, current_user.company_id, current_user.id)


@router.post("/telegram/qr/start", dependencies=[Depends(require_admin)])
async def tg_qr_start(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """QR-вход шаг 1: ExportLoginToken → возвращает SVG-QR (data-uri) и expires.

    Пользователь открывает Telegram на телефоне → Настройки → Устройства →
    Подключить устройство → сканирует QR. Затем клиент поллит /qr/status.
    """
    result = await tg_service.qr_start(session, current_user.company_id, current_user.id)
    await session.commit()
    return result


@router.get("/telegram/qr/status", dependencies=[Depends(require_admin)])
async def tg_qr_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """QR-вход шаг 2: ImportLoginToken → проверить состояние.

    Поллить каждые 2–3 секунды до state='connected'|'need_password'.
    При state='waiting' + qr_image — токен протух, показать новый QR.
    При state='need_password' — вызвать /confirm-password как обычно.
    """
    result = await tg_service.qr_status(session, current_user.company_id, current_user.id)
    await session.commit()
    return result


@router.post("/telegram/disconnect", dependencies=[Depends(require_admin)])
async def tg_disconnect(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить Telegram (сессия удаляется полностью)."""
    await tg_service.disconnect(session, current_user.company_id, current_user.id)
    await session.commit()
    return {"message": "Telegram отключён"}


# ---------------------------------------------------------------------------
# Mango Office (VPBX API)
# ---------------------------------------------------------------------------

@router.post("/mango/config", dependencies=[Depends(require_admin)])
async def save_mango_config(
    data: MangoConfigRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Сохранить конфигурацию Mango Office. Возвращает статус (без секретов)."""
    await mango_service.save_config(
        session,
        current_user.company_id,
        api_key=data.api_key,
        api_salt=data.api_salt,
        vpbx_api_url=data.vpbx_api_url,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return await mango_service.get_status(session, current_user.company_id)


@router.get("/mango/status", dependencies=[Depends(require_settings_read_access)])
async def get_mango_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Статус интеграции Mango Office (секреты не возвращаются)."""
    return await mango_service.get_status(session, current_user.company_id)


@router.post("/mango/test", dependencies=[Depends(require_admin)])
async def test_mango(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Проверить подключение к Mango Office (реальный вызов stats/request)."""
    # test_connection коммитит сам (успех и сбой) — чтобы last_test_* сохранилось.
    return await mango_service.test_connection(
        session, current_user.company_id, actor_user_id=current_user.id
    )


@router.post("/mango/disconnect", dependencies=[Depends(require_admin)])
async def disconnect_mango(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить Mango Office (status=disconnected; конфиг остаётся)."""
    await mango_service.disconnect(
        session, current_user.company_id, actor_user_id=current_user.id
    )
    await session.commit()
    return {"message": "Mango Office отключён"}


# ---------------------------------------------------------------------------
# Хабр Карьера — OAuth-подключение (ТОЛЬКО connect; приём откликов/поиск НЕ реализованы)
# ---------------------------------------------------------------------------

@router.get("/habr/status", dependencies=[Depends(require_settings_read_access)])
async def get_habr_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Статус OAuth-подключения Хабр Карьера для компании."""
    return await habr_service.get_status(session, current_user.company_id)


@router.get("/habr/authorize", dependencies=[Depends(require_admin)])
async def start_habr_authorization(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Начать OAuth-флоу Хабр Карьера. Возвращает {authorize_url} для редиректа браузера."""
    authorize_url = await habr_service.start_oauth(
        session, current_user.company_id, current_user.id
    )
    await session.commit()
    return {"authorize_url": authorize_url}


@router.get("/habr/callback")
async def habr_oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    session: AsyncSession = Depends(get_db)
):
    """Callback-эндпоинт OAuth Хабр Карьера (ПУБЛИЧНЫЙ — без авторизации, защищён через state).

    Хабр Карьера проверяет этот URL при одобрении приложения.
    НИКОГДА не возвращает 500 — всегда RedirectResponse на фронт.

    Redirect URI (точный): https://glafira.dclouds.ru/api/v1/integrations/habr/callback
    """
    frontend_base = settings.FRONTEND_BASE_URL

    if error:
        # Пользователь нажал «Отклонить» / «Назад» на странице авторизации Хабра
        return RedirectResponse(
            url=f"{frontend_base}/settings?tab=integrations&habr=denied"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_base}/settings?tab=integrations&habr=error"
        )

    try:
        await habr_service.handle_callback(session, code, state)
        await session.commit()
        return RedirectResponse(
            url=f"{frontend_base}/settings?tab=integrations&habr=connected"
        )

    except AppError as e:
        logger.warning("Хабр OAuth callback failed: %s", e.message)
        return RedirectResponse(
            url=f"{frontend_base}/settings?tab=integrations&habr=error&habr_msg={quote(e.message)}"
        )
    except Exception:
        logger.exception("Хабр OAuth callback: неожиданная ошибка")
        return RedirectResponse(
            url=f"{frontend_base}/settings?tab=integrations&habr=error"
        )


@router.post("/habr/disconnect", dependencies=[Depends(require_admin)])
async def disconnect_habr(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить интеграцию Хабр Карьера (обнуляет токены)."""
    await habr_service.disconnect(session, current_user.company_id)
    await session.commit()
    return {"message": "Хабр Карьера отключён"}


# ---------------------------------------------------------------------------
# Хабр Карьера — синхронизация откликов (новые эндпоинты)
# ---------------------------------------------------------------------------

@router.post("/habr/poll-responses", dependencies=[Depends(require_admin)])
async def habr_poll_responses(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Ручной забор откликов с Хабр Карьера (привязанные вакансии → этап «Отклик»).

    ⚠️ Требует подключённого Хабра + привязанных вакансий (habr_vacancy_id).
    Тратит API-квоту Хабра. Пиннинг эндпоинтов Хабра — после одобрения приложения.
    """
    result = await habr_sync.poll_habr_responses_now(session, current_user.company_id)
    await session.commit()
    return result


@router.get("/habr/vacancies", dependencies=[Depends(require_settings_read_access)])
async def list_habr_vacancies(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Список вакансий работодателя на Хабр Карьере (для UI-связывания).

    Эндпоинт: GET {HABR_API_BASE}/vacancies
    При ошибке возвращает честный 400 с описанием.
    """
    access_token = await habr_sync.get_valid_access_token_habr(session, current_user.company_id)
    try:
        data = await habr_client_module.get_employer_vacancies(access_token)
    except ValueError as exc:
        from ...core.errors import ValidationError as AppValidationError
        raise AppValidationError(str(exc)) from exc

    # Структура ответа GET /vacancies — список вакансий (точный формат уточняется при первом prod-запуске)
    items = data.get("items") or data.get("vacancies") or []
    return [
        {
            "id": str(item.get("id") or ""),
            "title": item.get("title") or item.get("name") or "",
            "city": (item.get("city") or {}).get("name") if isinstance(item.get("city"), dict) else item.get("city"),
        }
        for item in items
        if item.get("id")
    ]


@router.post("/habr/link-vacancy", dependencies=[Depends(require_admin)])
async def habr_link_vacancy(
    data: HabrLinkVacancyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Привязать вакансию Глафиры к вакансии Хабр Карьера."""
    import uuid as _uuid
    try:
        vacancy_id = _uuid.UUID(data.vacancy_id)
    except ValueError as exc:
        from ...core.errors import ValidationError as AppValidationError
        raise AppValidationError("Некорректный vacancy_id") from exc

    await habr_sync.link_habr_vacancy(
        session,
        vacancy_id=vacancy_id,
        habr_vacancy_id=data.habr_vacancy_id,
        company_id=current_user.company_id,
        user_id=current_user.id,
    )
    await session.commit()
    return {"message": "Вакансия привязана к Хабр Карьере", "habr_vacancy_id": data.habr_vacancy_id}


@router.post("/habr/unlink-vacancy", dependencies=[Depends(require_admin)])
async def habr_unlink_vacancy(
    vacancy_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отвязать вакансию Глафиры от Хабр Карьеры."""
    import uuid as _uuid
    try:
        vid = _uuid.UUID(vacancy_id)
    except ValueError as exc:
        from ...core.errors import ValidationError as AppValidationError
        raise AppValidationError("Некорректный vacancy_id") from exc

    await habr_sync.unlink_habr_vacancy(
        session,
        vacancy_id=vid,
        company_id=current_user.company_id,
        user_id=current_user.id,
    )
    await session.commit()
    return {"message": "Вакансия отвязана от Хабр Карьеры"}


@router.post(
    "/habr/candidates/{candidate_id}/open-contacts",
    dependencies=[Depends(require_admin)],
)
async def habr_open_candidate_contacts(
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Открыть контакты кандидата Хабра (phone/email).

    ⚠️ ПЛАТНО: каждый первый вызов списывает лимит открытий контактов компании на Хабре.
    Повторный вызов (если контакты уже открыты) — БЕСПЛАТНО, возвращает имеющиеся данные.

    Требует: кандидат source='habr' + external_id(login) + подключённый Хабр.
    Ошибки: 400 если лимит исчерпан / нет доступа (НЕ 500, НЕ фейк-успех).

    После открытия контактов: дедуп с базой (phone/email) → при совпадении слияние кандидатов.
    Возврат: { merged, candidate_id, phone, email, already_opened }
    """
    import uuid as _uuid
    try:
        cid = _uuid.UUID(candidate_id)
    except ValueError as exc:
        raise ValidationError("Некорректный candidate_id") from exc

    result = await habr_sync.open_habr_contacts(
        session,
        company_id=current_user.company_id,
        candidate_id=cid,
        user_id=current_user.id,
    )
    await session.commit()
    return result


# ---------------------------------------------------------------------------
# Авито Работа — client_credentials, отклики на вакансии работодателя
# ---------------------------------------------------------------------------

@router.post("/avito/config", dependencies=[Depends(require_admin)])
async def save_avito_config(
    data: AvitoConfigRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Сохранить client_id/secret Авито (per-company, Fernet-шифрование).

    OAuth: client_credentials — не нужен браузерный флоу.
    client_id/secret получают в Кабинете разработчика Авито.
    ⚠️ client_secret НЕ логируется и НЕ возвращается.
    """
    await avito_service.save_config(
        session,
        company_id=current_user.company_id,
        client_id=data.client_id,
        client_secret=data.client_secret,
        user_id=current_user.id,
        avito_user_id=data.avito_user_id,
    )
    await session.commit()
    return {"message": "Авито подключён"}


@router.get("/avito/status", dependencies=[Depends(require_settings_read_access)])
async def get_avito_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Статус интеграции Авито: {connected, avito_user_id}."""
    return await avito_service.get_status(session, current_user.company_id)


@router.post("/avito/poll-responses", dependencies=[Depends(require_admin)])
async def avito_poll_responses(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Вручную запустить забор откликов Авито для привязанных вакансий.

    ⚠️ Требует подключённого Авито (client_id/secret) + привязанных вакансий (avito_vacancy_id).
    Телефон кандидата содержится в отклике БЕСПЛАТНО — /contacts НЕ вызывается.
    Возврат: {imported, updated, skipped, vacancies, errors}
    """
    result = await avito_sync.poll_avito_responses_now(session, current_user.company_id)
    await session.commit()
    return result


@router.post("/avito/link-vacancy", dependencies=[Depends(require_admin)])
async def avito_link_vacancy(
    data: AvitoLinkVacancyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Привязать вакансию Глафиры к вакансии Авито (avito_vacancy_id)."""
    import uuid as _uuid
    try:
        vacancy_id = _uuid.UUID(data.vacancy_id)
    except ValueError as exc:
        raise ValidationError("Некорректный vacancy_id") from exc

    await avito_service.link_avito_vacancy(
        session,
        vacancy_id=vacancy_id,
        avito_vacancy_id=data.avito_vacancy_id,
        company_id=current_user.company_id,
        user_id=current_user.id,
    )
    await session.commit()
    return {"message": "Вакансия привязана к Авито", "avito_vacancy_id": data.avito_vacancy_id}


@router.post("/avito/unlink-vacancy", dependencies=[Depends(require_admin)])
async def avito_unlink_vacancy(
    vacancy_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Отвязать вакансию Глафиры от Авито."""
    import uuid as _uuid
    try:
        vid = _uuid.UUID(vacancy_id)
    except ValueError as exc:
        raise ValidationError("Некорректный vacancy_id") from exc

    await avito_service.unlink_avito_vacancy(
        session,
        vacancy_id=vid,
        company_id=current_user.company_id,
        user_id=current_user.id,
    )
    await session.commit()
    return {"message": "Вакансия отвязана от Авито"}


@router.post("/avito/disconnect", dependencies=[Depends(require_admin)])
async def avito_disconnect(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Отключить интеграцию Авито (очистить credentials и кэш токена)."""
    await avito_service.disconnect(session, current_user.company_id, current_user.id)
    await session.commit()
    return {"message": "Авито отключён"}