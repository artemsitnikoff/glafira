"""Эндпоинты для работы с интеграциями"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ...deps import get_current_user
from ...core.errors import ValidationError, ForbiddenError
from ...core.permissions import require_admin, require_settings_read_access
from ...database import get_db
from ...models import User
from ...services.integrations.hh import service as hh_service
from ...services.integrations.smtp import service as smtp_service
from ...services.integrations.bitrix24 import service as b24_service
from ...services.integrations.telegram import service as tg_service
from ...schemas.bitrix24 import BitrixDepartment, BitrixImportCandidate, BitrixImportRequest, BitrixImportResult
from ...config import settings


class HhConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str


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

router = APIRouter()


@router.post("/hh/config", dependencies=[Depends(require_admin)])
async def save_hh_config(
    data: HhConfigRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Сохранить конфигурацию hh.ru и начать OAuth"""
    # Сохраняем конфигурацию
    await hh_service.save_config(
        session,
        current_user.company_id,
        current_user.id,
        data.client_id,
        data.client_secret,
        data.redirect_uri
    )

    # Сразу начинаем OAuth flow
    authorize_url = await hh_service.start_oauth(
        session, current_user.company_id, current_user.id
    )

    return {"authorize_url": authorize_url}


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

    except Exception:
        # Это браузерный редирект — на ЛЮБУЮ ошибку (невалидный state, сбой обмена кода,
        # недоступность hh) возвращаем редирект на фронт, а не 500.
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


@router.post("/telegram/disconnect", dependencies=[Depends(require_admin)])
async def tg_disconnect(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить Telegram (сессия удаляется полностью)."""
    await tg_service.disconnect(session, current_user.company_id, current_user.id)
    await session.commit()
    return {"message": "Telegram отключён"}