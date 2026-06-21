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
from .home import router as home_router
from .analytics import router as analytics_router
from .settings import router as settings_router
from .audit import router as audit_router
from .integrations import router as integrations_router
from .suggestions import router as suggestions_router
from .smart import router as smart_router
from .message_templates import router as message_templates_router
from .calls import router as calls_router
from ...core.permissions import settings_permission_dependency, integrations_permission_dependency, require_recruiter_or_admin

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(vacancies_router, prefix="/vacancies", tags=["vacancies"])
api_router.include_router(applications_router, tags=["applications"])
api_router.include_router(candidates_router, prefix="/candidates", tags=["candidates"])
api_router.include_router(candidate_import_router, prefix="/candidates/import", tags=["candidate_import"])
api_router.include_router(
    clients_router,
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_recruiter_or_admin)],
)
api_router.include_router(consents_router, tags=["consents"])
api_router.include_router(messages_router, tags=["messages"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(comments_router, tags=["comments"])
api_router.include_router(glafira_router, prefix="/glafira", tags=["glafira"])
api_router.include_router(candidates_evaluation_router, tags=["glafira"])
api_router.include_router(verifications_router, tags=["verifications"])
api_router.include_router(pulse_router, prefix="/pulse", tags=["pulse"])
# Публичные опросы — БЕЗ авторизации (доступ по секретному токену). См. public_surveys.py
api_router.include_router(public_surveys_router, prefix="/public", tags=["public"])
api_router.include_router(home_router, prefix="/home", tags=["home"])
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
api_router.include_router(audit_router, prefix="/audit-log", tags=["audit"])
api_router.include_router(
    integrations_router,
    prefix="/integrations",
    tags=["integrations"],
)
api_router.include_router(suggestions_router, prefix="/suggestions", tags=["suggestions"])
api_router.include_router(
    smart_router,
    prefix="/smart",
    tags=["smart"],
    dependencies=[Depends(require_recruiter_or_admin)]
)
api_router.include_router(message_templates_router, prefix="/message-templates", tags=["message_templates"])
# Звонки — статические роуты ПЕРЕД динамическими
api_router.include_router(calls_router, tags=["calls"])