"""Эндпоинты для работы с интеграциями"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ...deps import get_current_user
from ...core.errors import ValidationError
from ...database import get_db
from ...models import User
from ...services.integrations.hh import service as hh_service
from ...services.integrations.smtp import service as smtp_service
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

router = APIRouter()


@router.post("/hh/config")
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


@router.get("/hh/status")
async def get_hh_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Получить статус интеграции hh.ru"""
    status = await hh_service.get_status(session, current_user.company_id)
    return status


@router.get("/hh/authorize")
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


@router.post("/hh/disconnect")
async def disconnect_hh(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить интеграцию hh.ru"""
    await hh_service.disconnect(session, current_user.company_id, current_user.id)

    return {"message": "Интеграция hh.ru отключена"}


@router.get("/hh/vacancies")
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

@router.post("/smtp/config")
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


@router.get("/smtp/status")
async def get_smtp_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Статус SMTP-интеграции (пароль не возвращается)."""
    return await smtp_service.get_status(session, current_user.company_id)


@router.post("/smtp/test")
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


@router.post("/smtp/disconnect")
async def disconnect_smtp(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Отключить SMTP (status=disconnected; конфиг остаётся)."""
    await smtp_service.disconnect(session, current_user.company_id, current_user.id)
    await session.commit()
    return {"message": "SMTP отключён"}