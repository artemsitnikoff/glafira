"""Схемы для верификации"""

from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from .base import ORMBase


class VerificationBlock(BaseModel):
    status: str  # clean|info|warn|risk
    summary: str
    details: dict


class VerificationOut(ORMBase):
    id: UUID
    candidate_id: UUID
    consent_id: UUID
    checked_at: datetime
    status: str  # clean|info|warn|risk
    blocks: dict  # 7 ключей: inn, fssp, bankruptcy, registries, public, ai_intel, alimony