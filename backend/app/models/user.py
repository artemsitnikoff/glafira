import uuid
from typing import Optional

from sqlalchemy import String, Boolean, ForeignKey, CheckConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class User(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "users"

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
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'recruiter'")
    )
    position: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'Europe/Moscow'")
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'ru'")
    )
    date_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'DD.MM.YYYY'")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'recruiter', 'manager')",
            name="check_user_role"
        ),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="users")
    responsible_vacancies: Mapped[list["Vacancy"]] = relationship(
        "Vacancy", back_populates="responsible_user"
    )
    managed_employees: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="manager_user", foreign_keys="Employee.manager_user_id"
    )
    recruited_employees: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="recruiter_user", foreign_keys="Employee.recruiter_user_id"
    )