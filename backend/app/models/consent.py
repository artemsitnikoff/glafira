import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, CheckConstraint, TIMESTAMP, UniqueConstraint, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class Consent(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "consents"

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
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    channel: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    signed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    requested_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Онлайн-подписание согласия кандидатом. token — секрет публичной ссылки
    # /consent/{token} (nullable: старые записи и «ПдН подписан» рекрутёром токена не имеют).
    token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # IP клиента в момент подписания (X-Forwarded-For) — доказательство согласия 152-ФЗ.
    signed_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Кто подписал: 'candidate' (онлайн-страница) | 'recruiter' («ПдН подписан»).
    signed_by: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Снимок текста согласия, который подписал кандидат (152-ФЗ: хранить именно то,
    # с чем человек согласился, а не текущий шаблон, который мог измениться).
    consent_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'signed', 'revoked')",
            name="check_consent_status",
        ),
        UniqueConstraint("company_id", "number", name="uq_consents_company_number"),
        # Токен уникален глобально (по нему публичный роут находит компанию) — но partial,
        # т.к. записи без онлайн-ссылки (token IS NULL) не должны конфликтовать между собой.
        Index(
            "uq_consents_token",
            "token",
            unique=True,
            postgresql_where=text("token IS NOT NULL"),
        ),
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate")
    verifications: Mapped[list["Verification"]] = relationship(
        "Verification", back_populates="consent"
    )