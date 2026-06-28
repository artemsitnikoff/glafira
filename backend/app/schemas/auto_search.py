from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AutoSearchBasis(BaseModel):
    kind: Literal["vacancy", "prompt"]
    vacancy_id: Optional[UUID] = None
    prompt: Optional[str] = None


class AutoSearchItem(BaseModel):
    id: UUID
    hh_saved_search_id: str
    name: str
    region: Optional[str] = None
    subscribed: bool
    auto_eval: bool
    total: Optional[int] = None
    new_count: Optional[int] = None
    basis: Optional[AutoSearchBasis] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AutoSearchCandidate(BaseModel):
    hh_resume_id: str
    title: Optional[str] = None
    age: Optional[int] = None
    city: Optional[str] = None
    anonymous: bool = False
    salary: Optional[int] = None
    experience: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    last_job: Optional[str] = None
    updated_at: Optional[str] = None
    is_new: bool = False
    score: Optional[int] = None
    taken: bool = False


class AutoCandidatesResponse(BaseModel):
    items: list[AutoSearchCandidate]
    total: int
    page: int
    pages: int
    per_page: int


class AutoBasisRequest(BaseModel):
    kind: Literal["vacancy", "prompt"]
    vacancy_id: Optional[UUID] = None
    prompt: Optional[str] = None

    @model_validator(mode="after")
    def validate_fields(self) -> "AutoBasisRequest":
        if self.kind == "vacancy" and not self.vacancy_id:
            raise ValueError("vacancy_id required when kind='vacancy'")
        if self.kind == "prompt" and (
            not self.prompt or len(self.prompt.strip()) < 3
        ):
            raise ValueError("prompt must be at least 3 characters when kind='prompt'")
        return self


class AutoEvaluateRequest(BaseModel):
    segment: Literal["all", "new"] = "all"
    n: Optional[int] = None


class AutoTakeRequest(BaseModel):
    resume_ids: list[str]
    target: Literal["pool", "vacancy"] = "pool"
    vacancy_id: Optional[UUID] = None


class AutoAccessResponse(BaseModel):
    has_access: bool
    has_paid_access: bool
    reason: Optional[str] = None
    pool_left: Optional[int] = None
