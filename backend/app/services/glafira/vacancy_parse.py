"""Парсинг файла с описанием вакансии и автозаполнение полей формы"""

import logging

from .client import call_json
from .prompts import VACANCY_PARSE_PROMPT
from .resume_parse import extract_resume_text, _to_int, _to_str  # переиспускаем хелперы коэрсии

logger = logging.getLogger(__name__)


def _normalize_employment_type(value) -> str | None:
    """Приводит тип занятости к коду формы вакансии (full/part/project).

    LLM может вернуть код ('full') ИЛИ человекочитаемое ('Полная занятость') — фронт
    принимает только коды full/part/project, поэтому нормализуем здесь, иначе поле
    молча отбрасывается. Неизвестное → None (человек выберет сам).
    """
    if not value:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if "part" in s or "част" in s:
        return "part"
    if "project" in s or "проект" in s:
        return "project"
    if "full" in s or "полн" in s:
        return "full"
    return None


async def parse_vacancy_to_dict(content: bytes, filename: str, api_key: str) -> dict | None:
    """Parse vacancy file to structured dict without saving to DB.

    Переиспользует extract_resume_text (generic, PDF/DOCX/TXT, asyncio.to_thread внутри)
    и call_json (OpenRouter, ключ компании) — тот же канал, что у резюме-парсинга.

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
            max_tokens=8000,  # описание вакансии бывает длинным — не обрезать
        )

        result = {
            "name": _to_str(parsed_data.get("name"), 255),
            "city": _to_str(parsed_data.get("city"), 120),
            "department": _to_str(parsed_data.get("department"), 255),
            "employment_type": _normalize_employment_type(parsed_data.get("employment_type")),
            "salary_from": _to_int(parsed_data.get("salary_from")),
            "salary_to": _to_int(parsed_data.get("salary_to")),
            "description": _to_str(parsed_data.get("description"), 50000),
        }

        return result

    except Exception as e:
        logger.warning(f"Vacancy file parsing failed for {filename}: {e}")
        return None
