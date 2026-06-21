"""Glafira AI API endpoints"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...deps import get_current_user, get_db
from ...core.errors import NotFoundError, ValidationError, ForbiddenError
from ...core.permissions import can_manager_access_candidate
from ...models import User, AiEvaluation, Application
from ...schemas.glafira import (
    ScoreRequest,
    EvaluationOut,
    RequirementMatch,
    ScreeningStartRequest,
    ScreeningReplyRequest,
    ScreeningOut
)
from ...services.glafira.scoring import score_candidate
from ...services.glafira.scoring_log import log_scoring
from ...services.glafira.screening import start_screening, reply_screening

router = APIRouter()
# Separate router for /candidates/{id}/evaluation — mounted without /glafira prefix per TZ-2 §6.1.
candidates_evaluation_router = APIRouter()


async def _find_existing_evaluation(
    session: AsyncSession,
    candidate_id: UUID,
    application_id: UUID | None,
    company_id: UUID
) -> AiEvaluation | None:
    """Helper to find existing evaluation for candidate/application pair"""
    result = await session.execute(
        select(AiEvaluation).where(
            AiEvaluation.candidate_id == candidate_id,
            AiEvaluation.application_id.is_not_distinct_from(application_id),
            AiEvaluation.company_id == company_id
        ).order_by(AiEvaluation.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _find_evaluation_for_filter(
    session: AsyncSession,
    candidate_id: UUID,
    application_id: UUID | None,
    vacancy_id: UUID | None,
    company_id: UUID
) -> AiEvaluation | None:
    """Helper to find evaluation with flexible filtering"""
    if application_id is not None:
        # Direct lookup by application_id
        result = await session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == candidate_id,
                AiEvaluation.application_id == application_id,
                AiEvaluation.company_id == company_id
            ).order_by(AiEvaluation.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    elif vacancy_id is not None:
        # Resolve vacancy_id to application_id first
        app_result = await session.execute(
            select(Application).where(
                Application.candidate_id == candidate_id,
                Application.vacancy_id == vacancy_id,
                Application.company_id == company_id
            )
        )
        application = app_result.scalar_one_or_none()
        if not application:
            return None

        # Find evaluation by resolved application_id
        result = await session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == candidate_id,
                AiEvaluation.application_id == application.id,
                AiEvaluation.company_id == company_id
            ).order_by(AiEvaluation.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    else:
        # Get general evaluation (application_id IS NULL)
        result = await session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == candidate_id,
                AiEvaluation.application_id.is_(None),
                AiEvaluation.company_id == company_id
            ).order_by(AiEvaluation.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()


@router.post("/score", response_model=EvaluationOut, status_code=201)
async def score_candidate_endpoint(
    data: ScoreRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Score candidate for vacancy using Glafira AI"""

    if current_user.role == "manager":
        raise ForbiddenError("Менеджеры не могут оценивать кандидатов")

    # Determine application_id
    application_id = None
    if data.vacancy_id is not None:
        # Find application for this candidate/vacancy pair
        app_result = await session.execute(
            select(Application).where(
                Application.candidate_id == data.candidate_id,
                Application.vacancy_id == data.vacancy_id,
                Application.company_id == current_user.company_id
            )
        )
        application = app_result.scalar_one_or_none()
        if application:
            application_id = application.id

    # Check if evaluation already exists for this candidate/application pair.
    # При force=True пропускаем дедуп и считаем заново (переоценка с нуля).
    existing = None if data.force else await _find_existing_evaluation(
        session, data.candidate_id, application_id, current_user.company_id
    )

    if existing:
        # Оценка не создавалась (вернули существующую) → 200, а не 201
        log_scoring(
            f"КНОПКА • кандидат={data.candidate_id} • "
            f"оценки не было (уже была, балл {existing.score})"
        )
        response.status_code = 200
        return EvaluationOut(
            id=existing.id,
            candidate_id=existing.candidate_id,
            vacancy_id=data.vacancy_id,
            application_id=existing.application_id,
            score=existing.score,
            verdict=existing.verdict,
            summary=existing.summary,
            strengths=existing.strengths,
            risks=existing.risks,
            requirements_match=[RequirementMatch(**match) for match in (existing.requirements_match if isinstance(existing.requirements_match, list) else [])],
            forecast=existing.forecast or "",
            questions=existing.questions or [],
            model=existing.model,
            created_at=existing.created_at
        )

    # Create new evaluation
    evaluation = await score_candidate(
        session,
        candidate_id=data.candidate_id,
        vacancy_id=data.vacancy_id,
        company_id=current_user.company_id,
        actor_user_id=current_user.id,
        source="КНОПКА"
    )

    await session.commit()

    return EvaluationOut(
        id=evaluation.id,
        candidate_id=evaluation.candidate_id,
        vacancy_id=data.vacancy_id,
        application_id=evaluation.application_id,
        score=evaluation.score,
        verdict=evaluation.verdict,
        summary=evaluation.summary,
        strengths=evaluation.strengths,
        risks=evaluation.risks,
        requirements_match=[RequirementMatch(**match) for match in (evaluation.requirements_match if isinstance(evaluation.requirements_match, list) else [])],
        forecast=evaluation.forecast or "",
        questions=evaluation.questions or [],
        model=evaluation.model,
        created_at=evaluation.created_at
    )


@candidates_evaluation_router.get("/candidates/{candidate_id}/evaluation", response_model=EvaluationOut)
async def get_candidate_evaluation(
    candidate_id: UUID,
    application_id: UUID | None = Query(None),
    vacancy_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get evaluation for candidate"""
    # Менеджер: только кандидаты из своих вакансий
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, current_user.company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    if application_id is not None and vacancy_id is not None:
        raise ValidationError("Укажите либо application_id, либо vacancy_id, но не оба")

    evaluation = await _find_evaluation_for_filter(
        session, candidate_id, application_id, vacancy_id, current_user.company_id
    )

    if not evaluation:
        raise NotFoundError("Оценка")

    return EvaluationOut(
        id=evaluation.id,
        candidate_id=evaluation.candidate_id,
        vacancy_id=vacancy_id,
        application_id=evaluation.application_id,
        score=evaluation.score,
        verdict=evaluation.verdict,
        summary=evaluation.summary,
        strengths=evaluation.strengths,
        risks=evaluation.risks,
        requirements_match=[RequirementMatch(**match) for match in (evaluation.requirements_match if isinstance(evaluation.requirements_match, list) else [])],
        forecast=evaluation.forecast or "",
        questions=evaluation.questions or [],
        model=evaluation.model,
        created_at=evaluation.created_at
    )


@router.post("/screening/start", response_model=ScreeningOut, status_code=201)
async def start_screening_endpoint(
    data: ScreeningStartRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Start AI screening conversation"""

    if current_user.role == "manager":
        raise ForbiddenError("Менеджеры не могут запускать скрининг")

    result = await start_screening(
        session,
        candidate_id=data.candidate_id,
        application_id=data.application_id,
        script_key=data.script_key,
        company_id=current_user.company_id,
        actor_user_id=current_user.id
    )

    await session.commit()

    return ScreeningOut(
        message=result["message"],
        finished=result["finished"],
        extracted=result["extracted"]
    )


@router.post("/screening/reply", response_model=ScreeningOut, status_code=201)
async def reply_screening_endpoint(
    data: ScreeningReplyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Reply to candidate in AI screening conversation"""

    if current_user.role == "manager":
        raise ForbiddenError("Менеджеры не могут отвечать в скрининге")

    result = await reply_screening(
        session,
        candidate_id=data.candidate_id,
        message=data.message,
        company_id=current_user.company_id,
        actor_user_id=current_user.id
    )

    await session.commit()

    return ScreeningOut(
        message=result["message"],
        finished=result["finished"],
        extracted=result["extracted"]
    )