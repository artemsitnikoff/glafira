import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, TIMESTAMP, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class TalantixIntegration(Base, TimestampMixin, CompanyMixin):
    """Подключение ATS Talantix (talantix.ru) per-company.

    Пользователь получает из ЛК Talantix пару токенов (access_token + refresh_token,
    в json). Оба хранятся зашифрованными Fernet. access_token живёт ~24ч; при
    истечении (или 401) обменивается через POST /oauth/token на НОВУЮ пару —
    refresh_token ОДНОРАЗОВЫЙ (ротируется), новый обязательно персистится обратно,
    иначе следующий refresh упадёт. Токены НИКОГДА не возвращаются наружу/в логи.
    """
    __tablename__ = "talantix_integrations"

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
    # Токены Talantix — Fernet-шифрование (write-only, наружу не отдаются)
    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    connected_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint("company_id", name="uq_talantix_integrations_company_id"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    connected_by_user: Mapped[Optional["User"]] = relationship("User")
