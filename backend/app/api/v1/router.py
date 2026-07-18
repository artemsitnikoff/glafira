from fastapi import APIRouter, Depends

from .auth import router as auth_router
from .users import router as users_router
from .vacancies import router as vacancies_router
from .applications import router as applications_router
from .candidates import router as candidates_router
from .candidate_import import router as candidate_import_router
from .clients import router as clients_router
from .consents import router as consents_router
from .messages import router as messages_router
from .documents import router as documents_router
from .comments import router as comments_router
from .glafira import router as glafira_router, candidates_evaluation_router
from .verifications import router as verifications_router
from .pulse import router as pulse_router
from .public_surveys import router as public_surveys_router
from .public_photo import router as public_photo_router
from .public_schedule import router as public_schedule_router
from .home import router as home_router
from .analytics import router as analytics_router
from .settings import router as settings_router
from .audit import router as audit_router
from .integrations import router as integrations_router
from .suggestions import router as suggestions_router
from .smart import router as smart_router
from .message_templates import router as message_templates_router
from .calls import router as calls_router
from .requests import router as requests_router
from .public_requests import router as public_requests_router
from ...core.permissions import (
    settings_permission_dependency,
    integrations_permission_dependency,
    require_recruiter_or_admin,
    forbid_hiring_manager,
)

# Deny-by-default для роли hiring_manager (нанимающий менеджер): навешивается на ВСЕ
# роутеры данных ниже. Единственные доступные ему data-роуты — /requests (author-scoped)
# и /auth/me. Публичные роутеры (без авторизации) сюда не входят.
_deny_hm = [Depends(forbid_hiring_manager)]

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"], dependencies=_deny_hm)
api_router.include_router(vacancies_router, prefix="/vacancies", tags=["vacancies"], dependencies=_deny_hm)
api_router.include_router(applications_router, tags=["applications"], dependencies=_deny_hm)
api_router.include_router(candidates_router, prefix="/candidates", tags=["candidates"], dependencies=_deny_hm)
api_router.include_router(candidate_import_router, prefix="/candidates/import", tags=["candidate_import"], dependencies=_deny_hm)
api_router.include_router(
    clients_router,
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_recruiter_or_admin)],
)
api_router.include_router(consents_router, tags=["consents"], dependencies=_deny_hm)
api_router.include_router(messages_router, tags=["messages"], dependencies=_deny_hm)
api_router.include_router(documents_router, tags=["documents"], dependencies=_deny_hm)
api_router.include_router(comments_router, tags=["comments"], dependencies=_deny_hm)
api_router.include_router(glafira_router, prefix="/glafira", tags=["glafira"], dependencies=_deny_hm)
api_router.include_router(candidates_evaluation_router, tags=["glafira"], dependencies=_deny_hm)
api_router.include_router(verifications_router, tags=["verifications"], dependencies=_deny_hm)
api_router.include_router(pulse_router, prefix="/pulse", tags=["pulse"], dependencies=_deny_hm)
# Публичные опросы — БЕЗ авторизации (доступ по секретному токену). См. public_surveys.py
api_router.include_router(public_surveys_router, prefix="/public", tags=["public"])
# Публичный прокси фото кандидата — БЕЗ авторизации (<img src> не шлёт токен).
# SSRF-гард внутри (только hh-домены). Путь: /api/v1/public/photo. См. public_photo.py
api_router.include_router(public_photo_router, prefix="/public", tags=["public"])
# Публичная запись на интервью — БЕЗ авторизации (доступ по секретному токену).
# Rate-limit in-memory (30/min per IP:token). Путь: /api/v1/public/schedule/...
api_router.include_router(public_schedule_router, prefix="/public", tags=["public"])
api_router.include_router(home_router, prefix="/home", tags=["home"], dependencies=_deny_hm)
api_router.include_router(
    analytics_router,
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_recruiter_or_admin)],
)
api_router.include_router(
    settings_router,
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(settings_permission_dependency)]
)
api_router.include_router(audit_router, prefix="/audit-log", tags=["audit"], dependencies=_deny_hm)
api_router.include_router(
    integrations_router,
    prefix="/integrations",
    tags=["integrations"],
    dependencies=_deny_hm,
)
api_router.include_router(suggestions_router, prefix="/suggestions", tags=["suggestions"], dependencies=_deny_hm)
api_router.include_router(
    smart_router,
    prefix="/smart",
    tags=["smart"],
    dependencies=[Depends(require_recruiter_or_admin)]
)
api_router.include_router(message_templates_router, prefix="/message-templates", tags=["message_templates"], dependencies=_deny_hm)
# Звонки — статические роуты ПЕРЕД динамическими
api_router.include_router(calls_router, tags=["calls"], dependencies=_deny_hm)

# ── Заявки на подбор ─────────────────────────────────────────────────────────
# /requests — БЕЗ _deny_hm: нанимающий менеджер сюда ХОДИТ, скоуп по автору внутри.
api_router.include_router(requests_router, prefix="/requests", tags=["requests"])
# Публичная форма заявки — БЕЗ авторизации (доступ по ротируемому токену компании).
# Rate-limit + honeypot внутри. Путь: /api/v1/public/request-form/...
api_router.include_router(public_requests_router, prefix="/public", tags=["public"])