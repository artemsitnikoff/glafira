"""Синхронизация откликов Авито Работа → воронка Глафиры.

Зеркалит паттерн habr/hh-синхронизации.

Ключевые отличия от Хабра:
- OAuth: client_credentials (не браузерный флоу) — токен рефрешится автоматически.
- Телефон БЕСПЛАТНО в отклике (contacts.phones или enriched_properties.phone).
  НЕ нужно дёргать /contacts (это платно и не делаем).
- Два эндпоинта: get_application_ids (пагинация) → get_applications_by_ids (детали, батч ≤100).
- Опциональное обогащение резюме: GET /job/v2/resumes/{resume_id} (best-effort).

Структура отклика (из Swagger Авито Job API):
  apply: {
    id, vacancy_id, created_at, state,
    applicant: {
      data: {first_name, last_name, patronymic, birthday, citizenship, education, gender},
      resume_id
    },
    contacts: {phones: [{value}], chat: {value}},
    enriched_properties: {phone: {value}, experience, age, citizenship}
  }

Телефон: contacts.phones[].value (формат 72002000014) ИЛИ
         enriched_properties.phone.value (+79213223344) — оба через normalize_phone.

⚠️ НЕ вызывать /job/v1/resumes/... (поиск/платно).
⚠️ НЕ вызывать /contacts (телефон уже в отклике).
⚠️ company_id ВЕЗДЕ: все объекты строго company-scoped.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import (
    Vacancy,
    Application,
    Candidate,
    CandidateExperience,
    CandidateSkill,
    CandidateEducation,
)
from ....services.audit import audit
from ....services.candidate_dedup import find_duplicate_candidates
from ....services.phone import normalize_phone
from ....core.errors import ValidationError
from .service import get_valid_access_token
from . import client as avito_client

logger = logging.getLogger(__name__)

# Дата по умолчанию для первого poll — 90 дней назад
_DEFAULT_DAYS_BACK = 90


# ---------------------------------------------------------------------------
# Маппер отклика Авито → нормализованный dict
# ---------------------------------------------------------------------------

def _avito_application_to_normalized(apply: dict) -> dict:
    """Привести Авито-отклик к нормализованному dict.

    Структура apply (из Swagger):
      applicant.data: {first_name, last_name, patronymic, birthday, citizenship,
                       education, gender}
      applicant.resume_id: str | None
      contacts.phones[].value: строка с номером (72002000014)
      enriched_properties.phone.value: строка (+79213223344) — запасной источник

    Телефон извлекается из contacts.phones[].value ИЛИ enriched_properties.phone.value
    — оба формата обрабатываются через normalize_phone.

    ⚠️ НЕ вызывать /contacts — телефон уже здесь, БЕСПЛАТНО.
    """
    applicant = apply.get("applicant") or {}
    data = applicant.get("data") or {}

    # --- ФИО ---
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    middle_name = (data.get("patronymic") or "").strip() or None

    # --- Телефон (БЕСПЛАТНО в отклике, оба формата → normalize_phone) ---
    phone: Optional[str] = None

    # Приоритет 1: contacts.phones[].value
    contacts = apply.get("contacts") or {}
    phones_list = contacts.get("phones") or []
    for ph_obj in phones_list:
        if isinstance(ph_obj, dict):
            val = (ph_obj.get("value") or "").strip()
        elif isinstance(ph_obj, str):
            val = ph_obj.strip()
        else:
            continue
        if val:
            normalized = normalize_phone(val)
            if normalized:
                phone = normalized
                break

    # Запасной источник: enriched_properties.phone.value
    if not phone:
        enriched = apply.get("enriched_properties") or {}
        ep_phone = enriched.get("phone") or {}
        ep_val = ""
        if isinstance(ep_phone, dict):
            ep_val = (ep_phone.get("value") or "").strip()
        elif isinstance(ep_phone, str):
            ep_val = ep_phone.strip()
        if ep_val:
            phone = normalize_phone(ep_val)

    # --- resume_id (для обогащения v2) ---
    resume_id: Optional[str] = (applicant.get("resume_id") or "").strip() or None

    # --- extra из enriched_properties ---
    enriched = apply.get("enriched_properties") or {}
    extra_data: dict = {}
    experience_raw = enriched.get("experience")
    age_raw = enriched.get("age")
    citizenship_raw = enriched.get("citizenship")

    if experience_raw is not None:
        extra_data["avito_experience"] = experience_raw
    if age_raw is not None:
        extra_data["age"] = age_raw
    if citizenship_raw:
        extra_data["citizenship"] = citizenship_raw

    # --- ЗП: в отклике нет — заполняется из резюме v2 ---
    salary_from: Optional[int] = None
    currency: str = "RUB"

    return {
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "phone": phone,  # БЕСПЛАТНО из отклика
        "email": None,   # email в отклике Авито нет
        "title": None,   # берётся из резюме v2 если доступно
        "salary_from": salary_from,
        "salary_to": None,
        "currency": currency,
        "experience": [],   # заполняется из resume v2
        "skill_set": [],    # заполняется из resume v2
        "education": {"primary": []},  # заполняется из resume v2
        "extra": extra_data,
        "resume_id": resume_id,
    }


def _enrich_normalized_from_resume_v2(normalized: dict, resume_data: dict) -> dict:
    """Обогатить нормализованный dict данными из резюме v2 (GET /job/v2/resumes/{id}).

    resume_data (из Swagger /job/v2/resumes/{resume_id}):
      experience_list: [{work_start, work_finish, company, position, responsibilities}]
      education_list: [{name, faculty, specialization, year_of_graduation}]
      language_list: [{language, proficiency}]
      salary: {amount, currency}
      description: str (резюме/summary)

    Обогащение best-effort — не перезаписывает уже заполненные поля.
    """
    # Опыт
    raw_exp = resume_data.get("experience_list") or []
    experience: list[dict] = []
    for exp in raw_exp:
        if not isinstance(exp, dict):
            continue
        position = (exp.get("position") or "").strip()
        company = (exp.get("company") or "").strip() or None
        start = (exp.get("work_start") or "").strip() or None
        end = (exp.get("work_finish") or "").strip() or None
        description = (exp.get("responsibilities") or "").strip() or None
        experience.append({
            "position": position,
            "company": company,
            "start": start,
            "end": end,
            "description": description,
        })
    if experience:
        normalized["experience"] = experience

    # Образование
    raw_edu = resume_data.get("education_list") or []
    primary: list[dict] = []
    for ed in raw_edu:
        if not isinstance(ed, dict):
            continue
        name = (ed.get("name") or "").strip()
        if not name:
            continue
        faculty = (ed.get("faculty") or ed.get("specialization") or "").strip() or None
        year = str(ed.get("year_of_graduation") or "")[:4] or None
        primary.append({"name": name, "organization": faculty, "result": "", "year": year})
    if primary:
        normalized["education"] = {"primary": primary}

    # Должность из description (краткое описание → last_position)
    description = (resume_data.get("description") or "").strip()
    if description and not normalized.get("title"):
        # Берём первую строку как желаемую должность
        first_line = description.splitlines()[0].strip() if "\n" in description else ""
        if first_line and len(first_line) <= 255:
            normalized["title"] = first_line

    # ЗП
    salary_obj = resume_data.get("salary") or {}
    if isinstance(salary_obj, dict):
        amount = salary_obj.get("amount")
        curr = (salary_obj.get("currency") or "RUB").upper()
        if amount is not None:
            try:
                normalized["salary_from"] = int(amount)
                normalized["currency"] = curr
            except (TypeError, ValueError):
                pass

    return normalized


def _build_avito_resume_sections(
    candidate_id: UUID,
    company_id: UUID,
    normalized: dict,
) -> list:
    """Строит ORM-объекты секций резюме из нормализованного dict.

    Переиспользует hh-маппер build_candidate_resume_sections.
    """
    # Отложенный импорт для предотвращения циклов
    from ...integrations.hh.service import build_candidate_resume_sections
    return build_candidate_resume_sections(candidate_id, company_id, normalized)


# ---------------------------------------------------------------------------
# import_avito_application — основная функция импорта одного отклика
# ---------------------------------------------------------------------------

async def import_avito_application(
    session: AsyncSession,
    company_id: UUID,
    vacancy: "Vacancy",
    apply: dict,
    access_token: str,
    employee_of: Optional[str] = None,
) -> str:
    """Импорт ИЛИ обновление одного Авито-отклика. Возвращает 'created' | 'updated'.

    Логика:
    1. avito_application_id = apply.id.
    2. Дедуп отклика: Application(avito_application_id, company_id) уже есть → updated.
    3. Нормализация: _avito_application_to_normalized (ФИО, телефон БЕСПЛАТНО, resume_id).
    4. Опциональное обогащение: get_resume_v2(resume_id) best-effort → секции.
    5. Дедуп кандидата: find_duplicate_candidates(phone, None) company-scoped.
    6. Candidate(source='avito', phone=normalize_phone, company_id).
    7. Application(stage='response', avito_application_id, company_id, vacancy_id).
    8. audit actor_type='system'. company_id ВЕЗДЕ.

    ⚠️ Телефон В ОТКЛИКЕ (contacts.phones / enriched_properties.phone) — не /contacts.
    ⚠️ company_id на ВСЕХ создаваемых объектах.
    """
    # --- avito_application_id ---
    avito_app_id = str(apply.get("id") or "").strip()
    if not avito_app_id:
        raise ValueError("apply не содержит поле id")

    # --- Дедуп отклика ---
    existing_app = (await session.execute(
        select(Application).where(
            Application.avito_application_id == avito_app_id,
            Application.company_id == company_id,
        )
    )).scalar_one_or_none()

    # --- Нормализация базовых полей ---
    normalized = _avito_application_to_normalized(apply)
    first_name = normalized.get("first_name") or ""
    last_name = normalized.get("last_name") or ""
    middle_name = normalized.get("middle_name")
    phone = normalized.get("phone")   # normalize_phone уже применён
    title = normalized.get("title")
    salary_from = normalized.get("salary_from")
    currency = normalized.get("currency") or "RUB"
    extra_data = normalized.get("extra") or {}
    resume_id = normalized.get("resume_id")

    # --- Опциональное обогащение из резюме v2 (best-effort) ---
    if resume_id:
        try:
            resume_data = await avito_client.get_resume_v2(access_token, resume_id, employee_of)
            normalized = _enrich_normalized_from_resume_v2(normalized, resume_data)
            # Обновить после обогащения
            title = normalized.get("title") or title
            salary_from = normalized.get("salary_from") or salary_from
            currency = normalized.get("currency") or currency
        except Exception as exc:
            # Не падать при сбое обогащения
            logger.warning(
                "[avito] не удалось обогатить резюме resume_id=%s: %s",
                resume_id, exc,
            )

    is_new: bool
    candidate: Candidate

    if existing_app:
        # Обновление существующего
        cand = await session.get(Candidate, existing_app.candidate_id)
        if cand is None:
            # Defensive (штатно недостижимо — applications.candidate_id ON DELETE CASCADE):
            # пересоздаём кандидата И переназначаем на него отклик, чтобы не оставить битую ссылку.
            cand = Candidate(
                company_id=company_id, source="avito",
                first_name="Неизвестно", last_name="",
            )
            session.add(cand)
            await session.flush()
            existing_app.candidate_id = cand.id
            is_new = True
        else:
            is_new = False
        candidate = cand
    else:
        # --- Дедуп кандидата по телефону ---
        candidate_by_phone: Optional[Candidate] = None
        if phone:
            duplicates = await find_duplicate_candidates(session, company_id, phone, None)
            if duplicates:
                candidate_by_phone = duplicates[0]

        if candidate_by_phone:
            candidate = candidate_by_phone
            is_new = False
        else:
            # Новый кандидат
            candidate = Candidate(
                company_id=company_id, source="avito",
                first_name="Неизвестно", last_name="",
            )
            session.add(candidate)
            is_new = True

    # --- Обновить поля кандидата (не затираем непустым пустым) ---
    candidate.first_name = first_name or candidate.first_name or "Неизвестно"
    candidate.last_name = last_name or candidate.last_name or ""
    if middle_name:
        candidate.middle_name = middle_name
    if phone and not candidate.phone:
        candidate.phone = phone
    if title:
        candidate.last_position = title[:255]
    if salary_from is not None:
        candidate.salary_from = salary_from
        candidate.salary_expectation = salary_from  # синхронизация по invariant §salary-range
        candidate.currency = currency

    # Источник и external-id — ТОЛЬКО новому кандидату
    if is_new:
        candidate.source = "avito"
        candidate.external_source = "avito"
        if resume_id:
            candidate.external_id = resume_id[:120]
        # extra
        if extra_data:
            current_extra = dict(candidate.extra or {})
            current_extra.update(extra_data)
            candidate.extra = current_extra

    await session.flush()

    # --- Секции резюме ---
    if is_new:
        for row in _build_avito_resume_sections(candidate.id, company_id, normalized):
            session.add(row)
    elif existing_app:
        # Ре-полл того же отклика → обновляем секции
        from sqlalchemy import delete
        await session.execute(
            delete(CandidateExperience).where(CandidateExperience.candidate_id == candidate.id)
        )
        await session.execute(
            delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id)
        )
        await session.execute(
            delete(CandidateEducation).where(CandidateEducation.candidate_id == candidate.id)
        )
        for row in _build_avito_resume_sections(candidate.id, company_id, normalized):
            session.add(row)

    # --- Application ---
    now = datetime.now(timezone.utc)

    if existing_app is None:
        application = Application(
            company_id=company_id,
            candidate_id=candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            avito_application_id=avito_app_id,
            created_at=now,
            selected_at=now,
        )
        session.add(application)
    else:
        application = existing_app

    await session.flush()

    # --- Аудит ---
    action = "avito_application_imported" if existing_app is None else "avito_application_updated"
    await audit(
        session,
        action=action,
        entity_type="application",
        entity_id=application.id,
        after={
            "candidate_name": f"{first_name} {last_name}".strip() or "Неизвестно",
            "avito_application_id": avito_app_id,
            "phone_found": phone is not None,
            "stage": "response",
        },
        actor_type="system",
        actor_user_id=None,
        company_id=company_id,
    )

    return "created" if existing_app is None else "updated"


# ---------------------------------------------------------------------------
# poll_avito_responses_now — главная функция поллинга
# ---------------------------------------------------------------------------

async def poll_avito_responses_now(session: AsyncSession, company_id: UUID) -> dict:
    """Ручной или cron-забор откликов с Авито для привязанных вакансий компании.

    Паттерн: get_valid_access_token → вакансии с avito_vacancy_id → пагинация
    get_application_ids (vacancyIds-фильтр) → батчами ≤100 get_applications_by_ids
    → import_avito_application для новых id.

    Дедуп: set существующих avito_application_id (company-scoped) — не фетчит резюме
    повторно для уже импортированных.

    Возврат: {imported, updated, skipped, vacancies, errors}

    Raises:
        ValidationError: нет client_id/secret (не подключено), 402/ошибка токена.
    """
    # Токен (кэш или рефреш)
    access_token, employee_of = await get_valid_access_token(session, company_id)

    # Найти вакансии с avito_vacancy_id
    vacancies_result = await session.execute(
        select(Vacancy).where(
            Vacancy.company_id == company_id,
            Vacancy.avito_vacancy_id.isnot(None),
        )
    )
    vacancies = vacancies_result.scalars().all()

    if not vacancies:
        return {
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "vacancies": 0,
            "errors": [],
        }

    # Дедуп: set уже импортированных avito_application_id
    existing_rows = await session.execute(
        select(Application.avito_application_id).where(
            Application.company_id == company_id,
            Application.avito_application_id.isnot(None),
        )
    )
    existing_aids = {str(r[0]) for r in existing_rows if r[0] is not None}

    # Карта avito_vacancy_id → Vacancy для быстрого поиска
    vacancy_map: dict[str, Vacancy] = {v.avito_vacancy_id: v for v in vacancies}
    avito_vac_ids = list(vacancy_map.keys())

    stats: dict = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "vacancies": len(vacancies),
        "errors": [],
    }

    # Дата поллинга — 90 дней назад (первый запуск) или можно вычислять по min(created_at)
    date_from = (
        datetime.now(timezone.utc) - timedelta(days=_DEFAULT_DAYS_BACK)
    ).strftime("%Y-%m-%d")

    # --- Пагинация get_application_ids ---
    cursor: Optional[str] = None
    new_ids: list[str] = []

    while True:
        try:
            ids_data = await avito_client.get_application_ids(
                access_token,
                date_from=date_from,
                cursor=cursor,
                vacancy_ids=avito_vac_ids,
                employee_of=employee_of,
            )
        except ValueError as exc:
            err_str = str(exc)
            logger.warning("[avito] poll get_application_ids: %s", exc)
            stats["errors"].append({"step": "get_application_ids", "error": err_str})
            break

        applies_page = ids_data.get("applies") or []
        for apply_id_obj in applies_page:
            aid = str(apply_id_obj.get("id") or "").strip()
            if aid and aid not in existing_aids:
                new_ids.append(aid)

        # cursor-пагинация: если нет cursor в ответе или applies пуст — конец
        cursor = ids_data.get("cursor") or None
        if not cursor or not applies_page:
            break

    # --- Батчами ≤100 get_applications_by_ids → import ---
    batch_size = 100
    for i in range(0, len(new_ids), batch_size):
        batch = new_ids[i : i + batch_size]

        try:
            apps_data = await avito_client.get_applications_by_ids(
                access_token, batch, employee_of=employee_of
            )
        except ValueError as exc:
            err_str = str(exc)
            logger.warning("[avito] poll get_applications_by_ids batch error: %s", exc)
            stats["errors"].append({"step": "get_applications_by_ids", "error": err_str})
            continue

        applies = apps_data.get("applies") or []
        for apply in applies:
            aid = str(apply.get("id") or "").strip()
            if not aid:
                stats["skipped"] += 1
                continue

            if aid in existing_aids:
                stats["skipped"] += 1
                continue

            # Найти вакансию по avito_vacancy_id из отклика
            avito_vac_id = str(apply.get("vacancy_id") or "").strip()
            vacancy = vacancy_map.get(avito_vac_id)
            if vacancy is None:
                logger.warning(
                    "[avito] poll: отклик id=%s — vac_id=%s не привязана, пропуск",
                    aid, avito_vac_id,
                )
                stats["skipped"] += 1
                continue

            try:
                result = await import_avito_application(
                    session, company_id, vacancy, apply, access_token, employee_of
                )
                if result == "created":
                    stats["imported"] += 1
                    existing_aids.add(aid)
                elif result == "updated":
                    stats["updated"] += 1
            except Exception as imp_exc:
                logger.warning(
                    "[avito] import_avito_application aid=%s: %s",
                    aid, imp_exc,
                )
                stats["skipped"] += 1

    return stats
