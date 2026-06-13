"""Schemas для звонков Mango Office"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CallOut(BaseModel):
    """Схема вывода информации о звонке"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: Optional[str]
    from_number: Optional[str]
    to_number: Optional[str]
    duration_sec: int
    started_at: Optional[datetime]
    has_recording: bool
    recruiter_name: Optional[str]
    transcribe_status: str
    transcript: Optional[str]
    transcript_segments: Optional[List[Dict[str, Any]]]
    summary: Optional[str]
    ai_hint: Optional[str]
    ai_hint_tone: Optional[str]
    transcribe_error: Optional[str]

    @classmethod
    def from_call(cls, call) -> "CallOut":
        """Создание схемы из модели Call"""
        return cls(
            id=call.id,
            direction=call.direction,
            from_number=call.from_number,
            to_number=call.to_number,
            duration_sec=call.duration_sec,
            started_at=call.started_at,
            has_recording=bool(call.recording_id),
            recruiter_name=call.recruiter_name,
            transcribe_status=call.transcribe_status,
            transcript=call.transcript,
            transcript_segments=call.transcript_segments,
            summary=call.summary,
            ai_hint=call.ai_hint,
            ai_hint_tone=call.ai_hint_tone,
            transcribe_error=call.transcribe_error,
        )


class CallSyncJobOut(BaseModel):
    """Схема вывода информации о джобе синхронизации"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    total: int
    matched: int
    created: int
    error: Optional[str]
    finished_at: Optional[datetime]


class CallSyncStartResponse(BaseModel):
    """Ответ при запуске синхронизации"""
    job_id: UUID
    status: str = "running"