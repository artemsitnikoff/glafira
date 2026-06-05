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

# Двухшаг (как ArkadyJarvis): сначала СВОБОДНАЯ разведка (нарратив) — она находит людей куда
# лучше строгого JSON (строгий JSON + опус отбрасывали реальные находки). Потом отдельный
# дешёвый вызов БЕЗ веба разбирает нарратив в JSON для UI. Инструкция — в USER-промпте, не system.

# Шаг 1 — найти (свободный текст со ссылками).
_OSINT_FIND_PROMPT = """Ты — AI-разведчик для рекрутера. Найди в ОТКРЫТОМ интернете публичную профессиональную активность человека. Активно используй WebSearch и WebFetch — сделай 4–6 РАЗНЫХ запросов (ФИО+компания, ФИО+город, ФИО+должность, по email/нику из email, по номеру телефона, прицельно по GitHub / Habr / Stack Overflow / Telegram / vc.ru / ВКонтакте / LinkedIn / личный сайт). Не сдавайся после одного запроса.

Человек (данные по его согласию — используй ВСЁ как ключи поиска):
{query}

Собери карточку: кто это; профили (со ссылками); telegram-каналы; доклады/статьи/интервью/упоминания (короткая цитата + ссылка). Что нашёл с ВЫСОКОЙ вероятностью того же человека (совпадение по компании/городу/должности/почте) — включай, можно с пометкой «вероятно». Что не нашёл — прямо пиши «не нашёл». У каждой находки — реальная ССЫЛКА (URL), которую ты реально открыл. Факты и числа не выдумывай. Ответ — свободным текстом со ссылками."""

# Шаг 2 — структурировать нарратив в JSON (без веба, дёшево).
_OSINT_STRUCTURE_PROMPT = """Из текста-разведки ниже извлеки находки в строгий JSON. Бери ТОЛЬКО то, что РЕАЛЬНО есть в тексте и снабжено URL — ничего не добавляй, не выдумывай, не догадывайся. profiles — аккаунты/профили/каналы на платформах (GitHub / Habr / Stack Overflow / Telegram-канал / LinkedIn / ВКонтакте / Instagram / личный сайт). mentions — статьи / интервью / доклады / новости / упоминания. stats заполняй ТОЛЬКО если в тексте есть конкретные числа (звёзды/подписчики/статьи/репутация), иначе пусто. У каждого элемента ОБЯЗАТЕЛЕН url (http…) — без url не включай. Находки с пометкой «вероятно/возможно НЕ он» — НЕ включай.

Верни ТОЛЬКО JSON, без markdown и текста вокруг:
{"profiles":[{"platform":"...","handle":"... или пусто","url":"https://...","stats":"... или пусто"}],"mentions":[{"quote":"короткая цитата","url":"https://..."}]}

Текст разведки:
{narrative}"""


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


def _osint_pending_blocks() -> list[dict]:
    """Блоки OSINT в состоянии «идёт разведка» — пока fill_candidate_osint не заполнит."""
    return [
        {
            "key": "public_expertise",
            "title": "Публичная экспертиза",
            "sources": [{"name": s, "type": "web"} for s in _OSINT_PLATFORMS],
            "status": "info",
            "data": {"profiles": [], "pending": True},
        },
        {
            "key": "mentions",
            "title": "Упоминания",
            "sources": [{"name": "Веб-поиск", "type": "web"}],
            "status": "info",
            "data": {"mentions": [], "pending": True},
        },
    ]


async def _build_osint_blocks(candidate: Candidate) -> list[dict]:
    """Интернет-разведка кандидата через claude CLI (WebSearch/WebFetch).

    В поиск (по согласию кандидата) уходят ФИО + город + должность + компания + год +
    email + телефон — как ключи. Двухшаг: свободная разведка (находит) → разбор в JSON.
    Возвращает «Публичная экспертиза» (профили) и «Упоминания». Любой сбой → честная заглушка.
    """
    if not candidate.full_name:
        return _osint_stub_blocks("Недостаточно данных для разведки (нет ФИО)")
    if not resolve_claude_token():
        return _osint_stub_blocks("Интернет-разведка не настроена")

    # Все доступные ключи поиска (по согласию кандидата): ФИО, город, должность, компания,
    # год рождения, email, телефон. Контакты — сильные сигналы (привязаны к GitHub/соцсетям).
    parts = [f"ФИО: {candidate.full_name}"]
    if candidate.city:
        parts.append(f"Город: {candidate.city}")
    if candidate.last_position:
        parts.append(f"Должность: {candidate.last_position}")
    if candidate.last_company:
        parts.append(f"Компания: {candidate.last_company}")
    if candidate.birth_date:
        parts.append(f"Год рождения: {candidate.birth_date.year}")
    if candidate.email:
        parts.append(f"Email: {candidate.email}")
    if candidate.phone:
        parts.append(f"Телефон: {candidate.phone}")
    query = "\n".join(parts)
    find_model = settings.GLAFIRA_OSINT_MODEL or "sonnet"

    # Шаг 1 — свободная разведка (находит людей; опус-строгий-JSON отбрасывал реальные находки)
    narrative = await claude_cli_complete(
        prompt=_OSINT_FIND_PROMPT.replace("{query}", query),
        system=None,
        allowed_tools="WebSearch,WebFetch",
        model=find_model,
    )
    if not narrative:
        return _osint_stub_blocks("Разведка недоступна (CLI/токен не настроены или сбой)")

    # Шаг 2 — разобрать нарратив в JSON (без веба, дёшево, sonnet)
    structured = await claude_cli_complete(
        prompt=_OSINT_STRUCTURE_PROMPT.replace("{narrative}", narrative),
        system=None,
        allowed_tools="",  # без инструментов — чистое форматирование
        model="sonnet",
        timeout=60,
    )
    data = _parse_osint_json(structured) if structured else None
    if data is None:
        logger.warning("[osint] разведка прошла, но структурирование не разобралось")
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


async def fill_candidate_osint(candidate_id: UUID, company_id: UUID) -> None:
    """Дозаполнить OSINT-блоки последней верификации кандидата (фоном/инлайн в кроне).

    Открывает СВОЮ сессию (для фоновой задачи из HTTP-эндпоинта). Заменяет pending-блоки
    «Публичная экспертиза»/«Упоминания» результатами разведки, пересчитывает overall-статус.
    Полностью изолирована: любой сбой → лог, без падения.
    """
    from ...database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(Verification)
                .where(Verification.candidate_id == candidate_id, Verification.company_id == company_id)
                .order_by(Verification.created_at.desc())
                .limit(1)
            )
            verification = res.scalar_one_or_none()
            if not verification:
                return
            cres = await session.execute(
                select(Candidate).where(
                    Candidate.id == candidate_id,
                    Candidate.company_id == company_id,
                    Candidate.deleted_at.is_(None),
                )
            )
            candidate = cres.scalar_one_or_none()
            if not candidate:
                return

            osint = await _build_osint_blocks(candidate)  # медленно (WebSearch)

            # Заменить pending-блоки результатами, остальные сохранить
            others = [b for b in (verification.blocks or []) if b.get("key") not in ("public_expertise", "mentions")]
            new_blocks = others + osint
            statuses = [b.get("status") for b in new_blocks]
            if "risk" in statuses:
                overall = "risk"
            elif "warn" in statuses:
                overall = "warn"
            elif "info" in statuses:
                overall = "info"
            else:
                overall = "clean"

            verification.blocks = new_blocks  # переприсвоение → SQLAlchemy зафиксирует JSONB
            verification.status = overall
            await session.commit()
            logger.info(
                "[osint] разведка дозаполнена candidate=%s: %d профилей, %d упоминаний",
                candidate_id,
                len(osint[0]["data"].get("profiles", [])),
                len(osint[1]["data"].get("mentions", [])),
            )
    except Exception as e:  # noqa: BLE001 — фон, не роняем процесс
        logger.warning("[osint] фоновая разведка не удалась candidate=%s: %s", candidate_id, e)


async def verify_candidate(
    session: AsyncSession,
    *,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID | None
) -> Verification:
    """Verify candidate data with real DaData + AI analysis + honest government stubs"""
    # CRITICAL: Check for signed consent first. Фильтр company_id — defense-in-depth
    # (инв.3): consent-гейт 152-ФЗ не должен зависеть от порядка последующих проверок.
    consent_result = await session.execute(
        select(Consent).where(
            Consent.candidate_id == candidate_id,
            Consent.company_id == company_id,
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

    # 3. Интернет-разведка идёт ДОЛГО (4 платформы + упоминания = 60–90с) — не блокируем
    #    HTTP-запрос/скоринг: кладём блоки как «идёт разведка», заполняет fill_candidate_osint.
    blocks.extend(_osint_pending_blocks())

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