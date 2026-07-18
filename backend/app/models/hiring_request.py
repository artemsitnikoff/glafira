"""Модели модуля «Заявки на подбор».

Нанимающий менеджер подаёт заявку (из кабинета ИЛИ анонимной публичной формой),
рекрутер ведёт её по воронке заявок; из заявки создаётся вакансия (1:1); прогресс
найма считается РЕАЛЬНО из воронки связанной вакансии; при найме всех позиций заявка
закрывается автоматически.

Стадии воронки заявок хранятся СТРОКОЙ (status = stage_key), как Application.stage —
фиксированные ключи в core/request_stages.py, кастомные (между «В работе» и «В подборе»)
в таблице request_funnel_stages.
"""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    String, Text, Integer, Boolean, Date, TIMESTAMP,
    ForeignKey, CheckConstraint, UniqueConstraint, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CreatedAtMixin


class HiringRequest(Base, TimestampMixin):
    __tablename__ = "hiring_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    # Сквозной номер per-company (см. hiring_request-сервис: max+1 под unique-защитой)
    num: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    positions: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # Отсутствие deadline = «не срочно»
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    salary_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 'office' | 'hybrid' | 'remote'
    employment_format: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # 'normal' | 'high'
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'normal'"))

    # Стадия воронки заявок (stage_key). Фиксированные: new/work/sourcing/done/rejected + кастомные.
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'new'"))

    # Автор-пользователь Глафиры (нанимающий менеджер из кабинета). NULL — заявка с публичной формы.
    author_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Источник заявки: cabinet (менеджер-юзер) | form (публичная форма) | manual (рекрутер со слов)
    via: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'manual'"))
    # Внешний автор (для via=form/manual) — ТЕКСТОВЫЙ контакт для рекрутера, НЕ канал автоуведомлений.
    author_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    author_role: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    author_contact: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Связь 1:1 с вакансией. SET NULL: удаление/архив вакансии НЕ удаляет заявку.
    vacancy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancies.id", ondelete="SET NULL"), nullable=True
    )

    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    closed_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("priority IN ('normal', 'high')", name="check_request_priority"),
        CheckConstraint("via IN ('cabinet', 'form', 'manual')", name="check_request_via"),
        UniqueConstraint("company_id", "num", name="uq_request_company_num"),
        UniqueConstraint("vacancy_id", name="uq_request_vacancy"),
        Index("ix_hiring_requests_company_status", "company_id", "status"),
        Index("ix_hiring_requests_company_author", "company_id", "author_user_id"),
    )

    author_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[author_user_id])
    vacancy: Mapped[Optional["Vacancy"]] = relationship(
        "Vacancy", foreign_keys=[vacancy_id], post_update=True
    )
    comments: Mapped[list["RequestComment"]] = relationship(
        "RequestComment", back_populates="request", cascade="all, delete-orphan"
    )


class RequestComment(Base, CreatedAtMixin):
    __tablename__ = "request_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hiring_requests.id", ondelete="CASCADE"), nullable=False
    )
    # 'recruiter' | 'manager'
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    author_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("side IN ('recruiter', 'manager')", name="check_request_comment_side"),
        Index("ix_request_comments_request", "request_id", "created_at"),
    )

    request: Mapped["HiringRequest"] = relationship("HiringRequest", back_populates="comments")
    author_user: Mapped[Optional["User"]] = relationship("User")


class RequestFunnelStage(Base, CreatedAtMixin):
    """Кастомные этапы воронки заявок (вставляются МЕЖДУ «В работе» и «В подборе»).

    Фиксированные этапы (new/work/sourcing/done/rejected) — код-константы
    (core/request_stages.py), в этой таблице НЕ хранятся.
    """
    __tablename__ = "request_funnel_stages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    stage_key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "stage_key", name="uq_request_stage_company_key"),
    )


class RequestSettings(Base, TimestampMixin):
    """Настройки модуля заявок per-company (1 строка): правила-переключатели + токен формы."""
    __tablename__ = "request_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    # Автозакрытие заявки при найме всех позиций
    autoclose_on: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Вопрос в треде из «Новой» переводит заявку в «В работе»
    question_moves_to_work: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Уведомлять менеджера (email, если он пользователь Глафиры) при смене этапа
    notify_manager_on_stage: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Публичная форма: токен (перегенерация = ротация, старая ссылка мгновенно 404) + флаг активности
    form_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    form_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
