"""Публичная форма подачи заявки на подбор — БЕЗ авторизации.

Зеркало public_schedule.py: company_id берётся ТОЛЬКО из ротируемого токена компании
(RequestSettings.form_token), rate-limit in-memory, honeypot-поле против ботов. Наружу
отдаётся МИНИМУМ (только название компании для брендинга).
"""
import asyncio
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...core.errors import AppError
from ...models import RequestSettings, Company
from ...schemas.hiring_request import PublicFormInfo, PublicRequestSubmit, PublicRequestResult
from ...services import hiring_request as svc

router = APIRouter()

# ── Rate limiter (in-memory, best-effort) — форма спамится сильнее, окно жёстче ──
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = asyncio.Lock()
_RATE_LIMIT = 10       # запросов
_RATE_WINDOW = 60.0    # секунд


async def _check_rate_limit(request: Request, token: str) -> None:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    key = f"{ip}:{token}"
    now = time.monotonic()
    async with _rate_lock:
        timestamps = [t for t in _rate_store[key] if now - t < _RATE_WINDOW]
        if len(timestamps) >= _RATE_LIMIT:
            _rate_store[key] = timestamps
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "RATE_LIMITED", "message": "Слишком много запросов. Попробуйте позже."}},
            )
        timestamps.append(now)
        _rate_store[key] = timestamps


async def _company_for_token(session: AsyncSession, token: str):
    """Компания по активному токену формы. Нет/выключено → 404 без деталей."""
    st = (await session.execute(
        select(RequestSettings).where(RequestSettings.form_token == token)
    )).scalar_one_or_none()
    if st is None or not st.form_enabled:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Форма не найдена"}},
        )
    company = await session.get(Company, st.company_id)
    if company is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Форма не найдена"}},
        )
    return st, company


@router.get("/request-form/{token}", response_model=PublicFormInfo)
async def get_form_info(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    await _check_rate_limit(request, token)
    _st, company = await _company_for_token(session, token)
    return PublicFormInfo(company_name=company.name, enabled=True)


@router.post("/request-form/{token}", response_model=PublicRequestResult)
async def submit_form(
    token: str,
    body: PublicRequestSubmit,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    await _check_rate_limit(request, token)
    st, company = await _company_for_token(session, token)

    # Honeypot: реальные люди поле website не заполняют. Непусто → тихо «приняли»,
    # но НЕ создаём запись (не 4xx, чтобы бот не подстраивался).
    if body.website and body.website.strip():
        return PublicRequestResult(ok=True, num=None)

    try:
        req = await svc.create_request(
            session, company_id=st.company_id, user=None, data=body, via="form",
            author_name=(body.author_name or None),
            author_role=(body.author_role or None),
            author_contact=(body.author_contact or None),
        )
        await session.commit()
    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": {"code": e.code, "message": e.message}},
        )
    return PublicRequestResult(ok=True, num=req.num)
