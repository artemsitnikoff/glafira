"""Парсинг резюме и автозаполнение полей кандидата"""

import logging
from io import BytesIO
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .client import call_json
from .prompts import RESUME_PARSE_PROMPT
from ...models import Candidate

logger = logging.getLogger(__name__)


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

        # Update candidate fields only if they are None
        if candidate.last_position is None and parsed_data.get("last_position"):
            candidate.last_position = parsed_data["last_position"]

        if candidate.last_company is None and parsed_data.get("last_company"):
            candidate.last_company = parsed_data["last_company"]

        if candidate.last_period is None and parsed_data.get("last_period"):
            candidate.last_period = parsed_data["last_period"]

        if candidate.salary_expectation is None and parsed_data.get("salary_expectation"):
            candidate.salary_expectation = parsed_data["salary_expectation"]

        if candidate.city is None and parsed_data.get("city"):
            candidate.city = parsed_data["city"]

        if candidate.phone is None and parsed_data.get("phone"):
            candidate.phone = parsed_data["phone"]

        if candidate.email is None and parsed_data.get("email"):
            candidate.email = parsed_data["email"]

        if hasattr(candidate, 'experience_years') and candidate.experience_years is None and parsed_data.get("experience_years"):
            candidate.experience_years = parsed_data["experience_years"]

        await session.flush()
        logger.info(f"Updated candidate {candidate_id} from parsed resume")

    except Exception as e:
        logger.warning(f"Resume parsing failed for {filename}: {e}")
        # Don't raise - we don't want to block file upload
        return