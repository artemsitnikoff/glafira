"""Синхронизация откликов с Хабр Карьера → воронка Глафиры.

Зеркалит паттерн hh-синхронизации (import_response / poll_responses_now / link_vacancy).
Маппинг response.user Хабра → нормализованный dict — в _habr_response_user_to_normalized().

ВАЖНО: вся инфраструктура (дедуп, Application, normalize_phone, company-изоляция, audit)
РЕАЛЬНАЯ и тестируется с мок-клиентом.

Структура отклика (подтверждена документацией Хабр Карьера):
  response: { id, vacancy_id, body, favorite, archived, created_at, user }
  response.user: { login, name, avatar, birthday, specialization,
                   skills[{title, alias_name}], experience_total{month},
                   relocation, remote, compensation{value, currency},
                   work_state, age, location{city, country},
                   experiences[{company, position, period}],
                   educations[{university, faculty, start_date, end_date}] }
  NB: phone/email в response.user ОТСУТСТВУЮТ — только через платный /users/{login}/contacts.
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
# Маппер response.user Хабра → нормализованный dict
# ---------------------------------------------------------------------------

def _habr_response_user_to_normalized(user: dict) -> dict:
    """Приводит response.user из Хабр-отклика к нормализованному dict.

    Поля response.user (подтверждены документацией):
      login, name, avatar, birthday, specialization,
      skills[{title, alias_name}], experience_total{month},
      relocation, remote, compensation{value, currency}, work_state, age,
      location{city, country},
      experiences[{company, position, period}],
      educations[{university, faculty, start_date, end_date}]

    ⚠️ phone/email в response.user ОТСУТСТВУЮТ (только через платный /contacts).
    Кандидат создаётся БЕЗ контактов. Для получения контактов — open_habr_contacts().
    """
    # --- ФИО из поля name (формат: «Фамилия Имя» или «Имя Фамилия») ---
    full_name = (user.get("name") or "").strip()
    parts = full_name.split() if full_name else []
    last_name = parts[0] if len(parts) >= 1 else ""
    first_name = parts[1] if len(parts) >= 2 else ""
    middle_name = parts[2] if len(parts) >= 3 else None

    # --- Город ---
    location = user.get("location") or {}
    if isinstance(location, dict):
        city = (location.get("city") or "").strip() or None
    else:
        city = None

    # --- Желаемая должность ---
    title = (user.get("specialization") or "").strip() or None

    # --- Зарплатные ожидания ---
    compensation = user.get("compensation") or {}
    salary_from: Optional[int] = None
    currency: str = "RUB"
    if isinstance(compensation, dict):
        val = compensation.get("value")
        try:
            salary_from = int(val) if val is not None else None
        except (TypeError, ValueError):
            salary_from = None
        curr = (compensation.get("currency") or "").upper()
        if curr:
            currency = curr

    # --- Опыт (experiences[{company, position, period}]) ---
    # period — строка (например «Январь 2020 — Декабрь 2023»); храним as-is
    raw_experiences = user.get("experiences") or []
    experience: list[dict] = []
    for exp in raw_experiences:
        if not isinstance(exp, dict):
            continue
        pos = (exp.get("position") or "").strip()
        comp = (exp.get("company") or "").strip() or None
        period = (exp.get("period") or "").strip() or None
        experience.append({
            "position": pos,
            "company": comp,
            # start/end неизвестны из period-строки → передаём None, period — в company-field
            "start": None,
            "end": None,
            "description": period,  # period-строку сохраняем как description
        })

    # --- Навыки (skills[{title, alias_name}]) ---
    raw_skills = user.get("skills") or []
    skill_set: list[str] = []
    for sk in raw_skills:
        if isinstance(sk, dict):
            name = (sk.get("title") or sk.get("alias_name") or "").strip()
            if name:
                skill_set.append(name)
        elif isinstance(sk, str) and sk.strip():
            skill_set.append(sk.strip())

    # --- Образование (educations[{university, faculty, start_date, end_date}]) ---
    raw_educations = user.get("educations") or []
    education_primary: list[dict] = []
    for ed in raw_educations:
        if not isinstance(ed, dict):
            continue
        inst = (ed.get("university") or "").strip()
        if not inst:
            continue
        faculty = (ed.get("faculty") or "").strip() or None
        # Год окончания из end_date (строка «YYYY-MM-DD» или просто «YYYY»)
        end_date = ed.get("end_date") or ""
        year: Optional[str] = str(end_date)[:4] if end_date else None
        education_primary.append({
            "name": inst,
            "organization": faculty,
            "result": "",
            "year": year,
        })

    # --- extra: дополнительные поля из user ---
    extra_data: dict = {}
    experience_total = user.get("experience_total") or {}
    if isinstance(experience_total, dict) and experience_total.get("month") is not None:
        extra_data["experience_total_month"] = experience_total["month"]
    work_state = user.get("work_state")
    if work_state:
        extra_data["work_state"] = work_state
    age = user.get("age")
    if age is not None:
        extra_data["age"] = age

    return {
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "city": city,
        "phone": None,           # контактов в отклике НЕТ (только /contacts, платно)
        "email": None,           # контактов в отклике НЕТ (только /contacts, платно)
        "title": title,
        "salary_from": salary_from,
        "currency": currency,
        "experience": experience,
        "skill_set": skill_set,
        "education": {"primary": education_primary},
        "extra": extra_data,
    }


# ---------------------------------------------------------------------------
# Вспомогательная функция построения секций резюме
# ---------------------------------------------------------------------------

def _build_habr_resume_sections(
    candidate_id: UUID,
    company_id: UUID,
    normalized: dict,
) -> list:
    """Строит ORM-объекты секций резюме из нормализованного dict.

    Переиспользует hh-маппер build_candidate_resume_sections.
    """
    from ...integrations.hh.service import build_candidate_resume_sections
    return build_candidate_resume_sections(candidate_id, company_id, normalized)


# ---------------------------------------------------------------------------
# Получение валидного access_token Хабра (per-company)
# ---------------------------------------------------------------------------

async def get_valid_access_token_habr(session: AsyncSession, company_id: UUID) -> str:
    """Возвращает расшифрованный access_token из HabrIntegration.

    Если токен истёк — честная ValidationError «переподключите Хабр», не 500.

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

    if integration.expires_at:
        now = datetime.now(timezone.utc)
        expires_at = integration.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now >= expires_at:
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

    Структура response_item (подтверждена документацией):
      { id, vacancy_id, body, favorite, archived, created_at, user }
      response.user содержит профиль кандидата БЕЗ контактов (phone/email отсутствуют).

    Логика:
    1. Извлечь habr_response_id = response_item.id.
    2. Если Application с этим id уже есть (company-scoped) → обновить данные кандидата.
    3. Дедуп кандидата по (external_source='habr', external_id=user.login) — company-scoped.
    4. Если не найден по login: дедуп по телефону/email (их нет в отклике — всегда None).
    5. Создать/обновить Candidate(source='habr', external_id=user.login, БЕЗ phone/email).
    6. Секции резюме (опыт/навыки/образование).
    7. Application(stage='response', habr_response_id, company_id, vacancy_id).
    8. audit.
    """
    # --- Извлечь habr_response_id ---
    response_id = str(response_item.get("id") or "").strip()
    if not response_id:
        raise ValueError("response_item не содержит поле id")

    # --- Данные пользователя из отклика ---
    user = response_item.get("user") or {}
    login = (user.get("login") or "").strip()

    normalized = _habr_response_user_to_normalized(user)
    first_name = normalized.get("first_name") or ""
    last_name = normalized.get("last_name") or ""
    middle_name = normalized.get("middle_name")
    city = normalized.get("city")
    title = normalized.get("title")
    salary_from = normalized.get("salary_from")
    currency = normalized.get("currency") or "RUB"
    extra_data = normalized.get("extra") or {}

    # phone/email в отклике ОТСУТСТВУЮТ — они None
    # (контакты открываются отдельно через open_habr_contacts)

    # --- Существующая заявка по habr_response_id? ---
    existing_app = (await session.execute(
        select(Application).where(
            Application.habr_response_id == response_id,
            Application.company_id == company_id,
        )
    )).scalar_one_or_none()

    is_new: bool
    candidate: Candidate

    if existing_app:
        cand = await session.get(Candidate, existing_app.candidate_id)
        if cand is None:
            cand = Candidate(
                company_id=company_id, source="habr",
                first_name="Неизвестно", last_name="",
            )
            session.add(cand)
            is_new = True
        else:
            is_new = False
        candidate = cand
    else:
        # --- Дедуп по (external_source='habr', external_id=login) ---
        candidate_by_login: Optional[Candidate] = None
        if login:
            result_login = await session.execute(
                select(Candidate).where(
                    Candidate.company_id == company_id,
                    Candidate.external_source == "habr",
                    Candidate.external_id == login,
                    Candidate.deleted_at.is_(None),
                )
            )
            candidate_by_login = result_login.scalar_one_or_none()

        if candidate_by_login:
            candidate = candidate_by_login
            is_new = False
        else:
            # Дедуп по телефону/email (при импорте из хабр-отклика оба None)
            duplicates = await find_duplicate_candidates(session, company_id, None, None)
            if duplicates:
                candidate = duplicates[0]
                is_new = False
            else:
                candidate = Candidate(
                    company_id=company_id, source="habr",
                    first_name="Неизвестно", last_name="",
                )
                session.add(candidate)
                is_new = True

    # --- Обновить поля кандидата (не затираем непустым пустым) ---
    candidate.first_name = first_name or candidate.first_name or "Неизвестно"
    candidate.last_name = last_name or candidate.last_name or ""
    if middle_name:
        candidate.middle_name = middle_name
    if city:
        candidate.city = city[:120]
    if title:
        candidate.last_position = title[:255]
    if salary_from is not None:
        candidate.salary_from = salary_from
        candidate.salary_expectation = salary_from  # синхронизация по invariant
        candidate.currency = currency

    # Источник/external проставляем ТОЛЬКО НОВОМУ кандидату
    if is_new:
        candidate.source = "habr"
        candidate.external_source = "habr"
        if login:
            candidate.external_id = login[:120]
        # Обновляем extra
        if extra_data:
            current_extra = dict(candidate.extra or {})
            current_extra.update(extra_data)
            candidate.extra = current_extra

    await session.flush()

    # --- Секции резюме ---
    if is_new:
        for row in _build_habr_resume_sections(candidate.id, company_id, normalized):
            session.add(row)
    elif existing_app:
        # Ре-полл того же отклика → обновляем секции
        await session.execute(
            delete(CandidateExperience).where(CandidateExperience.candidate_id == candidate.id)
        )
        await session.execute(
            delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id)
        )
        await session.execute(
            delete(CandidateEducation).where(CandidateEducation.candidate_id == candidate.id)
        )
        for row in _build_habr_resume_sections(candidate.id, company_id, normalized):
            session.add(row)
    # дедуп-матч существующего кандидата на НОВОМ отклике → секции НЕ трогаем

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
            "habr_login": login,
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

    Тот же паттерн, что hh.poll_responses_now:
    - Проверить подключение и получить валидный токен.
    - Найти вакансии с habr_vacancy_id (company-scoped).
    - Собрать set уже импортированных habr_response_id (дедуп без фетча резюме).
    - По каждой вакансии: get_vacancy_responses → import_habr_response для новых.

    Структура ответа Хабра: { responses: [...], pagination: {total, page, per} }

    Возврат: {imported, skipped, updated, vacancies, errors}

    Raises:
        ValidationError: интеграция не подключена, токен протух.
    """
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
        page = 1
        while True:
            try:
                data = await habr_client.get_vacancy_responses(
                    access_token,
                    vacancy.habr_vacancy_id,
                    page=page,
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
                break

            # Структура ответа: { responses: [...], pagination: {total, page, per} }
            items = data.get("responses") or []
            if not items:
                break

            for item in items:
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

            # Пагинация: { total, page, per }
            pagination = data.get("pagination") or {}
            total = pagination.get("total") or 0
            per = pagination.get("per") or 50
            current_page = pagination.get("page") or page
            if not total or current_page * per >= total:
                break
            page += 1

    return stats


# ---------------------------------------------------------------------------
# open_habr_contacts — ПЛАТНОЕ открытие контактов кандидата Хабра
# ---------------------------------------------------------------------------

async def open_habr_contacts(
    session: AsyncSession,
    company_id: UUID,
    candidate_id: UUID,
    user_id: UUID,
) -> dict:
    """Открыть контакты кандидата Хабра.

    ⚠️ ПЛАТНО: каждый первый вызов списывает лимит компании.
    ⚠️ ИДЕМПОТЕНТНОСТЬ: если habr_contacts_opened_at уже стоит → вернуть имеющиеся
       контакты из кандидата, НЕ вызывать /contacts повторно.

    Логика:
    1. Загрузить кандидата company-scoped; не habr / нет external_id(login) → ValidationError.
    2. Если habr_contacts_opened_at проставлен → вернуть текущие phone/email, merged=False.
    3. Иначе: get_user_contacts(token, login).
    4. Лимит/ошибка → ValidationError (честно, НЕ помечать opened).
    5. Распарсить phones/emails/messengers.
    6. ДЕДУП ПОСЛЕ ОТКРЫТИЯ: find_duplicate_candidates(phone, email) ИСКЛЮЧАЯ текущего.
       Если найден другой кандидат E (тот же человек) → СЛИЯНИЕ:
         - перенести Application(ы) хабр-кандидата на E (гард уникальности по vacancy);
         - проставить E.phone/email если пусты;
         - секции скопировать в E если у E нет;
         - soft-delete хабр-кандидата;
         - audit слияния.
       Вернуть {merged: True, candidate_id: E.id}.
    7. Если нет дубля → проставить phone/email текущему, habr_contacts_opened_at=now.
       Вернуть {merged: False, candidate_id}.
    8. audit ПЛАТНОГО открытия.

    Raises:
        ValidationError: кандидат не найден/не habr/нет login/лимит исчерпан.
    """
    from ....core.errors import NotFoundError

    # --- Загрузить кандидата company-scoped ---
    cand = (await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

    if cand is None:
        raise NotFoundError("Кандидат не найден")

    if cand.external_source != "habr" or not cand.external_id:
        raise ValidationError(
            "Открытие контактов доступно только для кандидатов, импортированных с Хабра"
        )

    login = cand.external_id

    # --- Идемпотентность: контакты уже открыты (по ORM-полю, не по extra) ---
    if cand.habr_contacts_opened_at is not None:
        return {
            "merged": False,
            "candidate_id": str(cand.id),
            "phone": cand.phone,
            "email": cand.email,
            "already_opened": True,
        }

    # --- Получить токен компании ---
    access_token = await get_valid_access_token_habr(session, company_id)

    # --- Дёрнуть /contacts (ПЛАТНО) ---
    try:
        contacts_data = await habr_client.get_user_contacts(access_token, login)
    except ValueError as exc:
        # Честная ошибка: лимит/нет доступа — НЕ помечаем как открытые
        err_msg = str(exc)
        if "402" in err_msg or "403" in err_msg or "429" in err_msg:
            raise ValidationError(
                "Лимит открытий контактов Хабра исчерпан или нет доступа к базе резюме. "
                "Проверьте тариф на Хабр Карьере."
            ) from exc
        raise ValidationError(
            f"Ошибка при открытии контактов Хабра: {exc}"
        ) from exc

    # --- Распарсить контакты ---
    phone: Optional[str] = None
    email: Optional[str] = None
    messengers_extra: list = []

    # contacts_data может быть dict с разными форматами (Хабр не уточнил схему публично)
    # Пробуем типичные варианты
    phones_list = contacts_data.get("phones") or []
    emails_list = contacts_data.get("emails") or []
    messengers_list = contacts_data.get("messengers") or []

    # Также contacts_data может содержать плоские поля phone/email
    if not phones_list and contacts_data.get("phone"):
        phones_list = [contacts_data["phone"]]
    if not emails_list and contacts_data.get("email"):
        emails_list = [contacts_data["email"]]

    # Также Хабр может вернуть список contacts[{type, value}]
    for contact in (contacts_data.get("contacts") or []):
        if not isinstance(contact, dict):
            continue
        ctype = (contact.get("type") or "").lower()
        cval = contact.get("value") or ""
        if "phone" in ctype and cval:
            phones_list.append(cval)
        elif "email" in ctype and cval:
            emails_list.append(cval)
        elif cval:
            messengers_extra.append({"type": ctype, "value": cval})

    # Нормализуем первый телефон
    for ph in phones_list:
        if ph:
            normalized_ph = normalize_phone(str(ph))
            if normalized_ph:
                phone = normalized_ph
                break

    # Берём первый email
    for em in emails_list:
        if em and isinstance(em, str) and em.strip():
            email = em.strip()[:255]
            break
    if not email and isinstance(emails_list, list):
        for item in emails_list:
            if isinstance(item, dict) and item.get("value"):
                email = str(item["value"]).strip()[:255]
                break

    # Добавляем мессенджеры из Хабра в список + дополнительные
    for msg in messengers_list:
        if isinstance(msg, dict) and msg.get("value"):
            messengers_extra.append(msg)

    now = datetime.now(timezone.utc)

    # --- audit ПЛАТНОГО открытия (до дедупа, чтобы всегда записать факт вызова) ---
    await audit(
        session,
        action="habr_contacts_opened",
        entity_type="candidate",
        entity_id=cand.id,
        after={
            "habr_login": login,
            "phone_found": phone is not None,
            "email_found": email is not None,
        },
        actor_type="human",
        actor_user_id=user_id,
        company_id=company_id,
    )

    # --- Дедуп после открытия: ищем ДРУГОГО кандидата с тем же phone/email ---
    if phone or email:
        duplicates = await find_duplicate_candidates(session, company_id, phone, email)
        # Исключаем самого хабр-кандидата из результатов
        duplicates = [d for d in duplicates if d.id != cand.id]

        if duplicates:
            # Survivor — существующий кандидат (уже в базе)
            survivor = duplicates[0]

            # Перенести Application(ы) хабр-кандидата → survivor
            habr_apps = (await session.execute(
                select(Application).where(
                    Application.candidate_id == cand.id,
                    Application.company_id == company_id,
                )
            )).scalars().all()

            for app in habr_apps:
                # Гард уникальности (candidate, vacancy): если у survivor уже есть такая заявка
                survivor_app = (await session.execute(
                    select(Application).where(
                        Application.candidate_id == survivor.id,
                        Application.vacancy_id == app.vacancy_id,
                        Application.company_id == company_id,
                    )
                )).scalar_one_or_none()

                if survivor_app is not None:
                    # Бэкфиллим habr_response_id на survivor_app, дубль-заявку удаляем
                    if app.habr_response_id and not survivor_app.habr_response_id:
                        survivor_app.habr_response_id = app.habr_response_id
                    await session.delete(app)
                else:
                    # Переносим заявку на survivor
                    app.candidate_id = survivor.id

            # Проставить phone/email survivor'у если пусты
            if phone and not survivor.phone:
                survivor.phone = phone
            if email and not survivor.email:
                survivor.email = email[:255]

            # Скопировать секции хабр-кандидата в survivor если у него нет
            survivor_has_exp = (await session.execute(
                select(CandidateExperience.id).where(
                    CandidateExperience.candidate_id == survivor.id
                ).limit(1)
            )).scalar_one_or_none()

            survivor_has_skills = (await session.execute(
                select(CandidateSkill.id).where(
                    CandidateSkill.candidate_id == survivor.id
                ).limit(1)
            )).scalar_one_or_none()

            if not survivor_has_exp:
                habr_exps = (await session.execute(
                    select(CandidateExperience).where(
                        CandidateExperience.candidate_id == cand.id
                    )
                )).scalars().all()
                for exp in habr_exps:
                    session.add(CandidateExperience(
                        company_id=company_id,
                        candidate_id=survivor.id,
                        position=exp.position,
                        company=exp.company,
                        period=exp.period,
                        description=exp.description,
                        order_index=exp.order_index,
                    ))

            if not survivor_has_skills:
                habr_skills = (await session.execute(
                    select(CandidateSkill).where(
                        CandidateSkill.candidate_id == cand.id
                    )
                )).scalars().all()
                for sk in habr_skills:
                    session.add(CandidateSkill(
                        company_id=company_id,
                        candidate_id=survivor.id,
                        skill=sk.skill,
                        order_index=sk.order_index,
                    ))

            await session.flush()

            # Soft-delete хабр-кандидата
            cand.deleted_at = now

            await session.flush()

            # audit слияния
            await audit(
                session,
                action="habr_candidate_merged",
                entity_type="candidate",
                entity_id=survivor.id,
                after={
                    "merged_habr_candidate_id": str(cand.id),
                    "habr_login": login,
                    "survivor_id": str(survivor.id),
                },
                actor_type="human",
                actor_user_id=user_id,
                company_id=company_id,
            )

            return {
                "merged": True,
                "candidate_id": str(survivor.id),
                "phone": survivor.phone,
                "email": survivor.email,
                "already_opened": False,
            }

    # --- Нет дубля → проставить контакты хабр-кандидату ---
    if phone:
        cand.phone = phone
    if email:
        cand.email = email

    # Мессенджеры: добавляем в extra
    if messengers_extra:
        current_extra = dict(cand.extra or {})
        current_extra["habr_messengers"] = messengers_extra
        cand.extra = current_extra

    # Пометить контакты как открытые (ORM-поле)
    cand.habr_contacts_opened_at = now

    await session.flush()

    return {
        "merged": False,
        "candidate_id": str(cand.id),
        "phone": cand.phone,
        "email": cand.email,
        "already_opened": False,
    }


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
    """Привязывает вакансию Глафиры к вакансии Хабр Карьера. company-scoped.

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
