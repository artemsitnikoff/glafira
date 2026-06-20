"""Синхронизация откликов с Хабр Карьера → воронка Глафиры.

Зеркалит паттерн hh-синхронизации (import_response / poll_responses_now / link_vacancy).
Все вызовы Хабр-API изолированы в client.py и помечены ASSUMPTION.
Маппинг резюме Хабра → нормализованный dict — в _habr_resume_to_normalized() ниже.

ВАЖНО: вся инфраструктура (дедуп, Application, normalize_phone, company-изоляция, audit)
РЕАЛЬНАЯ и тестируется с мок-клиентом.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import (
    Vacancy,
    Application,
    Candidate,
    CandidateExperience,
    CandidateSkill,
    CandidateEducation,
)
from ....models.habr_integration import HabrIntegration
from ....services.audit import audit
from ....services.candidate_dedup import find_duplicate_candidates
from ....services.phone import normalize_phone
from ....core.errors import ValidationError
from ....services.settings.crypto import decrypt_text
from . import client as habr_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Маппер Хабр-резюме → нормализованный dict (ключи как у hh-маппера)
# ---------------------------------------------------------------------------

def _habr_resume_to_normalized(raw_resume: dict) -> dict:
    """Приводит raw-резюме Хабра к нормализованному dict с ключами, совместимыми
    с hh-маппером: first_name, last_name, middle_name, city, phone, email, title,
    experience[{position, company, start, end, description}], skill_set[], education.

    # ⚠️ ASSUMPTION — имена полей Хабр-резюме НЕ подтверждены документацией.
    # Все ключи raw_resume.get("...") — предположения на основе типичных REST API.
    # Пиннинг требуется по реальному ответу с одобренным приложением Хабром.
    #
    # Предположения:
    #   first_name      → raw["first_name"] или raw["name"] split[0]
    #   last_name       → raw["last_name"] или raw["name"] split[-1]
    #   city            → raw["city"]["name"] | raw["location"]["name"] | raw["city"]
    #   phone           → raw["phone"] | raw["contacts"][?]["phone"]
    #   email           → raw["email"] | raw["contacts"][?]["email"]
    #   title           → raw["title"] | raw["specialization"] | raw["position"]
    #   experience      → raw["experience"] | raw["work_experience"]
    #     position      → exp["position"] | exp["title"]
    #     company       → exp["company"] | exp["employer"]
    #     start         → exp["started_at"] | exp["start_date"] | exp["start"]
    #     end           → exp["finished_at"] | exp["end_date"] | exp["end"]
    #     description   → exp["description"]
    #   skill_set       → raw["skills"] | raw["skill_set"] (list[str|dict])
    #   education       → raw["education"]["primary"] | raw["education"] (list)

    Изолировано в этой функции — при пиннинге править ТОЛЬКО здесь.
    """
    # --- ФИО ---
    # ⚠️ ASSUMPTION — ключи first_name/last_name/middle_name
    first_name = (raw_resume.get("first_name") or "").strip()
    last_name = (raw_resume.get("last_name") or "").strip()
    middle_name = (raw_resume.get("middle_name") or "").strip() or None

    # Фолбэк: если нет раздельных полей, пробуем "name" (ASSUMPTION)
    if not first_name and not last_name:
        full_name = (raw_resume.get("name") or "").strip()
        parts = full_name.split() if full_name else []
        last_name = parts[0] if len(parts) >= 1 else ""
        first_name = parts[1] if len(parts) >= 2 else ""
        middle_name = parts[2] if len(parts) >= 3 else None

    # --- Город ---
    # ⚠️ ASSUMPTION — city.name | location.name | city (строка)
    city_raw = raw_resume.get("city") or raw_resume.get("location") or {}
    if isinstance(city_raw, dict):
        city = city_raw.get("name") or None
    elif isinstance(city_raw, str) and city_raw.strip():
        city = city_raw.strip()
    else:
        city = None

    # --- Контакты ---
    # ⚠️ ASSUMPTION — phone/email как прямые поля ИЛИ в contacts[]
    phone_raw = raw_resume.get("phone")
    email_raw = raw_resume.get("email")

    # Фолбэк на contacts[] (ASSUMPTION — список dict с type/value)
    if not phone_raw or not email_raw:
        for contact in (raw_resume.get("contacts") or []):
            if not isinstance(contact, dict):
                continue
            ctype = (contact.get("type") or "").lower()
            cval = contact.get("value") or contact.get("phone") or contact.get("email")
            if not cval:
                continue
            if "phone" in ctype and not phone_raw:
                phone_raw = cval
            elif "email" in ctype and not email_raw:
                email_raw = cval

    phone = normalize_phone(str(phone_raw)) if phone_raw else None
    email = (str(email_raw).strip()[:255] or None) if email_raw else None

    # --- Желаемая должность ---
    # ⚠️ ASSUMPTION — title | specialization | position
    title = (
        raw_resume.get("title")
        or raw_resume.get("specialization")
        or raw_resume.get("position")
        or ""
    ).strip() or None

    # --- Опыт ---
    # ⚠️ ASSUMPTION — experience | work_experience (список dict)
    raw_experience = raw_resume.get("experience") or raw_resume.get("work_experience") or []
    experience = []
    for exp in raw_experience:
        if not isinstance(exp, dict):
            continue
        # ⚠️ ASSUMPTION — position | title; company | employer; started_at | start_date | start
        pos = (exp.get("position") or exp.get("title") or "").strip()
        comp = (exp.get("company") or exp.get("employer") or "").strip() or None
        start = (
            exp.get("started_at") or exp.get("start_date") or exp.get("start") or None
        )
        end = (
            exp.get("finished_at") or exp.get("end_date") or exp.get("end") or None
        )
        desc = exp.get("description") or None
        experience.append({
            "position": pos,
            "company": comp,
            "start": str(start)[:10] if start else None,
            "end": str(end)[:10] if end else None,
            "description": desc,
        })

    # --- Навыки ---
    # ⚠️ ASSUMPTION — skills | skill_set (список строк или dict с полем name/title)
    raw_skills = raw_resume.get("skills") or raw_resume.get("skill_set") or []
    skill_set = []
    for sk in raw_skills:
        if isinstance(sk, str) and sk.strip():
            skill_set.append(sk.strip())
        elif isinstance(sk, dict):
            name = (sk.get("name") or sk.get("title") or sk.get("label") or "").strip()
            if name:
                skill_set.append(name)

    # --- Образование ---
    # ⚠️ ASSUMPTION — education.primary | education (список dict)
    raw_edu = raw_resume.get("education") or {}
    if isinstance(raw_edu, dict):
        edu_list = raw_edu.get("primary") or raw_edu.get("items") or []
    elif isinstance(raw_edu, list):
        edu_list = raw_edu
    else:
        edu_list = []

    education_primary = []
    for ed in edu_list:
        if not isinstance(ed, dict):
            continue
        # ⚠️ ASSUMPTION — name | organization; specialty | faculty; year | graduation_year
        inst = (ed.get("name") or ed.get("organization") or ed.get("university") or "").strip()
        if not inst:
            continue
        education_primary.append({
            "name": inst,
            "organization": (ed.get("faculty") or ed.get("specialty") or "").strip(),
            "result": (ed.get("degree") or "").strip(),
            "year": ed.get("year") or ed.get("graduation_year"),
        })

    return {
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "city": city,
        "phone": phone,          # уже normalize_phone (цифры без '+' или None)
        "email": email,
        "title": title,
        "experience": experience,
        "skill_set": skill_set,
        "education": {"primary": education_primary},
    }


# ---------------------------------------------------------------------------
# Вспомогательная функция построения секций резюме
# Переиспользует hh-маппер build_candidate_resume_sections через нормализованный dict
# ---------------------------------------------------------------------------

def _build_habr_resume_sections(
    candidate_id: UUID,
    company_id: UUID,
    normalized: dict,
) -> list:
    """Строит ORM-объекты секций резюме из нормализованного Хабр-резюме.

    Формат normalized совместим с hh-маппером — ключи те же:
    experience[{position, company, start, end, description}], skill_set[], education.primary[].
    Переиспользует hh-маппер _hh_period, структуры CandidateExperience/Skill/Education.
    """
    # Импорт локальный — избегаем циклического импорта между habr.sync и hh.service
    from ...integrations.hh.service import build_candidate_resume_sections
    return build_candidate_resume_sections(candidate_id, company_id, normalized)


# ---------------------------------------------------------------------------
# Получение валидного access_token Хабра (per-company)
# ---------------------------------------------------------------------------

async def get_valid_access_token_habr(session: AsyncSession, company_id: UUID) -> str:
    """Возвращает расшифрованный access_token из HabrIntegration.

    Хабр: рефреш-флоу неизвестен до одобрения приложения.
    Если токен протух — возвращает честную ValidationError «переподключите Хабр»,
    не 500 и не фейк-успех. Рефреш токена НЕ делается (риск ошибки неизвестного API).

    Raises:
        ValidationError: нет интеграции / токен не установлен / истёк.
    """
    result = await session.execute(
        select(HabrIntegration).where(HabrIntegration.company_id == company_id)
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.access_token:
        raise ValidationError(
            "Хабр Карьера не подключён: пройдите OAuth-авторизацию в Настройки → Интеграции"
        )

    # Проверяем срок действия (если хранится)
    if integration.expires_at:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        # Если expires_at naive → сделать aware (в БД должно быть timezone-aware, но подстрахуемся)
        expires_at = integration.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now >= expires_at:
            # ⚠️ Рефреш-флоу Хабра неизвестен до одобрения приложения.
            # Честная ошибка: пользователь должен переподключить Хабр вручную.
            raise ValidationError(
                "Токен Хабр Карьера истёк. Переподключите интеграцию в Настройки → Интеграции."
            )

    return decrypt_text(integration.access_token)


# ---------------------------------------------------------------------------
# import_habr_response — зеркало hh.service.import_response
# ---------------------------------------------------------------------------

async def import_habr_response(
    session: AsyncSession,
    company_id: UUID,
    vacancy: "Vacancy",
    response_item: dict,
    access_token: str,
) -> str:
    """Импорт ИЛИ обновление одного отклика Хабр Карьера. Возвращает 'created' | 'updated'.

    # ⚠️ ASSUMPTION — структура response_item (поля id, resume, status...) НЕ подтверждена.
    # Предположение: response_item содержит:
    #   id          — идентификатор отклика (habr_response_id для дедупа)
    #   resume      — dict или {id/url} ссылка на резюме кандидата
    #   status      — статус отклика (например 'new', 'viewed', 'rejected')
    # Пиннинг по реальному ответу GET /employer/responses с одобренным приложением.

    Логика (зеркало hh.service.import_response):
    1. Извлечь habr_response_id из response_item (дедуп).
    2. Если Application с этим id уже есть (company-scoped) → обновить данные кандидата.
    3. Иначе: получить полное резюме через get_resume, нормализовать.
    4. Дедуп кандидата find_duplicate_candidates(phone, email) → существующий или новый.
    5. Создать/обновить Candidate(source='habr', company_id, ...).
    6. Секции резюме (опыт/навыки/образование).
    7. Application(stage='response', habr_response_id, company_id, vacancy_id, ...).
    8. audit.
    """
    # --- Извлечь habr_response_id ---
    # ⚠️ ASSUMPTION — поле "id" в response_item
    response_id = str(response_item.get("id") or "").strip()
    if not response_id:
        raise ValueError("response_item не содержит поле id — пиннинг формата ответа Хабра")

    # --- Полное резюме ---
    # ⚠️ ASSUMPTION — resume доступно как вложенный dict или ссылка в поле "resume"
    resume_raw = response_item.get("resume") or {}
    resume_ref = None
    if isinstance(resume_raw, dict):
        # ⚠️ ASSUMPTION — resume в отклике = dict с полями резюме ИЛИ содержит {id/url}
        resume_ref = resume_raw.get("id") or resume_raw.get("url")
        # Если resume_raw уже полное резюме (есть поля first_name/name) — используем как есть
        if not resume_raw.get("first_name") and not resume_raw.get("name") and resume_ref:
            try:
                full = await habr_client.get_resume(access_token, str(resume_ref))
                if isinstance(full, dict):
                    resume_raw = full
            except Exception as exc:
                logger.warning(
                    "[habr] get_resume failed for ref=%s: %s (used response_item.resume)",
                    resume_ref, exc,
                )
    elif isinstance(resume_raw, str) and resume_raw.strip():
        # ⚠️ ASSUMPTION — resume может быть URL/ID строкой
        resume_ref = resume_raw
        try:
            full = await habr_client.get_resume(access_token, resume_ref)
            if isinstance(full, dict):
                resume_raw = full
        except Exception as exc:
            logger.warning(
                "[habr] get_resume failed for ref=%s: %s (no resume data)",
                resume_ref, exc,
            )
            resume_raw = {}

    normalized = _habr_resume_to_normalized(resume_raw)
    phone = normalized.get("phone")   # уже normalize_phone или None
    email = normalized.get("email")
    first_name = normalized.get("first_name") or ""
    last_name = normalized.get("last_name") or ""
    middle_name = normalized.get("middle_name")
    city = normalized.get("city")
    title = normalized.get("title")

    # --- Существующая заявка по habr_response_id? ---
    existing_app = (await session.execute(
        select(Application).where(
            Application.habr_response_id == response_id,
            Application.company_id == company_id,
        )
    )).scalar_one_or_none()

    if existing_app:
        candidate = await session.get(Candidate, existing_app.candidate_id)
        is_new = candidate is None
        if candidate is None:
            candidate = Candidate(company_id=company_id, source="habr", first_name="Неизвестно", last_name="")
            session.add(candidate)
    else:
        # --- Дедуп кандидата по телефону/email (company-scoped) ---
        duplicates = await find_duplicate_candidates(session, company_id, phone, email)
        if duplicates:
            candidate = duplicates[0]
            is_new = False
        else:
            candidate = Candidate(company_id=company_id, source="habr", first_name="Неизвестно", last_name="")
            session.add(candidate)
            is_new = True

    # --- Обновить поля кандидата (не затираем непустым пустым) ---
    candidate.first_name = first_name or candidate.first_name or "Неизвестно"
    candidate.last_name = last_name or candidate.last_name or ""
    if middle_name:
        candidate.middle_name = middle_name
    if city:
        candidate.city = city[:120]
    if phone:
        candidate.phone = phone  # уже нормализован (цифры без '+')
    if email:
        candidate.email = email[:255]
    if title:
        candidate.last_position = title[:255]
    # Источник/external проставляем ТОЛЬКО НОВОМУ кандидату (созданному из этого Habr-отклика).
    # Дедуп-матч существующего кандидата из ДРУГОГО источника (hh/ручной) — его origin НЕ переписываем.
    if is_new:
        candidate.source = "habr"
        candidate.external_source = "habr"
        if resume_ref:
            candidate.external_id = str(resume_ref)[:120]

    await session.flush()

    # --- Секции резюме ---
    # is_new → добавляем секции из Habr-резюме.
    # existing_app (ре-полл того же Habr-отклика) → обновляем (delete+add).
    # дедуп-матч существующего кандидата из ДРУГОГО источника на новом отклике → секции НЕ трогаем
    # (иначе дубль или затирание чужих данных — баг ревью, фикс v0.9.119).
    if is_new:
        for row in _build_habr_resume_sections(candidate.id, company_id, normalized):
            session.add(row)
    elif existing_app:
        await session.execute(delete(CandidateExperience).where(CandidateExperience.candidate_id == candidate.id))
        await session.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id))
        await session.execute(delete(CandidateEducation).where(CandidateEducation.candidate_id == candidate.id))
        for row in _build_habr_resume_sections(candidate.id, company_id, normalized):
            session.add(row)

    # --- Application (создать или оставить) ---
    now = datetime.now(timezone.utc)

    if existing_app is None:
        application = Application(
            company_id=company_id,
            candidate_id=candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            habr_response_id=response_id,
            created_at=now,
            selected_at=now,
        )
        session.add(application)
    else:
        application = existing_app
    await session.flush()

    # --- Аудит ---
    action = "habr_response_imported" if existing_app is None else "habr_response_updated"
    await audit(
        session,
        action=action,
        entity_type="application",
        entity_id=application.id,
        after={
            "candidate_name": f"{first_name} {last_name}".strip(),
            "habr_response_id": response_id,
            "stage": "response",
        },
        actor_type="system",
        actor_user_id=None,
        company_id=company_id,
    )

    return "created" if existing_app is None else "updated"


# ---------------------------------------------------------------------------
# poll_habr_responses_now — зеркало hh.service.poll_responses_now
# ---------------------------------------------------------------------------

async def poll_habr_responses_now(session: AsyncSession, company_id: UUID) -> dict:
    """Ручной забор откликов с Хабр Карьера для привязанных вакансий компании.

    Зеркало poll_responses_now (hh). Тот же паттерн:
    - Проверить подключение и получить валидный токен.
    - Найти вакансии с habr_vacancy_id (company-scoped).
    - Собрать set уже импортированных habr_response_id (дедуп без фетча резюме).
    - По каждой вакансии: get_vacancy_responses → import_habr_response для новых.

    Возврат: {imported, skipped, updated, vacancies, errors}

    Raises:
        ValidationError: интеграция не подключена, токен протух.
    """
    # --- Проверить подключение и получить токен ---
    # get_valid_access_token_habr кидает ValidationError если нет/истёк
    access_token = await get_valid_access_token_habr(session, company_id)

    # --- Найти вакансии с habr_vacancy_id ---
    vacancies_result = await session.execute(
        select(Vacancy).where(
            Vacancy.company_id == company_id,
            Vacancy.habr_vacancy_id.isnot(None),
        )
    )
    vacancies = vacancies_result.scalars().all()

    # --- Дедуп: set уже импортированных habr_response_id этой компании ---
    existing_rows = await session.execute(
        select(Application.habr_response_id).where(
            Application.company_id == company_id,
            Application.habr_response_id.isnot(None),
        )
    )
    existing_rids = {str(r[0]) for r in existing_rows if r[0] is not None}

    stats: dict = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "vacancies": len(vacancies),
        "errors": [],
    }

    for vacancy in vacancies:
        page = 0
        while True:
            try:
                data = await habr_client.get_vacancy_responses(
                    access_token,
                    vacancy.habr_vacancy_id,
                    page=page,
                    per_page=50,
                )
            except Exception as exc:
                err_msg = str(exc)
                logger.warning(
                    "[habr] poll: ошибка get_vacancy_responses вакансия=%s: %s",
                    vacancy.habr_vacancy_id, err_msg,
                )
                stats["errors"].append({
                    "vacancy_id": str(vacancy.id),
                    "habr_vacancy_id": vacancy.habr_vacancy_id,
                    "error": err_msg,
                })
                break  # не падаем — продолжаем следующую вакансию

            # ⚠️ ASSUMPTION — структура ответа: {items: [...], total: N, per_page: N, page: N}
            items = data.get("items") or []
            if not items:
                break

            for item in items:
                # ⚠️ ASSUMPTION — id отклика в поле "id"
                rid = str(item.get("id") or "").strip()
                if not rid:
                    logger.warning("[habr] poll: response_item без id — пропускаем")
                    stats["skipped"] += 1
                    continue

                if rid in existing_rids:
                    stats["skipped"] += 1
                    continue

                try:
                    result = await import_habr_response(
                        session, company_id, vacancy, item, access_token
                    )
                    if result == "created":
                        stats["imported"] += 1
                        existing_rids.add(rid)
                    elif result == "updated":
                        stats["updated"] += 1
                except Exception as imp_exc:
                    logger.warning(
                        "[habr] сбой import_habr_response rid=%s: %s",
                        rid, imp_exc,
                    )
                    stats["skipped"] += 1

            # ⚠️ ASSUMPTION — пагинация: проверяем total и per_page
            total = data.get("total") or 0
            per_page = data.get("per_page") or 50
            if not total or (page + 1) * per_page >= total:
                break
            page += 1

    return stats


# ---------------------------------------------------------------------------
# link_habr_vacancy / unlink_habr_vacancy — зеркало hh.service.link_vacancy
# ---------------------------------------------------------------------------

async def link_habr_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    habr_vacancy_id: str,
    company_id: UUID,
    user_id: UUID,
) -> None:
    """Привязывает вакансию Глафиры к вакансии Хабр Карьера.

    Зеркало hh.service.link_vacancy. company-scoped.

    Raises:
        NotFoundError: вакансия не найдена в рамках компании.
    """
    from ....core.errors import NotFoundError

    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
        )
    )
    vacancy = result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    vacancy.habr_vacancy_id = habr_vacancy_id

    await audit(
        session,
        action="habr_vacancy_linked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"habr_vacancy_id": habr_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id,
    )


async def unlink_habr_vacancy(
    session: AsyncSession,
    vacancy_id: UUID,
    company_id: UUID,
    user_id: UUID,
) -> None:
    """Отвязывает вакансию Глафиры от Хабр Карьера.

    Raises:
        NotFoundError: вакансия не найдена в рамках компании.
    """
    from ....core.errors import NotFoundError

    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
        )
    )
    vacancy = result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    old_habr_vacancy_id = vacancy.habr_vacancy_id
    vacancy.habr_vacancy_id = None

    await audit(
        session,
        action="habr_vacancy_unlinked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        before={"habr_vacancy_id": old_habr_vacancy_id},
        after={"habr_vacancy_id": None},
        actor_user_id=user_id,
        company_id=company_id,
    )
