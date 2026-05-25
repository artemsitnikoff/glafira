"""Glafira AI API endpoints"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...deps import get_current_user, get_db
from ...core.errors import NotFoundError
from ...models import User, AiEvaluation
from ...schemas.glafira import (
    ScoreRequest,
    EvaluationOut,
    ScreeningStartRequest,
    ScreeningReplyRequest,
    ScreeningOut
)
from ...services.glafira.scoring import score_candidate
from ...services.glafira.screening import start_screening, reply_screening

router = APIRouter()
# Separate router for /candidates/{id}/evaluation — mounted without /glafira prefix per TZ-2 §6.1.
candidates_evaluation_router = APIRouter()


@router.post("/score", response_model=EvaluationOut, status_code=201)
async def score_candidate_endpoint(
    data: ScoreRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Score candidate for vacancy using Glafira AI"""

    # Check if evaluation already exists
    existing_result = await session.execute(
        select(AiEvaluation).where(
            AiEvaluation.candidate_id == data.candidate_id,
            AiEvaluation.application_id.is_not(None)
        ).order_by(AiEvaluation.created_at.desc()).limit(1)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # Return existing evaluation with 200 status
        return EvaluationOut(
            id=existing.id,
            candidate_id=existing.candidate_id,
            application_id=existing.application_id,
            score=existing.score,
            verdict=existing.verdict,
            summary=existing.summary,
            strengths=existing.strengths,
            risks=existing.risks,
            requirements_match=existing.requirements_match,
            forecast=existing.forecast,
            model=existing.model,
            created_at=existing.created_at
        )

    # Create new evaluation
    evaluation = await score_candidate(
        session,
        candidate_id=data.candidate_id,
        vacancy_id=data.vacancy_id,
        company_id=current_user.company_id,
        actor_user_id=current_user.id
    )

    await session.commit()

    return EvaluationOut(
        id=evaluation.id,
        candidate_id=evaluation.candidate_id,
        application_id=evaluation.application_id,
        score=evaluation.score,
        verdict=evaluation.verdict,
        summary=evaluation.summary,
        strengths=evaluation.strengths,
        risks=evaluation.risks,
        requirements_match=evaluation.requirements_match,
        forecast=evaluation.forecast,
        model=evaluation.model,
        created_at=evaluation.created_at
    )


@candidates_evaluation_router.get("/candidates/{candidate_id}/evaluation", response_model=EvaluationOut)
async def get_candidate_evaluation(
    candidate_id: UUID,
    application_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get latest evaluation for candidate"""

    if application_id:
        # Get evaluation for specific application
        result = await session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == candidate_id,
                AiEvaluation.application_id == application_id,
                AiEvaluation.company_id == current_user.company_id
            ).order_by(AiEvaluation.created_at.desc()).limit(1)
        )
    else:
        # Get latest evaluation for candidate
        result = await session.execute(
            select(AiEvaluation).where(
                AiEvaluation.candidate_id == candidate_id,
                AiEvaluation.company_id == current_user.company_id
            ).order_by(AiEvaluation.created_at.desc()).limit(1)
        )

    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise NotFoundError("Оценка")

    return EvaluationOut(
        id=evaluation.id,
        candidate_id=evaluation.candidate_id,
        application_id=evaluation.application_id,
        score=evaluation.score,
        verdict=evaluation.verdict,
        summary=evaluation.summary,
        strengths=evaluation.strengths,
        risks=evaluation.risks,
        requirements_match=evaluation.requirements_match,
        forecast=evaluation.forecast,
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

    message = await start_screening(
        session,
        application_id=data.application_id,
        company_id=current_user.company_id,
        actor_user_id=current_user.id
    )

    await session.commit()

    return ScreeningOut(
        ai_message_id=message.id,
        body=message.body
    )


@router.post("/screening/reply", response_model=ScreeningOut, status_code=201)
async def reply_screening_endpoint(
    data: ScreeningReplyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Reply to candidate in AI screening conversation"""

    message = await reply_screening(
        session,
        application_id=data.application_id,
        candidate_message=data.body,
        company_id=current_user.company_id,
        actor_user_id=current_user.id
    )

    await session.commit()

    return ScreeningOut(
        ai_message_id=message.id,
        body=message.body
    )