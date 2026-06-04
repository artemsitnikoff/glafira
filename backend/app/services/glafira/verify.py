"""Верификация кандидатов"""

import json
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...core.errors import ConsentRequiredError, NotFoundError
from ...models import Candidate, Consent, Verification, Event
from ...services.audit import audit
from ...services.dadata import clean_phone, clean_email, clean_name
from .claude_cli import claude_cli_complete, resolve_claude_token

logger = logging.getLogger(__name__)


async def _build_contacts_block(candidate: Candidate) -> dict:
    """Создать блок верификации контактных данных через DaData"""
    data = {}
    status = "clean"

    # Проверка телефона
    if candidate.phone:
        phone_result = await clean_phone(candidate.phone)
        if phone_result:
            data["phone"] = {
                "original": candidate.phone,
                "standardized": phone_result.get("phone"),
                "provider": phone_result.get("provider"),
                "region": phone_result.get("region"),
                "qc": phone_result.get("qc"),
                "valid": phone_result.get("qc") in [0, 7]  # 0=RU валид, 7=зарубеж валид
            }
            # Если телефон проблемный (qc 1,2,3)
            if phone_result.get("qc") not in [0, 7]:
                status = "warn"
        else:
            data["phone"] = {"status": "Не удалось проверить"}
            if status == "clean":
                status = "info"
    else:
        data["phone"] = {"status": "Не указан"}
        if status == "clean":
            status = "info"

    # Проверка email
    if candidate.email:
        email_result = await clean_email(candidate.email)
        if email_result:
            data["email"] = {
                "original": candidate.email,
                "standardized": email_result.get("email"),
                "type": email_result.get("type"),
                "qc": email_result.get("qc"),
                "valid": email_result.get("qc") == 0  # 0=валидный
            }
            # Если email невалидный
            if email_result.get("qc") != 0:
                status = "warn"
        else:
            data["email"] = {"status": "Не удалось проверить"}
            if status == "clean":
                status = "info"
    else:
        data["email"] = {"status": "Не указан"}
        if status == "clean":
            status = "info"

    # Проверка ФИО
    if candidate.full_name:
        name_result = await clean_name(candidate.full_name)
        if name_result:
            data["name"] = {
                "original": candidate.full_name,
                "surname": name_result.get("surname"),
                "name": name_result.get("name"),
                "patronymic": name_result.get("patronymic"),
                "gender": name_result.get("gender"),
                "qc": name_result.get("qc"),
                "parsed_correctly": name_result.get("qc") == 0
            }
            # Проверка соответствия пола
            if candidate.gender and name_result.get("gender"):
                gender_match = (
                    (candidate.gender == "male" and name_result["gender"] == "М") or
                    (candidate.gender == "female" and name_result["gender"] == "Ж")
                )
                data["name"]["gender_match"] = gender_match
                if not gender_match:
                    status = "warn"
        else:
            data["name"] = {"status": "Не удалось проверить"}
            if status == "clean":
                status = "info"
    else:
        data["name"] = {"status": "Не указано"}
        if status == "clean":
            status = "info"

    # Если DaData не настроена
    if not settings.DADATA_API_KEY or not settings.DADATA_SECRET_KEY:
        data = {"status": "DaData не настроена"}
        status = "info"

    return {
        "key": "contacts",
        "title": "Контактные данные",
        "sources": [{"name": "DaData", "type": "api"}],
        "status": status,
        "data": data
    }


# Источник правды по платформам публичной экспертизы (для шапки блока).
_OSINT_PLATFORMS = ["GitHub", "Habr Career", "Stack Exchange", "TGStat"]

_OSINT_SYSTEM_PROMPT = """Ты — AI-разведчик для HR. По НЕКОНТАКТНЫМ данным кандидата (ФИО, город, должность, компания, год рождения) найди в ОТКРЫТОМ интернете его публичную профессиональную активность. Используй WebSearch и WebFetch.

ЧТО ИСКАТЬ:
1. Профили на профессиональных платформах: GitHub, Habr / Habr Career, Stack Overflow / Stack Exchange, TGStat (телеграм-каналы), при наличии — vc.ru, профильные конференции.
2. Упоминания: доклады на конференциях, статьи, интервью, новости — с короткой цитатой и ссылкой.

СТРАТЕГИЯ: 3–6 запросов. Сначала «ФИО + компания/должность». Частая фамилия — сужай по городу/компании/тематике. Если кандидат — полный омоним публичной личности, НЕ приписывай ему чужое.

КРИТИЧЕСКИ ВАЖНО (анти-галлюцинация):
- Включай находку, ТОЛЬКО если у тебя есть реальный URL, который ты реально нашёл/открыл. Нет URL — не включай.
- НЕ выдумывай профили, ники и числа (звёзды, репозитории, карму, репутацию, подписчиков, ER). Не видел метрику — оставь поле stats пустым.
- НЕ приписывай чужие профили по одному совпадению имени без подтверждающего контекста (город/компания/тематика).
- Лучше пустые списки, чем выдуманные данные.
- НЕ ищи и НЕ упоминай телефоны, email, паспортные/персональные данные.

ФОРМАТ — ТОЛЬКО JSON, без markdown-обёртки и текста до/после:
{
  "profiles": [
    {"platform": "GitHub", "handle": "@ник или /users/...", "url": "https://...", "stats": "412 ★ · 28 repo · активность 2 г. (или пусто)"}
  ],
  "mentions": [
    {"quote": "короткая цитата упоминания", "url": "https://..."}
  ]
}
Ничего не нашёл — верни {"profiles": [], "mentions": []}."""


def _parse_osint_json(raw: str) -> dict | None:
    """Разобрать JSON из ответа CLI (с устойчивостью к обёрткам/преамбуле)."""
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
    return None


def _osint_stub_blocks(note: str) -> list[dict]:
    """Честные заглушки двух OSINT-блоков, когда разведка не выполнена/недоступна."""
    return [
        {
            "key": "public_expertise",
            "title": "Публичная экспертиза",
            "sources": [{"name": s, "type": "web"} for s in _OSINT_PLATFORMS],
            "status": "info",
            "data": {"profiles": [], "note": note},
        },
        {
            "key": "mentions",
            "title": "Упоминания",
            "sources": [{"name": "Веб-поиск", "type": "web"}],
            "status": "info",
            "data": {"mentions": [], "note": note},
        },
    ]


async def _build_osint_blocks(candidate: Candidate) -> list[dict]:
    """Интернет-разведка кандидата через claude CLI (WebSearch/WebFetch).

    PII-firewall: в запрос к ИИ уходят ТОЛЬКО ФИО, город, должность, компания и год
    рождения — телефон/email/паспортные данные НЕ передаются. Возвращает два блока:
    «Публичная экспертиза» (профили) и «Упоминания». Любой сбой → честная заглушка.
    """
    if not candidate.full_name:
        return _osint_stub_blocks("Недостаточно данных для разведки (нет ФИО)")
    if not resolve_claude_token():
        return _osint_stub_blocks("Интернет-разведка не настроена")

    # PII-firewall — только неконтактные идентификаторы
    parts = [f"ФИО: {candidate.full_name}"]
    if candidate.city:
        parts.append(f"Город: {candidate.city}")
    if candidate.last_position:
        parts.append(f"Должность: {candidate.last_position}")
    if candidate.last_company:
        parts.append(f"Компания: {candidate.last_company}")
    if candidate.birth_date:
        parts.append(f"Год рождения: {candidate.birth_date.year}")
    query = "\n".join(parts)

    raw = await claude_cli_complete(
        prompt=f"Данные кандидата (только публично-неконтактные):\n{query}\n\nВерни ТОЛЬКО JSON.",
        system=_OSINT_SYSTEM_PROMPT,
        allowed_tools="WebSearch,WebFetch",
    )
    if not raw:
        return _osint_stub_blocks("Разведка недоступна (CLI/токен не настроены или сбой)")

    data = _parse_osint_json(raw)
    if data is None:
        logger.warning("[osint] не удалось разобрать JSON разведки")
        return _osint_stub_blocks("Не удалось разобрать результат разведки")

    # Только находки с реальным URL — остальное отбрасываем (анти-галлюцинация)
    profiles = [
        {
            "platform": str(p.get("platform", "")).strip(),
            "handle": str(p.get("handle", "")).strip(),
            "url": str(p.get("url", "")).strip(),
            "stats": str(p.get("stats", "")).strip(),
        }
        for p in (data.get("profiles") or [])
        if isinstance(p, dict) and str(p.get("url", "")).startswith("http")
    ]
    mentions = [
        {
            "quote": str(m.get("quote", "")).strip(),
            "url": str(m.get("url", "")).strip(),
        }
        for m in (data.get("mentions") or [])
        if isinstance(m, dict) and str(m.get("url", "")).startswith("http")
    ]

    return [
        {
            "key": "public_expertise",
            "title": "Публичная экспертиза",
            "sources": [{"name": s, "type": "web"} for s in _OSINT_PLATFORMS],
            "status": "info",
            "data": {"profiles": profiles, "found": len(profiles)},
        },
        {
            "key": "mentions",
            "title": "Упоминания",
            "sources": [{"name": "Веб-поиск", "type": "web"}],
            "status": "info",
            "data": {"mentions": mentions, "found": len(mentions)},
        },
    ]


def _build_government_stub_blocks() -> list[dict]:
    """Создать честные заглушки для госреестров (без фейк-вердиктов)"""
    gov_blocks = [
        {
            "key": "inn",
            "title": "Проверка ИНН",
            "sources": [{"name": "ФНС", "type": "gov"}],
            "status": "info",
            "data": {
                "status": "Не подключено",
                "note": "Проверка по госреестрам требует официальной интеграции (152-ФЗ) — в разработке"
            }
        },
        {
            "key": "fssp",
            "title": "Исполнительные производства",
            "sources": [{"name": "ФССП", "type": "gov"}],
            "status": "info",
            "data": {
                "status": "Не подключено",
                "note": "Проверка по госреестрам требует официальной интеграции (152-ФЗ) — в разработке"
            }
        },
        {
            "key": "bankruptcy",
            "title": "Реестр банкротов",
            "sources": [{"name": "ЕФРСБ", "type": "gov"}],
            "status": "info",
            "data": {
                "status": "Не подключено",
                "note": "Проверка по госреестрам требует официальной интеграции (152-ФЗ) — в разработке"
            }
        },
        {
            "key": "registries",
            "title": "Прочие реестры",
            "sources": [{"name": "РОСРЕЕСТР", "type": "gov"}],
            "status": "info",
            "data": {
                "status": "Не подключено",
                "note": "Проверка по госреестрам требует официальной интеграции (152-ФЗ) — в разработке"
            }
        },
        {
            "key": "alimony",
            "title": "Алименты",
            "sources": [{"name": "ФССП", "type": "gov"}],
            "status": "info",
            "data": {
                "status": "Не подключено",
                "note": "Проверка по госреестрам требует официальной интеграции (152-ФЗ) — в разработке"
            }
        }
    ]
    return gov_blocks


async def verify_candidate(
    session: AsyncSession,
    *,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID | None
) -> Verification:
    """Verify candidate data with real DaData + AI analysis + honest government stubs"""
    # CRITICAL: Check for signed consent first
    consent_result = await session.execute(
        select(Consent).where(
            Consent.candidate_id == candidate_id,
            Consent.status == 'signed'
        ).limit(1)
    )
    consent = consent_result.scalar_one_or_none()
    if not consent:
        raise ConsentRequiredError()

    # Get candidate
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    candidate = candidate_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Кандидат")

    # Build verification blocks
    blocks = []

    # 1. Real contacts verification via DaData
    contacts_block = await _build_contacts_block(candidate)
    blocks.append(contacts_block)

    # 2. Honest government stubs (NOT fake verdicts)
    gov_blocks = _build_government_stub_blocks()
    blocks.extend(gov_blocks)

    # 3. Интернет-разведка: публичная экспертиза + упоминания (claude CLI, WebSearch)
    osint_blocks = await _build_osint_blocks(candidate)
    blocks.extend(osint_blocks)

    # Determine overall status: risk > warn > info > clean
    statuses = [block["status"] for block in blocks]
    if "risk" in statuses:
        overall_status = "risk"
    elif "warn" in statuses:
        overall_status = "warn"
    elif "info" in statuses:
        overall_status = "info"
    else:
        overall_status = "clean"

    # Create verification record
    now = datetime.now(timezone.utc)
    verification = Verification(
        company_id=company_id,
        candidate_id=candidate_id,
        consent_id=consent.id,
        checked_at=now,
        status=overall_status,
        blocks=blocks,
        is_mock=False,  # This is real partial verification, not mock
        created_at=now
    )

    session.add(verification)

    # Create event
    event = Event(
        company_id=company_id,
        type='verify',
        actor_type='ai',
        actor_user_id=actor_user_id,
        text=f"Глафира провела верификацию: {overall_status}",
        entities=[
            {"type": "candidate", "id": str(candidate_id), "label": candidate.full_name}
        ],
        candidate_id=candidate_id,
        created_at=now
    )
    session.add(event)

    # Audit log
    await audit(
        session,
        action='verify_candidate',
        entity_type='verification',
        entity_id=verification.id,
        after={
            'status': overall_status,
            'blocks_count': len(blocks),
            'consent_id': str(consent.id)
        },
        actor_user_id=actor_user_id,
        actor_type='ai',
        company_id=company_id,
    )

    await session.flush()
    return verification


async def get_candidate_verification(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID
) -> Verification | None:
    """Get latest verification for candidate"""
    # Verify candidate exists and belongs to company
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    # Get latest verification
    result = await session.execute(
        select(Verification)
        .where(Verification.candidate_id == candidate_id)
        .order_by(Verification.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()