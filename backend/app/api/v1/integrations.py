"""Эндпоинты для работы с интеграциями"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...deps import get_current_user
from ...core.errors import ValidationError
from ...database import get_db
from ...models import User
from ...services.integrations.hh import service as hh_service
from ...config import settings

router = APIRouter()


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