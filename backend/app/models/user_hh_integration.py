import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, TIMESTAMP, text, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class UserHhIntegration(Base, TimestampMixin, CompanyMixin):
    """Персональный OAuth-токен hh.ru конкретного рекрутёра.

    Зеркалит HhIntegration (per-company), но привязан к пользователю: интерактивные
    операции (просмотр резюме, чат, поиск) должны идти под токеном самого рекрутёра,
    чтобы суточный лимит hh (500 просмотров резюме) и атрибуция действий были ПЕРСОНАЛЬНЫМИ.
    Общий компанийный HhIntegration остаётся (фон/кроны/отклики/фолбэк, когда своего нет).

    Схема хранения токенов ЗЕРКАЛЬНАЯ HhIntegration: access_token/refresh_token — строки,
    зашифрованные Fernet (encrypt_text/decrypt_text), expires_at — момент истечения.
    UNIQUE(user_id): один персональный токен на пользователя.
    """

    __tablename__ = "user_hh_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        server_default=text("'00000000-0000-0000-0000-000000000001'"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Токены работодателя — зашифрованы Fernet (как в HhIntegration).
    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    hh_employer_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # id менеджера работодателя на hh (из /me) — идентифицирует конкретного рекрутёра.
    hh_manager_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Момент, когда ЛИЧНАЯ суточная квота просмотров резюме hh (500/сут) была замечена
    # исчерпанной. Пока дата == сегодня (UTC) — интерактивные просмотры этого рекрутёра
    # каскадом добираются из ОБЩЕГО компанийного токена, не выжигая личный впустую.
    # На следующие сутки метка «протухает» (сравнение по дате), личный токен снова первичен.
    daily_view_exhausted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    connected_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_hh_integrations_user_id"),
        Index("ix_user_hh_integrations_company_user", "company_id", "user_id"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    user: Mapped["User"] = relationship("User")
