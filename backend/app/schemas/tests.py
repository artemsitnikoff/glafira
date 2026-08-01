"""Рекрутёрские (приватные, authenticated) схемы модуля «Тесты».

⚠️ Это НЕ публичные схемы. Здесь рекрутёру МОЖНО показывать верность ответов
(is_correct) и ссылку прохождения — это авторизованный сотрудник. Публичные схемы
(schemas/public_test.py) остаются server-only по correct_option_id/is_correct.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TestAssignRequest(BaseModel):
    test_id: UUID
    ttl_days: int = Field(default=7, ge=1, le=90)
    # None → канал подбирается автоматически по контактам кандидата. Невалидное → 422.
    channel: Optional[Literal["email", "telegram", "hh"]] = None
    message: Optional[str] = None


class TestAnswerRow(BaseModel):
    index: int                 # order_index задания
    item_id: UUID
    item_kind: str             # 'matrix' | 'text' (item.kind)
    body: dict                 # тело задания (item.body): matrix {cells, question_cell} / text {kind, terms, prompt}
    chosen_option_id: str | None
    # Содержимое ВЫБРАННОГО кандидатом варианта {"params": .., "text": ..}; None — ответа не было / вариант не найден.
    chosen: Optional[dict] = None
    # Содержимое ПРАВИЛЬНОГО варианта {"params": .., "text": ..}. ⚠️ Приватный эндпоинт — рекрутёру можно.
    correct: dict
    is_correct: bool           # рекрутёру верность показывать МОЖНО
    time_ms: int | None


class TestResultOut(BaseModel):
    raw_score: int
    max_score: int
    block_scores: dict
    category: str | None
    category_label: str | None = None   # из test.category_thresholds по key
    percentile: int | None              # None если база компании < 30
    validity_flags: list
    validity_messages: list[str] = Field(default_factory=list)  # из tests_scoring.FLAG_MESSAGES
    duration_sec: int | None
    completed_at: datetime
    answers: list[TestAnswerRow] = Field(default_factory=list)


class TestAssignmentOut(BaseModel):
    id: UUID
    test_id: UUID
    test_name: str
    test_kind: str
    status: str
    channel: str | None
    url: str | None              # {FRONTEND_BASE_URL}/test/{token} — рекрутёру можно
    expires_at: datetime | None
    created_at: datetime
    result: Optional[TestResultOut] = None


class TestListItem(BaseModel):
    id: UUID
    key: str
    name: str
    kind: str
    status: str
    item_count: int
    assigned_count: int


class TestBlockDetail(BaseModel):
    id: UUID
    key: str
    title: str
    order_index: int
    duration_sec: int
    item_count: int


class TestDetail(BaseModel):
    id: UUID
    key: str
    name: str
    kind: str
    duration_sec: int | None
    randomize_options: bool
    allow_back: bool
    category_thresholds: list | None
    auto_reject_below: int | None
    status: str
    item_count: int
    assigned_count: int
    blocks: list[TestBlockDetail] = Field(default_factory=list)


class TestBlockDurationUpdate(BaseModel):
    id: UUID
    duration_sec: int = Field(ge=1)


class TestUpdate(BaseModel):
    category_thresholds: list | None = None
    auto_reject_below: int | None = None
    randomize_options: bool | None = None
    allow_back: bool | None = None
    status: Optional[Literal["active", "draft"]] = None
    blocks: Optional[list[TestBlockDurationUpdate]] = None
