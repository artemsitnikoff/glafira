import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, CheckConstraint, UniqueConstraint, Date, TIMESTAMP, Boolean, Numeric, text, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin, CreatedAtMixin


class Employee(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "employees"

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
    # nullable=True: сотрудники, импортированные из внешних систем (Б24), не имеют
    # ATS-кандидата. Инвариант «Employee из hire всегда с candidate» осознанно ослаблен —
    # действует только для наймов внутри ATS (create_employee_from_hire всегда ставит candidate_id).
    candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="RESTRICT"),
        nullable=True
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True
    )
    # Внешний источник сотрудника: NULL = создан внутри ATS (найм); 'bitrix24' = импортирован из Б24.
    external_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # ID сотрудника в внешней системе (Б24 user ID) — для идемпотентного upsert при импорте.
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    manager_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    recruiter_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    hire_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    probation_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'onboarding'"))
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'low'"))
    enps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    left_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    left_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb")
    )
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_summary_generated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('onboarding', 'passed', 'left')",
            name="check_employee_status"
        ),
        CheckConstraint(
            "risk_level IN ('low', 'mid', 'high')",
            name="check_employee_risk_level"
        ),
        CheckConstraint(
            "enps >= -100 AND enps <= 100",
            name="check_employee_enps"
        ),
        # DB-бэкстоп к app-level идемпотентности найма (SELECT-then-INSERT в
        # create_employee_from_hire) против гонки двойного найма из одной заявки.
        UniqueConstraint("application_id", name="uq_employees_application_id"),
        # Идемпотентность импорта из внешних систем: один внешний юзер = один Employee.
        # В Postgres NULL не конфликтует в UNIQUE, поэтому ATS-наймы (external_*=NULL)
        # дубли не образуют — ограничение работает только для импортированных строк.
        UniqueConstraint(
            "company_id", "external_source", "external_id", name="uq_employee_external"
        ),
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate")
    application: Mapped[Optional["Application"]] = relationship("Application")
    manager_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="managed_employees", foreign_keys=[manager_user_id]
    )
    recruiter_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="recruited_employees", foreign_keys=[recruiter_user_id]
    )
    surveys: Mapped[list["PulseSurvey"]] = relationship(
        "PulseSurvey", back_populates="employee"
    )
    plan_items: Mapped[list["PulsePlanItem"]] = relationship(
        "PulsePlanItem", back_populates="employee"
    )
    alerts: Mapped[list["PulseAlert"]] = relationship(
        "PulseAlert", back_populates="employee"
    )


class PulseSurvey(Base, CreatedAtMixin):
    __tablename__ = "pulse_surveys"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )
    template_key: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    answered_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Numeric(3,1) в SQLAlchemy/PG возвращает Decimal — аннотация Decimal, не float
    # (сериализация делает float() явно). См. _compute_overall_score.
    overall_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 1), nullable=True)
    # Список ответов: [{id, text, scale, kind, answer}] (см. submit_public_survey).
    # SurveyOut.answers тоже list — держим один формат (seed_demo тоже пишет list).
    answers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Секретный токен публичной ссылки (в URL-хеше у фронта). По нему публичный
    # эндпоинт без авторизации находит опрос. UNIQUE, nullable (старые опросы без него).
    public_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    # Снапшот вопросов на момент запуска: [{id, text, kind, optional, scale}].
    # Публичная страница рендерит именно их; правки шаблона их не меняют.
    questions: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "type IN ('weekly', 'monthly', 'special', 'enps')",
            name="check_pulse_survey_type"
        ),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="surveys")


class PulsePlanItem(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "pulse_plan_items"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    deadline_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    responsible: Mapped[str] = mapped_column(String(20), nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    done_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "phase IN ('welcome', 'month1', 'month2', 'month3')",
            name="check_pulse_plan_phase"
        ),
        CheckConstraint(
            "responsible IN ('hr', 'manager', 'employee')",
            name="check_pulse_plan_responsible"
        ),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="plan_items")


class PulseAlert(Base, CreatedAtMixin, CompanyMixin):
    __tablename__ = "pulse_alerts"

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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "level IN ('high', 'mid', 'info')",
            name="check_pulse_alert_level"
        ),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="alerts")