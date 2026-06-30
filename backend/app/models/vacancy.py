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
    recruiter_scoring_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    hh_vacancy_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    habr_vacancy_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    avito_vacancy_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Automation fields
    auto_move: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    auto_move_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("80"))
    # Целевой этап автоперевода по скорингу. NULL → дефолт 'selected' (обратная
    # совместимость). Должен быть НЕ защищённым этапом (не начальный/терминальный)
    # этой вакансии; валидируется при переводе (фолбэк на 'selected', иначе не двигаем).
    auto_move_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    auto_qa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # П.2 — настраиваемые этапы уточняющих вопросов: источник (на каком этапе задаём,
    # NULL→'response') и цель (куда переводим по ответам, NULL→'selected'). Источник —
    # любой НЕ терминальный этап; цель валидируется как у auto_move_stage (не защищённый/
    # не терминальный) при переводе.
    auto_qa_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    auto_qa_target_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Развилка вопросов П.2: 'weak' (NULL→) = по слабым сторонам резюме (LLM-вопросы из
    # скоринга, AiEvaluation.questions); 'fixed' = определённые статические вопросы из
    # auto_qa_fixed_text (рекрутёр пишет сам / вставляет из шаблона сообщений), всегда одни и те же.
    auto_qa_mode: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    auto_qa_fixed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auto_reject: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Слать ли кандидату вежливое сообщение при переводе в отказ (поднимает «вежливость» на hh).
    # Гейтит отправку в sync_company_rejections; discard на hh идёт независимо от флага.
    auto_reject_message: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    rejection_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    smart_search_runs: Mapped[list["SmartSearchRun"]] = relationship("SmartSearchRun", back_populates="vacancy")


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
    # Инструкции/контекст этапа для команды (что делать на этапе, чек-лист и т.п.)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Constraints removed to allow custom stage keys

    # Relationships
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="stages")