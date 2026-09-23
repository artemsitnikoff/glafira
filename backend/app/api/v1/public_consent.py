"""Публичное онлайн-подписание согласия на обработку ПдН (БЕЗ авторизации).

Кандидат получает ссылку /consent/{token} (фронт) и взаимодействует с двумя
эндпоинтами ниже. company_id определяется ТОЛЬКО из токена (lookup Consent по token).

Наружу отдаём МИНИМУМ PII: имя кандидата и текст согласия — да; телефон/email/
внутренние ID — НЕТ. Как только статус становится 'signed', consent-гейт 152-ФЗ
(verify/scoring/base_search/…) открывается сам — здесь мы гейт-логику НЕ трогаем.

Rate-limit: in-memory best-effort, 30 req/min per IP:token. X-Forwarded-For учитывается
(зеркало public_schedule).
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models import Candidate, Consent
from ...services.audit import audit
from ...services.company_display import resolve_company_display_name
from ...services.consent import build_consent_text

logger = logging.getLogger(__name__)

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Rate limiter (in-memory, best-effort) — тот же паттерн, что в public_schedule.
# ──────────────────────────────────────────────────────────────────────────────
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = asyncio.Lock()
_RATE_LIMIT = 30  # запросов
_RATE_WINDOW = 60.0  # секунд


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    return forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )


async def _check_rate_limit(request: Request, token: str) -> None:
    key = f"{_client_ip(request)}:{token}"
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


async def _get_consent_or_raise(session: AsyncSession, token: str) -> Consent:
    """Загружает Consent по токену. 404 без деталей (не раскрываем company/candidate)."""
    consent = (await session.execute(
        select(Consent).where(Consent.token == token)
    )).scalar_one_or_none()
    if not consent:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Ссылка не найдена"}},
        )
    return consent


def _is_expired(consent: Consent, now: datetime) -> bool:
    """Согласие «протухло»: не подписано И срок истёк."""
    if consent.status == "signed":
        return False
    exp = consent.expires_at
    if exp is None:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp < now


# ──────────────────────────────────────────────────────────────────────────────
# Схемы
# ──────────────────────────────────────────────────────────────────────────────

class ConsentPublicInfo(BaseModel):
    company_name: str
    candidate_name: str
    consent_text: str
    status: str  # 'pending' | 'signed' | 'revoked'
    expires_at: datetime | None = None
    can_sign: bool
    already_signed: bool
    expired: bool


class ConsentSignResult(BaseModel):
    status: str
    signed_at: datetime | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Эндпоинты
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/consent/{token}", response_model=ConsentPublicInfo)
async def get_consent_info(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Данные страницы подписания: компания, имя кандидата, текст согласия, статус.

    БЕЗ телефонов/email/внутренних ID. Истёкшая ссылка → 200 с expired=true (страница
    покажет «ссылка истекла»); несуществующий токен → 404.
    """
    await _check_rate_limit(request, token)

    consent = await _get_consent_or_raise(session, token)
    now = datetime.now(timezone.utc)

    # company_id — ТОЛЬКО из токена (из самой записи согласия).
    candidate = (await session.execute(
        select(Candidate).where(
            Candidate.id == consent.candidate_id,
            Candidate.company_id == consent.company_id,
        )
    )).scalar_one_or_none()
    candidate_name = candidate.full_name if candidate else ""

    company_name = await resolve_company_display_name(session, consent.company_id, None)

    consent_text = consent.consent_text or build_consent_text(candidate_name, company_name)

    expired = _is_expired(consent, now)
    already_signed = consent.status == "signed"
    can_sign = consent.status == "pending" and not expired

    return ConsentPublicInfo(
        company_name=company_name,
        candidate_name=candidate_name,
        consent_text=consent_text,
        status=consent.status,
        expires_at=consent.expires_at,
        can_sign=can_sign,
        already_signed=already_signed,
        expired=expired,
    )


@router.post("/consent/{token}/sign", response_model=ConsentSignResult)
async def sign_consent_public(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Кандидат подписывает согласие. Идемпотентно (повторный клик → тот же ok).

    signed → 200 (идемпотентно); revoked → 400; истёкшее pending → 410.
    company_id берётся ТОЛЬКО из токена. Пишем audit (actor_type='system', т.к. кандидат
    не является пользователем системы). Как только status='signed' — гейт 152-ФЗ открыт.
    """
    await _check_rate_limit(request, token)

    consent = await _get_consent_or_raise(session, token)
    now = datetime.now(timezone.utc)

    # Уже подписано — идемпотентно.
    if consent.status == "signed":
        return ConsentSignResult(status="signed", signed_at=consent.signed_at)

    if consent.status == "revoked":
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "CONSENT_REVOKED", "message": "Согласие было отозвано"}},
        )

    if _is_expired(consent, now):
        raise HTTPException(
            status_code=410,
            detail={"error": {"code": "LINK_EXPIRED", "message": "Срок ссылки истёк"}},
        )

    ip = _client_ip(request)

    # Атомарный переход pending→signed: защита от двойного клика (второй получит 0 строк).
    claimed = await session.execute(
        update(Consent)
        .where(Consent.token == token, Consent.status == "pending")
        .values(status="signed", signed_at=now, signed_ip=ip[:64], signed_by="candidate")
        .returning(Consent.id)
    )
    if claimed.first() is None:
        # Кто-то подписал/изменил параллельно — перечитываем и отдаём актуальное.
        fresh = await _get_consent_or_raise(session, token)
        if fresh.status == "signed":
            return ConsentSignResult(status="signed", signed_at=fresh.signed_at)
        if fresh.status == "revoked":
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "CONSENT_REVOKED", "message": "Согласие было отозвано"}},
            )
        raise HTTPException(
            status_code=410,
            detail={"error": {"code": "LINK_EXPIRED", "message": "Срок ссылки истёк"}},
        )

    # Синхронизируем ORM-инстанс: сырой UPDATE в загруженный объект не попадает
    # (expire_on_commit=False → identity-map отдаст stale-поля).
    consent.status = "signed"
    consent.signed_at = now
    consent.signed_ip = ip[:64]
    consent.signed_by = "candidate"

    await audit(
        session,
        action="sign_consent",
        entity_type="consent",
        entity_id=consent.id,
        before={"status": "pending"},
        after={"status": "signed", "signed_at": now.isoformat(), "by": "candidate", "ip": ip[:64]},
        actor_user_id=None,
        actor_type="system",
        company_id=consent.company_id,
    )
    await session.commit()

    return ConsentSignResult(status="signed", signed_at=now)
