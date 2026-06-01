import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, TIMESTAMP, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class HhIntegration(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "hh_integrations"

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
    client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_secret: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    redirect_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    hh_employer_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    connected_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint("company_id", name="uq_hh_integrations_company_id"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    connected_by_user: Mapped[Optional["User"]] = relationship("User")


class HhOauthState(Base, TimestampMixin):
    __tablename__ = "hh_oauth_states"

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