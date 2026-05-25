"""Схемы для Glafira API"""

from uuid import UUID
from pydantic import BaseModel

from .base import ORMBase


class ScoreRequest(BaseModel):
    candidate_id: UUID
    vacancy_id: UUID


class RequirementMatch(BaseModel):
    req: str
    status: str  # pass|warn|fail
    comment: str


class EvaluationOut(ORMBase):
    id: UUID
    candidate_id: UUID
    application_id: UUID | None
    score: int
    verdict: str  # good|partial|bad
    summary: str
    strengths: list[str]
    risks: list[str]
    requirements_match: dict
    forecast: str | None
    model: str | None


class ScreeningStartRequest(BaseModel):
    application_id: UUID


class ScreeningReplyRequest(BaseModel):
    application_id: UUID
    body: str


class ScreeningOut(BaseModel):
    ai_message_id: UUID
    body: str