"""Публичные эндпоинты опроса пульса (БЕЗ авторизации).

Респондент (сотрудник) проходит опрос по секретной ссылке вида
`/pulse/survey/#<public_token>`. Токен высокоэнтропийный (secrets.token_urlsafe(32))
и живёт в URL-хеше у фронта — на сервер/в логи не уходит. Никакой авторизации:
доступ контролирует только знание токена. PII на выдаче минимизирован (имя + компания).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...schemas.pulse import (
    PublicSurveyOut, PublicSurveyQuestion,
    PublicSurveySubmit, PublicSurveySubmitResult,
)
from ...services.pulse import surveys as surveys_svc

router = APIRouter()


def _first_name(full_name: str | None) -> str:
    """Имя для приветствия. ФИО хранится как «Фамилия Имя [Отчество]» —
    берём второй токен (Имя), иначе первый."""
    parts = (full_name or "").split()
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else ""


@router.get("/surveys/{token}", response_model=PublicSurveyOut)
async def get_public_survey(
    token: str,
    session: AsyncSession = Depends(get_db),
):
    """Данные опроса для публичной страницы (брендинг + вопросы)."""
    survey, employee, company = await surveys_svc.get_public_survey(session, token)
    return PublicSurveyOut(
        company_name=company.name if company else "",
        employee_first_name=_first_name(employee.full_name if employee else None),
        type=survey.type,
        answered=survey.answered_at is not None,
        questions=[PublicSurveyQuestion(**q) for q in (survey.questions or [])],
    )


@router.post("/surveys/{token}/answers", response_model=PublicSurveySubmitResult)
async def submit_public_survey(
    token: str,
    data: PublicSurveySubmit,
    session: AsyncSession = Depends(get_db),
):
    """Приём ответов респондента. Повторная отправка отклоняется (409)."""
    survey = await surveys_svc.submit_public_survey(session, token, data.answers)
    await session.commit()
    return PublicSurveySubmitResult(
        status="success",
        overall_score=float(survey.overall_score) if survey.overall_score is not None else None,
    )
