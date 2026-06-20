import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, TIMESTAMP, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class AvitoIntegration(Base, TimestampMixin, CompanyMixin):
    """OAuth client_credentials-подключение Авито Работа per-company.

    В отличие от Хабра (глобальный client_id) — у каждого арендатора свой
    Авито client_id/secret (хранятся зашифрованными Fernet per-company).
    access_token/expires_at: кэш client_credentials токена — рефрешится
    автоматически при истечении, не требует браузерного флоу.
    avito_user_id: опциональный идентификатор для заголовка X-Employee-Of.
    """
    __tablename__ = "avito_integrations"

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
    # Авито client_id/secret — per-company, Fernet-шифрование
    client_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    client_secret: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Кэш client_credentials токена (рефрешится автоматически)
    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Опциональный user_id для заголовка X-Employee-Of (нужен только для мультиаккаунтов)
    avito_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    connected_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint("company_id", name="uq_avito_integrations_company_id"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    connected_by_user: Mapped[Optional["User"]] = relationship("User")
