"""Парсинг резюме и автозаполнение полей кандидата"""

import logging
import re
from io import BytesIO
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .client import call_json
from .prompts import RESUME_PARSE_PROMPT
from ...models import Candidate

logger = logging.getLogger(__name__)


def _to_int(value) -> int | None:
    """Безопасно привести ответ LLM к int. LLM по промпту возвращает зарплату строкой
    ('180 000 ₽ на руки'), а колонка — INTEGER. Берём первое число, чистим разделители."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        n = value
    elif isinstance(value, float):
        n = int(value)
    elif isinstance(value, str):
        m = re.search(r'\d[\d\s]*\d|\d', value)
        if not m:
            return None
        try:
            n = int(re.sub(r'\s', '', m.group()))
        except ValueError:
            return None
    else:
        return None
    # Санити: отрицательные/абсурдные отбросить (PG INTEGER до ~2.1 млрд)
    if n < 0 or n > 1_000_000_000:
        return None
    return n


def _to_str(value, maxlen: int) -> str | None:
    """Привести к строке нужной длины (обрезать под лимит колонки), пустое/None — в None."""
    if value is None:
        return None
    s = str(value).strip()
    return s[:maxlen] if s else None


async def extract_resume_text(content: bytes, filename: str) -> str | None:
    """Extract text content from resume file"""
    file_ext = Path(filename).suffix.lower()

    if file_ext in {'.txt', '.md'}:
        try:
            return content.decode('utf-8', errors='ignore')
        except Exception:
            return None

    elif file_ext == '.pdf':
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts) if text_parts else None
        except Exception as e:
            logger.warning(f"Failed to extract PDF text: {e}")
            return None

    elif file_ext in {'.doc', '.docx'}:
        # TODO: Future implementation for Word documents
        return None

    return None


async def parse_and_apply_resume(
    session: AsyncSession,
    *,
    candidate_id: UUID,
    content: bytes,
    filename: str,
    company_id: UUID
) -> None:
    """Parse resume and update candidate fields"""
    # Extract text from file
    text = await extract_resume_text(content, filename)
    if not text:
        logger.info(f"No text extracted from {filename}")
        return

    # Get candidate
    result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        logger.warning(f"Candidate {candidate_id} not found")
        return

    # Update resume_text if it was None
    if candidate.resume_text is None:
        candidate.resume_text = text

    try:
        # Call Claude to parse structured data
        parsed_data = await call_json(
            system=RESUME_PARSE_PROMPT,
            user=text,
            max_tokens=1024
        )

        # Заполняем только пустые поля. Значения парсера КОЭРСИМ к типу/длине колонки
        # (LLM возвращает зарплату строкой → INTEGER; телефон/строки могут превысить лимит
        # колонки) — иначе flush падает DataError и отравляет сессию, роняя всю загрузку файла.
        if candidate.last_position is None:
            if (v := _to_str(parsed_data.get("last_position"), 255)):
                candidate.last_position = v

        if candidate.last_company is None:
            if (v := _to_str(parsed_data.get("last_company"), 255)):
                candidate.last_company = v

        if candidate.last_period is None:
            if (v := _to_str(parsed_data.get("last_period"), 120)):
                candidate.last_period = v

        if candidate.salary_expectation is None:
            if (v := _to_int(parsed_data.get("salary_expectation"))) is not None:
                candidate.salary_expectation = v

        if candidate.city is None:
            if (v := _to_str(parsed_data.get("city"), 120)):
                candidate.city = v

        if candidate.phone is None:
            if (v := _to_str(parsed_data.get("phone"), 20)):
                candidate.phone = v

        if candidate.email is None:
            if (v := _to_str(parsed_data.get("email"), 255)):
                candidate.email = v

        if hasattr(candidate, 'experience_years') and candidate.experience_years is None:
            if (v := _to_int(parsed_data.get("experience_years"))) is not None:
                candidate.experience_years = v

        await session.flush()
        logger.info(f"Updated candidate {candidate_id} from parsed resume")

    except Exception as e:
        logger.warning(f"Resume parsing failed for {filename}: {e}")
        # Don't raise - we don't want to block file upload
        return