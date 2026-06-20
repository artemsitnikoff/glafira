import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, TIMESTAMP, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class HabrIntegration(Base, TimestampMixin, CompanyMixin):
    """OAuth-подключение Хабр Карьера per-company.

    client_id/client_secret — глобальные (из env, НЕ хранятся здесь);
    access_token/refresh_token — per-company (Fernet-шифрование).
    """
    __tablename__ = "habr_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        server_default=text("'00000000-0000-0000-0000-000000000001'")
    )
    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Логин Хабра — опционально, для отображения в UI статуса
    habr_login: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    connected_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint("company_id", name="uq_habr_integrations_company_id"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    connected_by_user: Mapped[Optional["User"]] = relationship("User")


class HabrOauthState(Base, TimestampMixin):
    """Временный state OAuth-флоу Хабр Карьера.

    Создаётся при GET /habr/authorize, потребляется (и удаляется) при GET /habr/callback.
    TTL 10 минут. state-строка — привязка per-company через этот объект,
    чтобы callback знал в чей аккаунт сохранить токен.
    """
    __tablename__ = "habr_oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    state: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    user: Mapped[Optional["User"]] = relationship("User")
