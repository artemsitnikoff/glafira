"""Парсинг резюме и автозаполнение полей кандидата"""

import logging
import re
from io import BytesIO
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from .client import call_json
from .prompts import RESUME_PARSE_PROMPT
from ...models import Candidate, CandidateExperience, CandidateSkill, CandidateEducation

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
            text = content.decode('utf-8', errors='ignore')
            logger.info(f"Extracted {len(text)} characters from text file {filename}")
            return text if text.strip() else None
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
            text = "\n".join(text_parts) if text_parts else None
            if text:
                logger.info(f"Extracted {len(text)} characters from PDF {filename}")
            else:
                logger.warning(f"No text extracted from PDF {filename} (возможно скан/картинка)")
            return text
        except Exception as e:
            logger.warning(f"Failed to extract PDF text: {e}")
            return None

    elif file_ext in {'.doc', '.docx'}:
        # TODO: Future implementation for Word documents
        logger.info(f"DOC/DOCX format not yet supported: {filename}")
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

    # Get candidate с eager-загрузкой связей — иначе доступ к candidate.experience/skills/
    # education в async-режиме триггерит ленивый SELECT вне greenlet → "greenlet_spawn has
    # not been called" и парс падает.
    result = await session.execute(
        select(Candidate)
        .options(
            selectinload(Candidate.experience),
            selectinload(Candidate.skills),
            selectinload(Candidate.education),
        )
        .where(
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
        # Call Claude to parse structured data with increased token limit for full resumes
        parsed_data = await call_json(
            system=RESUME_PARSE_PROMPT,
            user=text,
            # 16000: полное резюме + дословное «Обо мне» не должны упереться в лимит и обрезать
            # JSON (обрезка по finish_reason=length роняет весь парс — см. client.py)
            max_tokens=16000
        )

        # Заполняем только пустые поля. Значения парсера КОЭРСИМ к типу/длине колонки
        # (LLM возвращает зарплату строкой → INTEGER; телефон/строки могут превысить лимит
        # колонки) — иначе flush падает DataError и отравляет сессию, роняя всю загрузку файла.

        # Скаляры (как раньше) — только если поле пустое
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

        # «Обо мне» — самоописание кандидата (раздел резюме) → resume_summary (свободно под это)
        if candidate.resume_summary is None:
            if (v := _to_str(parsed_data.get("about"), 5000)):
                candidate.resume_summary = v

        if hasattr(candidate, 'experience_years') and candidate.experience_years is None:
            if (v := _to_int(parsed_data.get("experience_years"))) is not None:
                candidate.experience_years = v

        # Структурные записи — создаём только если у кандидата их ещё НЕТ (не затираем ручные правки)

        # Опыт работы
        if not candidate.experience and parsed_data.get("experience"):
            exp_count = 0
            created_exp = []
            for idx, exp_data in enumerate(parsed_data["experience"]):
                # position обязателен — пропускаем записи без position
                if not (position := _to_str(exp_data.get("position"), 255)):
                    continue

                experience = CandidateExperience(
                    candidate_id=candidate.id,
                    company_id=company_id,
                    position=position,
                    company=_to_str(exp_data.get("company"), 255),
                    period=_to_str(exp_data.get("period"), 120),
                    description=_to_str(exp_data.get("description"), 10000),  # Text колонка, большой лимит
                    order_index=idx
                )
                session.add(experience)
                created_exp.append(experience)
                exp_count += 1

            # Синхронизируем денормализованные «последнее место» со самой свежей записью опыта,
            # чтобы мета карточки совпадала с опытом (а не с устаревшими/ручными last_*).
            from ...services.candidate import pick_latest_experience
            latest = pick_latest_experience(created_exp)
            if latest:
                candidate.last_position = latest.position
                candidate.last_company = latest.company
                candidate.last_period = latest.period

            logger.info(f"Created {exp_count} experience records for candidate {candidate_id}")

        # Навыки
        if not candidate.skills and parsed_data.get("skills"):
            skill_count = 0
            for idx, skill_data in enumerate(parsed_data["skills"]):
                if not (skill := _to_str(skill_data, 120)):
                    continue

                candidate_skill = CandidateSkill(
                    candidate_id=candidate.id,
                    company_id=company_id,
                    skill=skill,
                    order_index=idx
                )
                session.add(candidate_skill)
                skill_count += 1

            logger.info(f"Created {skill_count} skill records for candidate {candidate_id}")

        # Образование
        if not candidate.education and parsed_data.get("education"):
            edu_count = 0
            for idx, edu_data in enumerate(parsed_data["education"]):
                education = CandidateEducation(
                    candidate_id=candidate.id,
                    company_id=company_id,
                    institution=_to_str(edu_data.get("institution"), 255),
                    specialty=_to_str(edu_data.get("specialty"), 255),
                    years=_to_str(edu_data.get("years"), 40),
                    order_index=idx
                )
                session.add(education)
                edu_count += 1

            logger.info(f"Created {edu_count} education records for candidate {candidate_id}")

        # Доп. поля для блока «Дополнительно» карточки (languages/relocation/business_trips/remote)
        # → пишем в candidate.extra (JSONB), как resume_gen. Реассайн обязателен (иначе SQLAlchemy
        # не заметит мутацию dict). Не затираем уже заполненные ключи.
        existing_extra = dict(candidate.extra or {})
        extra_changed = False
        if "languages" not in existing_extra and isinstance(parsed_data.get("languages"), list):
            langs = [s for x in parsed_data["languages"] if (s := _to_str(x, 120))]
            if langs:
                existing_extra["languages"] = langs
                extra_changed = True
        for key in ("relocation", "business_trips", "remote"):
            if not existing_extra.get(key) and (v := _to_str(parsed_data.get(key), 200)):
                existing_extra[key] = v
                extra_changed = True
        if extra_changed:
            candidate.extra = existing_extra

        await session.flush()
        logger.info(f"Successfully updated candidate {candidate_id} from parsed resume")

    except Exception as e:
        logger.warning(f"Resume parsing failed for {filename}: {e}")
        # Don't raise - we don't want to block file upload
        return