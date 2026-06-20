import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, ForeignKey, CheckConstraint, Date, Text, text, UniqueConstraint, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, CompanyMixin, SoftDeleteMixin


class Candidate(Base, TimestampMixin, CompanyMixin, SoftDeleteMixin):
    __tablename__ = "candidates"

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
    display_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    middle_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    salary_expectation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'RUB'"))
    last_position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_period: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    preferred_channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'telegram'")
    )
    resume_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resume_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    messengers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    duplicate_of: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="SET NULL"),
        nullable=True
    )
    is_anonymized: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    external_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Ссылка на резюме/профиль кандидата у источника (страница резюме на hh.ru и т.п.).
    # Заполняется вручную в форме ИЛИ автоматически при импорте с hh (alternate_url).
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Момент первого платного открытия контактов Хабра (per-company, списывает лимит).
    # NULL = контакты не открыты; NOT NULL = открыты, повторный вызов не тратит лимит.
    habr_contacts_opened_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "gender IN ('male', 'female')",
            name="check_candidate_gender"
        ),
        CheckConstraint(
            "source IN ('hh', 'avito', 'superjob', 'telegram', 'referral', 'direct', 'agency', 'import', 'manual', 'linkedin', 'potok', 'smart', 'habr', 'other')",
            name="check_candidate_source"
        ),
        CheckConstraint(
            "preferred_channel IN ('telegram', 'email', 'phone')",
            name="check_preferred_channel"
        ),
    )

    @property
    def full_name(self) -> str:
        """Get full name of candidate"""
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="candidates")
    duplicate_of_candidate: Mapped[Optional["Candidate"]] = relationship(
        "Candidate", remote_side="Candidate.id"
    )
    experience: Mapped[list["CandidateExperience"]] = relationship(
        "CandidateExperience", back_populates="candidate"
    )
    skills: Mapped[list["CandidateSkill"]] = relationship(
        "CandidateSkill", back_populates="candidate"
    )
    education: Mapped[list["CandidateEducation"]] = relationship(
        "CandidateEducation", back_populates="candidate"
    )
    tags: Mapped[list["CandidateTag"]] = relationship(
        "CandidateTag", back_populates="candidate"
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="candidate"
    )


class CandidateExperience(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "candidate_experience"

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
    position: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    period: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="experience")


class CandidateSkill(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "candidate_skills"

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
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="skills")


class CandidateEducation(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "candidate_education"

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
    institution: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    specialty: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    years: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="education")


class Tag(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "tags"

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
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    # Relationships
    candidate_tags: Mapped[list["CandidateTag"]] = relationship(
        "CandidateTag", back_populates="tag"
    )


class CandidateTag(Base, TimestampMixin, CompanyMixin):
    __tablename__ = "candidate_tags"

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
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint('candidate_id', 'tag_id', name='uq_candidate_tag'),
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="candidate_tags")