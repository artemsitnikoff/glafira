"""Маппинг данных кандидата из Potok.io в формат Глафиры"""

import html as _html
import logging
import re
from datetime import date, datetime
from typing import Dict, List, Optional, Any

from ....services.phone import normalize_phone

logger = logging.getLogger(__name__)

_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.I)
_BLOCK_END_RE = re.compile(r"</\s*(p|div|li|h[1-6]|tr)\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(value: Optional[str]) -> Optional[str]:
    """HTML → плоский текст с сохранением переводов строк. Часть резюме из Потока
    приходит с разметкой (<p>/<br>/&nbsp;) — храним чистый текст, чтобы теги не
    протекали в карточку/экспорт/скоринг. Для чистого текста — no-op."""
    if not value:
        return value
    if "<" not in value and "&" not in value:
        return value
    s = _BR_RE.sub("\n", value)
    s = _BLOCK_END_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() or None


def _parse_date(date_str: str) -> Optional[date]:
    """Парсинг даты из строки формата YYYY-MM-DD"""
    if not date_str:
        return None
    try:
        return date.fromisoformat(str(date_str)[:10])
    except (ValueError, TypeError):
        return None


def _parse_salary(salary_data: Any) -> Optional[int]:
    """Парсинг зарплаты - может быть числом или объектом {amount, currency}"""
    if salary_data is None:
        return None

    # Если это число
    if isinstance(salary_data, (int, float)):
        amount = int(salary_data)
        if 0 <= amount <= 10_000_000:
            return amount
        return None

    # Если это объект
    if isinstance(salary_data, dict):
        amount = salary_data.get("amount")
        if amount is not None:
            try:
                amount = int(amount)
                if 0 <= amount <= 10_000_000:
                    return amount
            except (ValueError, TypeError):
                pass

    return None


def _format_period(start: str, end: str, now: bool = False) -> Optional[str]:
    """Форматирование периода работы в формате как в hh-интеграции"""
    if not start and not end:
        return None
    s = (start or "")[:7] if start else "?"
    # Поток: end=None/пусто у текущего места работы → «по наст. время» (подтверждено живым API)
    e = "по наст. время" if (now or not end) else (end or "")[:7]
    return f"{s} — {e}"


def map_potok_applicant(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Маппинг кандидата из Potok в унифицированный формат

    ВНИМАНИЕ: Реальный JSON API живьём НЕ проверен (app.potok.io недоступен из dev-среды).
    Функция толерантна к отсутствующим полям через .get() с дефолтами.

    Args:
        raw: данные кандидата из Potok API

    Returns:
        Словарь с нормализованными данными кандидата
    """
    try:
        # Основные поля
        first_name = (raw.get("first_name") or "").strip() or "Неизвестно"
        last_name = (raw.get("last_name") or "").strip()
        middle_name = (raw.get("middle_name") or "").strip() or None

        # Контакты
        phones = raw.get("phones") or []
        primary_phone = ""
        if phones and isinstance(phones, list) and phones[0]:
            primary_phone = normalize_phone(str(phones[0])) or ""

        email = (raw.get("email") or "").strip() or None

        # Геолокация
        city_data = raw.get("city") or {}
        city = None
        if isinstance(city_data, dict):
            city = (city_data.get("name") or city_data.get("text") or "").strip() or None

        # Дата рождения
        birth_date = _parse_date(raw.get("born"))

        # Пол
        gender_str = (raw.get("gender") or "").strip()
        gender = gender_str if gender_str in ("male", "female") else None

        # Зарплата
        salary = _parse_salary(raw.get("salary"))

        # Желаемая должность
        title = (raw.get("title") or "").strip() or None

        # URL источника
        source_url = (raw.get("source_url") or "").strip() or None
        if source_url and len(source_url) > 500:
            source_url = source_url[:500]

        # cv_params теперь на TOP LEVEL applicant-а, не в resumes[].cv_params
        # (по проверенным данным из ArkadyJarvis)
        resume_params = raw.get("cv_params") or {}

        # Фолбэк на старую схему resumes[].cv_params если top-level пуст
        if not resume_params:
            resumes = raw.get("resumes") or []
            if resumes and isinstance(resumes, list) and resumes[0]:
                resume_params = resumes[0].get("cv_params") or {}

        # Извлекаем данные резюме
        about_me = _html_to_text((resume_params.get("about_me") or "").strip() or None)
        skills_text = (resume_params.get("skills") or "").strip() or None

        # Опыт работы
        experience = []
        exp_list = resume_params.get("experience") or []
        for idx, exp in enumerate(exp_list):
            if not isinstance(exp, dict):
                continue

            position = (exp.get("position") or "").strip()
            if not position:
                continue

            company = (exp.get("company") or "").strip() or None
            start = exp.get("start")
            end = exp.get("end")
            now = bool(exp.get("now"))
            period = _format_period(start, end, now)
            description = _html_to_text((exp.get("description") or "").strip() or None)

            experience.append({
                "position": position,
                "company": company,
                "period": period,
                "description": description,
                "order_index": idx
            })

        # Навыки
        skills = []
        skill_set = resume_params.get("skill_set") or []
        for idx, skill in enumerate(skill_set):
            skill_str = str(skill).strip()
            if skill_str:
                skills.append({
                    "skill": skill_str,
                    "order_index": idx
                })

        # Образование
        education = []
        education_data = resume_params.get("education") or {}
        primary_education = education_data.get("primary") or []
        for idx, ed in enumerate(primary_education):
            if not isinstance(ed, dict):
                continue

            institution = (ed.get("name") or ed.get("organization") or "").strip()
            if not institution:
                continue

            specialty = (ed.get("result") or ed.get("organization") or "").strip() or None
            year = ed.get("year")
            years = str(year) if year else None

            education.append({
                "institution": institution,
                "specialty": specialty,
                "years": years,
                "order_index": idx
            })

        # Языки (в extra как массив строк)
        languages = []
        languages_data = resume_params.get("languages") or []
        for lang in languages_data:
            if not isinstance(lang, dict):
                continue

            name = (lang.get("name") or "").strip()
            level_data = lang.get("level") or {}
            level_name = (level_data.get("name") or "").strip() if isinstance(level_data, dict) else ""

            if name:
                lang_str = f"{name} — {level_name}" if level_name else name
                languages.append(lang_str)

        # Собираем resume_text и resume_summary
        resume_parts = []
        if title:
            resume_parts.append(f"Желаемая должность: {title}")
        if about_me:
            resume_parts.append(about_me)
        if skills_text:
            resume_parts.append(skills_text)

        resume_text = "\n\n".join(resume_parts) or None
        resume_summary = about_me

        return {
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
            "phone": primary_phone or None,
            "email": email,
            "city": city,
            "birth_date": birth_date,
            "gender": gender,
            "salary_expectation": salary,
            "last_position": title,
            "source_url": source_url,
            "resume_text": resume_text,
            "resume_summary": resume_summary,
            "experience": experience,
            "skills": skills,
            "education": education,
            "languages": languages,
            "external_id": str(raw.get("id")) if raw.get("id") else None
        }

    except Exception as e:
        logger.error(f"Ошибка маппинга кандидата Potok: {e}")
        # Возвращаем минимальные данные, чтобы не сломать весь импорт
        return {
            "first_name": "Неизвестно",
            "last_name": "",
            "middle_name": None,
            "phone": None,
            "email": None,
            "city": None,
            "birth_date": None,
            "gender": None,
            "salary_expectation": None,
            "last_position": None,
            "source_url": None,
            "resume_text": None,
            "resume_summary": None,
            "experience": [],
            "skills": [],
            "education": [],
            "languages": [],
            "external_id": str(raw.get("id")) if raw.get("id") else None
        }