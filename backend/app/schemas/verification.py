"""Схемы для верификации"""

from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from .base import ORMBase


class VerifyBlock(BaseModel):
    key: str  # 'contacts'|'inn'|'fssp'|'bankruptcy'|'registries'|'alimony'|'public_expertise'|'mentions'
    title: str  # человекочитаемое название блока на русском
    sources: list[dict]  # [{name, type}] — откуда взяли
    status: str  # 'clean'|'info'|'warn'|'risk'
    data: dict  # произвольная структура per-block (детали)


class VerificationOut(ORMBase):
    id: UUID
    candidate_id: UUID
    consent_id: UUID
    consent_number: str  # номер подписанного consent
    status: str  # overall: 'clean'|'info'|'warn'|'risk'
    blocks: list[VerifyBlock]  # массив, не dict
    is_mock: bool  # если true - это mock данные
    created_at: datetime