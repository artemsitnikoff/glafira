"""Call модель - интеграция звонков Mango Office"""

from datetime import datetime
from uuid import UUID
from typing import Optional

from sqlalchemy import Column, String, Integer, DateTime, Text, CHAR, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.sql import text

from .base import TimestampMixin, Base


class Call(TimestampMixin, Base):
    """Звонок из Mango Office"""

    __tablename__ = "calls"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=text("gen_random_uuid()"))
    company_id = Column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    candidate_id = Column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    external_id = Column(String(255), nullable=False, comment="Идентификатор звонка в Mango Office")
    recording_id = Column(String(255), nullable=True, comment="ID записи в Mango Office")
    direction = Column(String(20), nullable=True, comment="Направление: out/in/missed")
    from_number = Column(String(50), nullable=True, comment="Номер звонящего")
    to_number = Column(String(50), nullable=True, comment="Номер получателя")
    duration_sec = Column(Integer, nullable=False, server_default=text("0"))
    started_at = Column(DateTime, nullable=True, comment="Время начала звонка")
    recruiter_name = Column(String(255), nullable=True, comment="Имя рекрутера")

    # Статус расшифровки
    transcribe_status = Column(
        String(20),
        nullable=False,
        server_default=text("'none'"),
        comment="Статус расшифровки: none/running/done/error"
    )

    # Результаты расшифровки и анализа
    transcript = Column(Text, nullable=True, comment="Полная расшифровка")
    transcript_segments = Column(JSONB, nullable=True, comment="Сегменты с таймстампами")
    summary = Column(Text, nullable=True, comment="AI-сводка звонка")
    ai_hint = Column(Text, nullable=True, comment="Совет от AI")
    ai_hint_tone = Column(
        String(10),
        nullable=True,
        comment="Тон AI-совета: warn/good"
    )
    transcribe_error = Column(Text, nullable=True, comment="Ошибка расшифровки")

    __table_args__ = (
        UniqueConstraint("company_id", "external_id", name="uq_calls_company_external"),
    )


class CallSyncJob(TimestampMixin, Base):
    """Джоб синхронизации звонков из Mango Office"""

    __tablename__ = "call_sync_jobs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=text("gen_random_uuid()"))
    company_id = Column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    status = Column(
        String(20),
        nullable=False,
        server_default=text("'running'"),
        comment="Статус: running/done/error"
    )
    total = Column(Integer, nullable=False, server_default=text("0"), comment="Всего звонков в выгрузке")
    matched = Column(Integer, nullable=False, server_default=text("0"), comment="Сопоставлено с кандидатами")
    created = Column(Integer, nullable=False, server_default=text("0"), comment="Создано записей")
    error = Column(Text, nullable=True, comment="Ошибка выполнения")
    finished_at = Column(DateTime, nullable=True, comment="Время завершения")