import uuid
from typing import Optional

from sqlalchemy import String, Integer, Boolean, ForeignKey, CheckConstraint, Text, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin


class RejectReason(Base, CompanyMixin):
    __tablename__ = "reject_reasons"

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
    # NULL = дефолт компании (шаблон из Настроек). Заполнен = причина, привязанная к вакансии
    # (копия дефолтов на момент создания, далее правится независимо). CASCADE с вакансией.
    vacancy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="CASCADE"),
        nullable=True,
    )
    side: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Системная причина — нельзя удалить (гарантия непустоты: ≥1 на каждую сторону).
    # Переименовать можно. По одной системной на side ('company' / 'candidate').
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "side IN ('candidate', 'company')",
            name="check_reject_reason_side"
        ),
    )


class EmailTemplate(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "email_templates"

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
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class SurveyTemplate(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "survey_templates"

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
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    channels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    questions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class GlafiraSettings(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "glafira_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        server_default=text("'00000000-0000-0000-0000-000000000001'")
    )
    tone: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'friendly'"))
    use_informal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    emoji_level: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'moderate'"))
    auto_reject_below: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    auto_select_above: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("80"))
    days_no_response: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("7"))
    stop_words: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    default_mode: Mapped[str] = mapped_column(String(1), nullable=False, server_default=text("'A'"))
    # Источник данных о текучке: 'none' (не подключён) | 'bitrix24' (импорт сотрудников из Б24).
    turnover_source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'none'"))
    # Текст отказа по умолчанию для компании
    default_rejection_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Верх (приветствие) и низ (подпись) письма-оффера — обрамляют тело оффера,
    # которое генерит Глафира. Обычный текст, БЕЗ плейсхолдеров. NULL/пусто → дефолт из кода.
    offer_email_header: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    offer_email_footer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # LLM-модель для оценки резюме (NULL = fallback на env GLAFIRA_MODEL)
    llm_model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    # API-ключ OpenRouter для компании (зашифрованный Fernet)
    openrouter_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "tone IN ('friendly', 'formal', 'business')",
            name="check_glafira_tone"
        ),
        CheckConstraint(
            "default_mode IN ('A', 'B', 'C')",
            name="check_glafira_default_mode"
        ),
        CheckConstraint(
            "turnover_source IN ('none', 'bitrix24')",
            name="check_glafira_turnover_source"
        ),
    )


class Integration(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "integrations"

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
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'disconnected'"))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('connected', 'disconnected')",
            name="check_integration_status"
        ),
    )


class FunnelTemplate(Base, CompanyMixin):
    """Именованный шаблон воронки (пресет) для формы создания вакансии.

    «По умолчанию» — НЕ здесь: это company_default_stages (отдельная воронка по умолчанию).
    Здесь — дополнительные пресеты (Массовый/Технический/Продажи и любые свои).
    Этапы шаблона — в funnel_template_stages.
    """
    __tablename__ = "funnel_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        server_default=text("'00000000-0000-0000-0000-000000000001'")
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class FunnelTemplateStage(Base):
    """Этап именованного шаблона воронки (см. FunnelTemplate)."""
    __tablename__ = "funnel_template_stages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("funnel_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_key: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class MessageTemplate(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "message_templates"

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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class CompanyDefaultStage(Base, CompanyMixin):
    __tablename__ = "company_default_stages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        server_default=text("'00000000-0000-0000-0000-000000000001'")
    )
    stage_key: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)