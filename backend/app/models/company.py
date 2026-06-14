import uuid
from datetime import date
from sqlalchemy import String, Date, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    paid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationships (forward references will be resolved after all models are loaded)
    users: Mapped[list["User"]] = relationship("User", back_populates="company", lazy="select")
    clients: Mapped[list["Client"]] = relationship("Client", back_populates="company", lazy="select")
    vacancies: Mapped[list["Vacancy"]] = relationship("Vacancy", back_populates="company", lazy="select")
    candidates: Mapped[list["Candidate"]] = relationship("Candidate", back_populates="company", lazy="select")