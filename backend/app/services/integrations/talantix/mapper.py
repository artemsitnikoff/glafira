"""Маппинг данных Talantix → формат Глафиры (кандидат + комментарии + согласие).

Поля подтверждены по доке api.talantix.ru/docs:
* PersonItem: id, firstName!, lastName, middleName, gender(male/female), birthDay(Instant),
  area{name}, source{id name}, contacts{items{ContactItem{type value}}},
  resumes{items{StructuredResume{title skills}}} (skills = ВЕСЬ текст резюме плоско),
  personalDataAgreement, responses{count}.
* CommentAdded: id!(дедуп), eventTime!(Instant, дата оригинала), html(текст),
  initiator(Initiator=CompanyManager|SystemInitiator — автор), vacancy(контекст).
* HhCommentAdded: id!, eventTime!, html, managerName!(автор строкой), initiator.
* PersonalDataAgreement: personalDataAgreementStatus!(enum agree/disagree/expired/
  not_sent/sent), updatedAt!, expiredAt.
"""

import logging
from datetime import date, datetime, timezone

from ....services.phone import normalize_phone
from ..potok.mapper import _html_to_text

logger = logging.getLogger(__name__)

# Типы контактов Talantix, которые считаем телефоном (первый найденный → phone).
_PHONE_TYPES = {"cell", "work", "home", "mobile", "phone"}


def _instant_to_datetime(value) -> datetime | None:
    """Instant (миллисекунды с эпохи, int) → aware datetime UTC."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _instant_to_date(value) -> date | None:
    dt = _instant_to_datetime(value)
    return dt.date() if dt else None


def _extract_contacts(node: dict) -> tuple[str | None, str | None, list[dict]]:
    """(phone, email, messengers) из contacts.items[]{type,value}."""
    items = ((node.get("contacts") or {}).get("items")) or []
    phone: str | None = None
    email: str | None = None
    messengers: list[dict] = []
    for c in items:
        if not isinstance(c, dict):
            continue
        ctype = (c.get("type") or "").strip().lower()
        value = (c.get("value") or "").strip()
        if not value:
            continue
        if ctype == "email":
            if email is None:
                email = value
        elif ctype in _PHONE_TYPES:
            if phone is None:
                norm = normalize_phone(value)
                phone = norm or value
        elif ctype == "telegram":
            messengers.append({"type": "tg", "value": value})
    return phone, email, messengers


def _resume_text(node: dict) -> tuple[str | None, str | None]:
    """(resume_text, resume_title). В Talantix StructuredResume.skills — ВЕСЬ текст
    резюме плоской строкой (опыт/навыки/образование). title — заголовок резюме."""
    resumes = ((node.get("resumes") or {}).get("items")) or []
    if not resumes:
        return None, None
    r = resumes[0] or {}
    text = _html_to_text((r.get("skills") or "").strip() or None)
    title = (r.get("title") or "").strip() or None
    return text, title


def map_person(node: dict) -> dict:
    """PersonItem (dict) → нормализованные поля кандидата.

    Толерантна к отсутствию полей (.get с дефолтами). Salary из Talantix НЕ приходит
    в PersonItem — не выдумываем (остаётся None)."""
    first_name = (node.get("firstName") or "").strip() or "Неизвестно"
    last_name = (node.get("lastName") or "").strip()
    middle_name = (node.get("middleName") or "").strip() or None

    phone, email, messengers = _extract_contacts(node)

    area = node.get("area") or {}
    city = (area.get("name") or "").strip() or None if isinstance(area, dict) else None

    gender_raw = (node.get("gender") or "").strip().lower()
    gender = gender_raw if gender_raw in ("male", "female") else None

    birth_date = _instant_to_date(node.get("birthDay"))

    resume_text, resume_title = _resume_text(node)

    source_obj = node.get("source") or {}
    source_name = (source_obj.get("name") or "").strip() or None if isinstance(source_obj, dict) else None

    responses = node.get("responses") or {}
    responses_count = responses.get("count") if isinstance(responses, dict) else None

    return {
        "talantix_person_id": str(node.get("id")) if node.get("id") is not None else None,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "phone": phone,
        "email": email,
        "messengers": messengers,
        "city": city,
        "birth_date": birth_date,
        "gender": gender,
        "last_position": resume_title,
        "resume_text": resume_text,
        "source_name": source_name,
        "responses_count": responses_count,
    }


def _initiator_name(initiator) -> str | None:
    """Имя автора из Initiator (union CompanyManager | SystemInitiator)."""
    if not isinstance(initiator, dict):
        return None
    if initiator.get("__typename") == "SystemInitiator":
        return "Talantix (система)"
    parts = [initiator.get("lastName"), initiator.get("firstName"), initiator.get("middleName")]
    joined = " ".join(str(p).strip() for p in parts if p and str(p).strip())
    return joined or None


def map_comment_event(node: dict) -> dict | None:
    """История-событие → комментарий dict, ИЛИ None если это не комментарий.

    Только CommentAdded / HhCommentAdded. Возвращает:
    {external_id, author_name, created_at(datetime оригинала), body}.
    Автор и дата ОРИГИНАЛА сохраняются как есть (не приписываются импортёру)."""
    if not isinstance(node, dict):
        return None
    typename = node.get("__typename")
    if typename not in ("CommentAdded", "HhCommentAdded"):
        return None

    raw_id = node.get("id")
    if raw_id is None:
        return None
    external_id = str(raw_id)

    body = _html_to_text((node.get("html") or "").strip() or None)
    if not body:
        return None  # пустой комментарий не импортируем

    # Автор: HhCommentAdded несёт managerName строкой; CommentAdded — только initiator.
    author_name = None
    if typename == "HhCommentAdded":
        author_name = (node.get("managerName") or "").strip() or None
    if not author_name:
        author_name = _initiator_name(node.get("initiator"))

    # Контекст вакансии (участие в вакансиях фиксируем в тексте истории) — только у CommentAdded.
    vacancy = node.get("vacancy") or {}
    vacancy_title = (vacancy.get("title") or "").strip() or None if isinstance(vacancy, dict) else None
    if vacancy_title:
        body = f"[Вакансия: {vacancy_title}]\n\n{body}"

    created_at = _instant_to_datetime(node.get("eventTime"))

    return {
        "external_id": external_id,
        "author_name": author_name,
        "created_at": created_at,
        "body": body,
    }


def pd_agreement_is_signed(pd: dict | None) -> bool:
    """personalDataAgreement → True только при статусе 'agree' (кандидат дал согласие)."""
    if not isinstance(pd, dict):
        return False
    return (pd.get("personalDataAgreementStatus") or "").strip().lower() == "agree"


def pd_agreement_signed_at(pd: dict | None) -> datetime | None:
    """Дата согласия = updatedAt (Instant) агримента, если есть."""
    if not isinstance(pd, dict):
        return None
    return _instant_to_datetime(pd.get("updatedAt"))
