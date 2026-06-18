"""Парсинг файла с описанием вакансии и автозаполнение полей формы"""

import logging
import re

from .client import call_json
from .prompts import VACANCY_PARSE_PROMPT
from .resume_parse import extract_resume_text

logger = logging.getLogger(__name__)


def _to_int(value) -> int | None:
    """Безопасно привести ответ LLM к int (аналог resume_parse._to_int)."""
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
    if n < 0 or n > 1_000_000_000:
        return None
    return n


def _to_str(value, maxlen: int) -> str | None:
    """Привести к строке нужной длины, пустое/None → None."""
    if value is None:
        return None
    s = str(value).strip()
    return s[:maxlen] if s else None


async def parse_vacancy_to_dict(content: bytes, filename: str, api_key: str) -> dict | None:
    """Parse vacancy file to structured dict without saving to DB.

    Переиспользует extract_resume_text (generic, PDF/DOCX/TXT, asyncio.to_thread внутри).

    Returns:
        dict с полями вакансии или None если формат не поддержан / текст не распознан.
    """
    text = await extract_resume_text(content, filename)
    if not text:
        logger.info(f"No text extracted from vacancy file {filename}")
        return None

    try:
        parsed_data = await call_json(
            system=VACANCY_PARSE_PROMPT,
            user=text,
            api_key=api_key,
            max_tokens=4000,
        )

        result = {
            "name": _to_str(parsed_data.get("name"), 255),
            "city": _to_str(parsed_data.get("city"), 120),
            "department": _to_str(parsed_data.get("department"), 255),
            "employment_type": _to_str(parsed_data.get("employment_type"), 120),
            "salary_from": _to_int(parsed_data.get("salary_from")),
            "salary_to": _to_int(parsed_data.get("salary_to")),
            "description": _to_str(parsed_data.get("description"), 50000),
        }

        return result

    except Exception as e:
        logger.warning(f"Vacancy file parsing failed for {filename}: {e}")
        return None
