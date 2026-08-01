"""Модели модуля «Тесты» (когнитивное тестирование кандидатов).

Два теста: «Логика» (матрицы, аналог Равена SPM, single-таймер) и «Структура
интеллекта» (аналог IST, blocked — таймер на каждый блок отдельно).

⚠️ БЕЗОПАСНОСТЬ (заложено на уровне модели):
- Правильный ответ живёт ТОЛЬКО в `TestItem.correct_option_id` — ОТДЕЛЬНОЙ колонкой,
  ФИЗИЧЕСКИ отделённой от «тела задания» (`body`) и списка вариантов (`options`).
  Ни `body`, ни `options` НЕ содержат признака правильности. Публичная схема (фаза API)
  ОБЯЗАНА сериализовать body/options и НИКОГДА `correct_option_id`.
- Матрицы хранятся ПАРАМЕТРАМИ (не готовым SVG): `body = {cells: 3×3, question_cell}`,
  `options = [{id, params}]`. Рендер ч/б SVG — на фронте; при этом ответ не утекает.
  ⚠️ В параметрах ячейки НЕТ цвета — только ч/б геометрия (shape/fill/size/count/rot/lines).

`__test__ = False` на каждом классе — чтобы pytest не пытался коллектить модели
как тест-классы (имена начинаются с `Test`).
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Boolean, TIMESTAMP,
    ForeignKey, CheckConstraint, UniqueConstraint, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Test(Base, TimestampMixin):
    """Тест-шаблон компании (справочник, засевается seed_tests)."""
    __tablename__ = "tests"
    __test__ = False  # не коллектить pytest'ом

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    # 'logic' | 'intelligence' (ключ теста, без CHECK — новые тесты в будущем)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # 'single' — один общий таймер на весь тест; 'blocked' — таймер на каждый блок
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Для 'single': длительность всего теста, сек. Для 'blocked' — None (таймеры в блоках).
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    randomize_options: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # Возврат внутри блока/теста (к предыдущему заданию). Для «Логики» — False.
    allow_back: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Настраиваемые пороги категорий (список бэндов {min,max,key,label,marker}). None — нет категорий.
    category_thresholds: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Порог авто-отказа по сырому баллу (None — не отклонять автоматически).
    auto_reject_below: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 'active' | 'draft'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )

    __table_args__ = (
        CheckConstraint("kind IN ('single', 'blocked')", name="check_test_kind"),
        CheckConstraint("status IN ('active', 'draft')", name="check_test_status"),
        UniqueConstraint("company_id", "key", name="uq_test_company_key"),
        Index("ix_tests_company", "company_id"),
    )

    blocks: Mapped[list["TestBlock"]] = relationship(
        "TestBlock", back_populates="test", cascade="all, delete-orphan"
    )
    items: Mapped[list["TestItem"]] = relationship(
        "TestItem", back_populates="test", cascade="all, delete-orphan"
    )


class TestBlock(Base, TimestampMixin):
    """Блок теста 'blocked' (для «Структуры интеллекта»: 4 блока со своими таймерами)."""
    __tablename__ = "test_blocks"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Таймер блока, сек.
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("test_id", "key", name="uq_test_block_key"),
        Index("ix_test_blocks_company", "company_id"),
        Index("ix_test_blocks_test", "test_id"),
    )

    test: Mapped["Test"] = relationship("Test", back_populates="blocks")
    items: Mapped[list["TestItem"]] = relationship(
        "TestItem", back_populates="block", cascade="all, delete-orphan"
    )


class TestItem(Base, TimestampMixin):
    """Задание теста. ⚠️ correct_option_id — ОТДЕЛЬНАЯ server-only колонка.

    НЕ сериализовать `correct_option_id` в публичную схему. `body` и `options` признака
    правильности НЕ содержат.
    """
    __tablename__ = "test_items"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    # nullable — для 'single'-теста «Логика» задания вне блоков.
    block_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_blocks.id", ondelete="CASCADE"), nullable=True
    )
    # 'matrix' (параметрическая матрица) | 'text' (вербальное задание)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # Тело задания БЕЗ признака правильности.
    #   matrix: {cells: 3×3 из {shape,fill,size,count,rot,lines}, question_cell:[r,c]}
    #   text:   {kind, prompt, terms:[...] | {a,b,c}}
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Список вариантов БЕЗ признака верности: [{id, params:{...}}] | [{id, text}].
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    # ⚠️ SERVER-ONLY: id верного варианта. НИКОГДА не отдавать в публичную схему.
    correct_option_id: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('matrix', 'text')", name="check_test_item_kind"),
        Index("ix_test_items_company", "company_id"),
        Index("ix_test_items_test", "test_id", "order_index"),
        Index("ix_test_items_block", "block_id"),
    )

    test: Mapped["Test"] = relationship("Test", back_populates="items")
    block: Mapped[Optional["TestBlock"]] = relationship("TestBlock", back_populates="items")


class TestAssignment(Base, TimestampMixin):
    """Назначение теста кандидату (привязано к Application). token заполнит фаза API."""
    __tablename__ = "test_assignments"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    # Публичный токен ссылки прохождения (заполняет фаза API). Несколько NULL допустимы.
    token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # 'sent' | 'started' | 'completed' | 'expired' | 'cancelled'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'sent'")
    )
    channel: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('sent', 'started', 'completed', 'expired', 'cancelled')",
            name="check_test_assignment_status",
        ),
        UniqueConstraint("token", name="uq_test_assignment_token"),
        Index("ix_test_assignments_company", "company_id"),
        Index("ix_test_assignments_application", "application_id"),
    )


class TestAttempt(Base, TimestampMixin):
    """Прохождение теста (серверные таймеры, консент, воспроизводимая рандомизация)."""
    __tablename__ = "test_attempts"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_assignments.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    # Серверный таймер всего теста (для 'single').
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # 152-ФЗ: согласие на прохождение (время + IP).
    consent_agreed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    consent_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    current_block_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_blocks.id", ondelete="SET NULL"), nullable=True
    )
    current_item_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Серверный таймер текущего блока (для 'blocked').
    block_started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Seed рандомизации порядка вариантов — воспроизводимость выдачи.
    options_seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'in_progress'")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'abandoned', 'expired')",
            name="check_test_attempt_status",
        ),
        Index("ix_test_attempts_company", "company_id"),
        Index("ix_test_attempts_assignment", "assignment_id"),
        Index("ix_test_attempts_application", "application_id"),
    )


class TestAnswer(Base):
    """Ответ на задание. is_correct считает СЕРВЕР (сверяя с TestItem.correct_option_id)."""
    __tablename__ = "test_answers"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_items.id", ondelete="CASCADE"), nullable=False
    )
    # None — пропущено (таймаут / не отвечено).
    chosen_option_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("attempt_id", "item_id", name="uq_test_answer_attempt_item"),
        Index("ix_test_answers_company", "company_id"),
        Index("ix_test_answers_attempt", "attempt_id"),
    )


class TestResult(Base):
    """Денормализованный итог теста (для карточки/воронки). Привязан к Application."""
    __tablename__ = "test_results"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL: денормализованный итог переживает удаление назначения.
    assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_assignments.id", ondelete="SET NULL"), nullable=True
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    raw_score: Mapped[int] = mapped_column(Integer, nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    block_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # None — база компании < 30 прохождений (перцентиль скрыт).
    percentile: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Список кодов флагов достоверности.
    validity_flags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_test_results_company", "company_id"),
        Index("ix_test_results_application", "application_id"),
        Index("ix_test_results_assignment", "assignment_id"),
    )
