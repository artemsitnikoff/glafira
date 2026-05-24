import uuid
from datetime import date
from typing import Optional

from sqlalchemy import String, Integer, Boolean, ForeignKey, CheckConstraint, Date, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin, SoftDeleteMixin


class Vacancy(Base, TimestampMixin, CompanyMixin, SoftDeleteMixin):
    __tablename__ = "vacancies"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("500"))
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True
    )
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    positions_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    salary_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'RUB'"))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    archive_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    closed_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    funnel_template: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default=text("'default'")
    )
    glafira_mode: Mapped[str] = mapped_column(String(1), nullable=False, server_default=text("'A'"))
    responsible_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    external_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="check_vacancy_status"
        ),
        CheckConstraint(
            "archive_result IN ('hired', 'cancelled', 'frozen')",
            name="check_vacancy_archive_result"
        ),
        CheckConstraint(
            "funnel_template IN ('default', 'mass', 'technical', 'sales')",
            name="check_funnel_template"
        ),
        CheckConstraint(
            "glafira_mode IN ('A', 'B', 'C')",
            name="check_glafira_mode"
        ),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="vacancies")
    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="vacancies")
    responsible_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="responsible_vacancies"
    )
    team: Mapped[list["VacancyTeam"]] = relationship("VacancyTeam", back_populates="vacancy")
    stages: Mapped[list["VacancyStage"]] = relationship("VacancyStage", back_populates="vacancy")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="vacancy")


class VacancyTeam(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "vacancy_team"

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
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    is_responsible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Relationships
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="team")
    user: Mapped["User"] = relationship("User")


class VacancyStage(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "vacancy_stages"

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
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="CASCADE"),
        nullable=False
    )
    stage_key: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "stage_key IN ('response', 'selected', 'recruiter', 'interview', 'test', 'manager', 'offer', 'hired', 'rejected', 'added')",
            name="check_stage_key"
        ),
    )

    # Relationships
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="stages")