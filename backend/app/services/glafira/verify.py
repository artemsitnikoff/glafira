"""Верификация кандидатов"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...core.errors import ConsentRequiredError, NotFoundError, GlafiraParseError
from ...models import Candidate, Consent, Verification, Event
from ...services.audit import audit
from ...services.dadata import clean_phone, clean_email, clean_name
from .client import call_json

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


async def _build_ai_intel_block(candidate: Candidate, contacts_data: dict) -> dict:
    """Создать блок AI-анализа на основе имеющихся данных"""
    verify_model = settings.GLAFIRA_VERIFY_MODEL or settings.GLAFIRA_MODEL

    # Подготовим данные для анализа
    analysis_data = {
        "resume_text": candidate.resume_text or "",
        "personal_info": {
            "full_name": candidate.full_name,
            "birth_date": str(candidate.birth_date) if candidate.birth_date else None,
            "city": candidate.city,
            "phone": candidate.phone,
            "email": candidate.email,
            "position": candidate.last_position,
            "company": candidate.last_company
        },
        "dadata_results": contacts_data
    }

    system_prompt = """Вы — AI-аналитик безопасности для HR. Анализируете ТОЛЬКО предоставленные данные о кандидате.

КРИТИЧЕСКИ ВАЖНО:
- НЕ выдумывайте внешние факты (нет веб-поиска, соцсетей, баз данных)
- НЕ утверждайте что "нашли профиль", "проверили в интернете", "найдены упоминания"
- Анализируйте ТОЛЬКО согласованность предоставленных данных

Анализируйте:
1. Полноту и качество предоставленной информации
2. Согласованность данных между собой
3. Результаты стандартизации контактов (если есть)
4. Явные несоответствия или пропуски

Ответьте в JSON:
{
  "summary": "Краткая оценка (1-2 предложения)",
  "flags": ["список выявленных проблем/особенностей"],
  "confidence": число_от_0_до_1
}"""

    user_prompt = f"Данные кандидата для анализа:\n\n{analysis_data}"

    try:
        result = await call_json(
            system=system_prompt,
            user=user_prompt,
            max_tokens=1024,
            model=verify_model
        )

        return {
            "key": "ai_intel",
            "title": "AI-оценка Глафиры",
            "sources": [{"name": "Глафира AI", "type": "ai"}],
            "status": "info",  # AI-анализ всегда информационный
            "data": {
                "summary": result.get("summary", ""),
                "flags": result.get("flags", []),
                "confidence": result.get("confidence", 0.0)
            }
        }
    except (GlafiraParseError, Exception) as e:
        logger.warning("AI-анализ верификации неудачен: %s", e)
        return {
            "key": "ai_intel",
            "title": "AI-оценка Глафиры",
            "sources": [{"name": "Глафира AI", "type": "ai"}],
            "status": "info",
            "data": {"status": "AI-оценка недоступна"}
        }


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

    # 3. AI analysis of available data only
    ai_block = await _build_ai_intel_block(candidate, contacts_block["data"])
    blocks.append(ai_block)

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