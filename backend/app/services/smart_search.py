"""Сервис умного подбора кандидатов через hh.ru"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..models import (
    SmartSearchRun, Vacancy, Candidate, Application, AuditLog, Company
)
from ..schemas.smart import (
    SmartSearchRequest, SmartVacancyItem, InvitedCandidate
)
from ..core.errors import ValidationError, NotFoundError
from ..services.integrations.hh import service as hh_service
from ..services.integrations.hh import client as hh_client
from ..services.glafira.scoring import score_resume_dict, _strip_html
from ..services.glafira.client import call_json
from ..core.errors import GlafiraParseError
from ..services.audit import audit

logger = logging.getLogger(__name__)

# Глобальное хранилище для активных задач (предотвращает GC)
_active_tasks = {}


def _parse_api_quota(quota_data) -> tuple[bool, int, bool]:
    """Парсит ответ get_payable_api_actions по реальной схеме OpenAPI.

    Args:
        quota_data: сырой ответ {items:[...]} или legacy формат

    Returns:
        (unlimited, limited_remaining, has_service):
            unlimited: есть API_UNLIMITED (balance=null)
            limited_remaining: остаток запросов по API_LIMITED (если есть)
            has_service: есть хотя бы одна API-услуга
    """
    items = quota_data.get("items", []) if isinstance(quota_data, dict) else (quota_data or [])
    unlimited = False
    limited_remaining = 0
    has_service = False

    for item in items:
        if not isinstance(item, dict):
            continue

        service_type = item.get("service_type") or {}
        service_id = service_type.get("id") or ""

        if service_id == "API_UNLIMITED":
            unlimited = True
            has_service = True
        elif service_id == "API_LIMITED":
            has_service = True
            balance = item.get("balance") or {}
            actual = balance.get("actual") or 0
            limited_remaining += int(actual)

    return unlimited, limited_remaining, has_service


async def check_access(session: AsyncSession, company_id: UUID) -> tuple[bool, bool, Optional[str]]:
    """
    Проверяет доступ к умному подбору

    Returns:
        tuple[bool, bool, str|None]: (has_access, has_paid_access, reason)
        has_access: hh подключён (валидный токен + employer_id)
        has_paid_access: есть платный доступ к базе резюме (для приглашений)
    """
    try:
        # Проверяем подключение hh.ru
        access_token = await hh_service.get_valid_access_token(session, company_id)

        # Получаем информацию о пользователе для employer_id
        me_data = await hh_client.get_me(access_token)
        employer_id = me_data.get("employer", {}).get("id")

        if not employer_id:
            return False, False, "hh.ru не подключён"

        # Проверяем наличие платных услуг
        try:
            quota_data = await hh_client.get_payable_api_actions(access_token, str(employer_id))
            unlimited, limited_remaining, has_service = _parse_api_quota(quota_data)

            # has_access = hh подключён (можем искать и оценивать)
            has_access = True

            # has_paid_access = есть платный доступ к базе резюме (для приглашений)
            has_paid_access = unlimited or has_service

            return has_access, has_paid_access, None
        except Exception as e:
            logger.warning(f"Не удалось проверить квоты hh.ru: {e}")
            # hh подключён, но квоты неясны - базовый доступ есть, платный неизвестен
            return True, False, "Не удалось проверить квоту hh"

    except ValidationError as e:
        if "не подключён" in str(e):
            return False, False, "hh.ru не подключён"
        return False, False, str(e)
    except Exception as e:
        logger.error(f"Ошибка проверки доступа к умному подбору: {e}")
        return False, False, "Ошибка проверки доступа"


async def get_smart_vacancies(session: AsyncSession, company_id: UUID) -> list[SmartVacancyItem]:
    """Получает активные вакансии с предзаполненными фильтрами"""

    result = await session.execute(
        select(Vacancy).where(
            Vacancy.company_id == company_id,
            Vacancy.status == "active",
            Vacancy.deleted_at.is_(None)
        ).order_by(Vacancy.sort_order, Vacancy.name)
    )
    vacancies = result.scalars().all()

    smart_vacancies = []
    for vacancy in vacancies:
        # Извлекаем навыки из описания (простая эвристика)
        skills = []
        if vacancy.description:
            # Ищем возможные навыки в тексте
            skill_patterns = [
                r'\b(Python|JavaScript|Java|C\+\+|SQL|Git|Docker|React|Angular|Vue)\b',
                r'\b(Agile|Scrum|English|B2|C1)\b'
            ]
            for pattern in skill_patterns:
                matches = re.findall(pattern, vacancy.description, re.IGNORECASE)
                skills.extend([m for m in matches if m not in skills])

        # Опыт из описания (простая эвристика)
        experience = None
        if vacancy.description:
            if re.search(r'(\d+)[\s\-]*(\+)?[\s]*лет', vacancy.description, re.IGNORECASE):
                match = re.search(r'(\d+)[\s\-]*(\+)?[\s]*лет', vacancy.description, re.IGNORECASE)
                if match:
                    years = match.group(1)
                    experience = f"{years}+ лет"

        smart_vacancy = SmartVacancyItem(
            id=vacancy.id,
            title=vacancy.name,
            city=vacancy.city,
            area=None,  # Заполнит AI-эндпоинт при выборе вакансии
            professional_role=None,  # Заполнит AI-эндпоинт при выборе вакансии
            experience=experience,
            salary_from=vacancy.salary_from,
            salary_to=vacancy.salary_to,
            skills=skills[:5],  # Ограничиваем количество
            found=None,  # Будет заполнено при поиске
            hh_published=bool(vacancy.hh_vacancy_id)  # Опубликована ли на hh.ru
        )
        smart_vacancies.append(smart_vacancy)

    return smart_vacancies


async def start_search(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    request: SmartSearchRequest
) -> UUID:
    """Запускает умный поиск"""

    # Проверяем доступ
    has_access, has_paid_access, reason = await check_access(session, company_id)
    if not has_access:
        raise ValidationError(f"Нет доступа к умному подбору: {reason}")

    # Проверяем вакансию
    vacancy_result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == request.vacancy_id,
            Vacancy.company_id == company_id,
            Vacancy.status == "active",
            Vacancy.deleted_at.is_(None)
        )
    )
    vacancy = vacancy_result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия")

    # Получаем токен и квоты для передачи в фоновую задачу
    try:
        access_token = await hh_service.get_valid_access_token(session, company_id)
        me_data = await hh_client.get_me(access_token)
        employer_id = str(me_data.get("employer", {}).get("id"))

        quota_data = await hh_client.get_payable_api_actions(access_token, employer_id)

        # ДИАГНОСТИКА: логируем сырой ответ для первого реального запуска
        logger.info("[smart] payable_api_actions raw=%s", quota_data)

    except Exception as e:
        logger.warning(f"Не удалось проверить квоты hh.ru: {e}")
        # Если не можем получить квоты - считаем что платного доступа нет
        has_paid_access = False

    # Создаем запись поиска
    search_run = SmartSearchRun(
        company_id=company_id,
        vacancy_id=request.vacancy_id,
        status="running",
        stage="search",
        params={
            "area": request.area,
            "professional_role": request.professional_role,
            "experience": request.experience,
            "skills": request.skills,
            "salary_from": request.salary_from,
            "salary_to": request.salary_to,
            "include_no_salary": request.include_no_salary,
            "scan_n": request.scan_n,
            "invite_m": request.invite_m,
            "threshold": request.threshold,
            "has_paid_access": has_paid_access,
        }
    )
    session.add(search_run)
    await session.commit()
    await session.refresh(search_run)

    # Запускаем фоновую задачу
    task = asyncio.create_task(_run_search_background(search_run.id, company_id, user_id))
    _active_tasks[search_run.id] = task  # Предотвращаем GC

    # Удаляем из активных после завершения
    def cleanup_task(task_future):
        _active_tasks.pop(search_run.id, None)
    task.add_done_callback(cleanup_task)

    return search_run.id


async def _run_search_background(run_id: UUID, company_id: UUID, user_id: UUID):
    """Фоновая задача выполнения поиска"""
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            run = await session.get(SmartSearchRun, run_id)
            if not run:
                return

            # Получаем токен и вакансию
            access_token = await hh_service.get_valid_access_token(session, company_id)
            vacancy = await session.get(Vacancy, run.vacancy_id)

            # ЭТАП 1: Поиск резюме
            params = run.params

            # Собираем text из роли + навыков (осмысленный поиск)
            text_parts = []
            professional_role = params.get("professional_role") or vacancy.name
            if professional_role:
                text_parts.append(professional_role)

            skills = params.get("skills", [])
            if skills:
                text_parts.extend(skills)

            search_text = " ".join(filter(None, text_parts)).strip()

            search_params = {
                "text": search_text or vacancy.name,  # Fallback на название вакансии
                "per_page": 50,
                "page": 0
            }

            # Добавляем структурные фильтры ТОЛЬКО при валидных значениях
            if params.get("area"):
                # area: только если числовое (id региона из справочника hh)
                area_value = params["area"]
                if str(area_value).strip().isdigit():
                    search_params["area"] = area_value
                # Иначе НЕ передаём area - значение уже в text, не ломает запрос

            if params.get("professional_role"):
                # professional_role: только если числовое (id роли из справочника hh)
                role_value = params["professional_role"]
                if str(role_value).strip().isdigit():
                    search_params["professional_role"] = role_value
                # Иначе НЕ передаём - роль уже в text

            if params.get("experience"):
                # experience: только если валидный enum hh
                exp_value = params["experience"]
                valid_experience = ["noExperience", "between1And3", "between3And6", "moreThan6"]
                if exp_value in valid_experience:
                    search_params["experience"] = exp_value
                # Иначе НЕ передаём - опыт может быть в text

            if params.get("skills") and isinstance(params["skills"], list):
                # skill: только если все элементы - числовые id навыков
                skills_list = params["skills"]
                if all(str(skill).strip().isdigit() for skill in skills_list):
                    search_params["skill"] = skills_list
                # Иначе НЕ передаём - навыки уже в text

            # Зарплатные фильтры - всегда валидны
            if params.get("salary_from"):
                search_params["salary_from"] = params["salary_from"]
            if params.get("salary_to"):
                search_params["salary_to"] = params["salary_to"]
            if params.get("include_no_salary"):
                search_params["only_with_salary"] = "false"

            # Диагностика: логируем итоговый запрос
            logger.info("[smart] search_params=%s", search_params)

            search_result = await hh_client.search_resumes(access_token, search_params)
            found_count = search_result.get("found", 0)
            resume_items = search_result.get("items", [])

            # Обновляем счетчик найденных
            run.found = found_count
            run.stage = "eval"
            await session.commit()

            # ЭТАП 2: Оценка резюме
            scan_n = min(params.get("scan_n", 50), len(resume_items))
            evaluated_candidates = []

            for i, resume_item in enumerate(resume_items[:scan_n]):
                try:
                    resume_id = resume_item.get("id")
                    if not resume_id:
                        run.scanned = i + 1
                        await session.commit()
                        continue

                    # Получаем полное резюме (ПЛАТНО)
                    full_resume = await hh_client.get_resume_by_id(access_token, str(resume_id))

                    try:
                        # Оцениваем резюме БЕЗ персиста
                        score_result = await score_resume_dict(full_resume, vacancy, company_id)

                        evaluated_candidates.append({
                            "resume_id": resume_id,
                            "candidate_data": {
                                "resume": full_resume,
                                "ai_score": score_result["score"],
                                "verdict": score_result["verdict"],
                                "summary": score_result["summary"]
                            },
                            "full_resume": full_resume
                        })

                        run.evaluated = len(evaluated_candidates)

                    except GlafiraParseError as e:
                        # При сбое парсинга JSON одного резюме - логируем и пропускаем
                        logger.warning(f"Ошибка парсинга AI-оценки резюме {resume_id}: {e}")

                    # Обновляем прогресс
                    run.scanned = i + 1
                    await session.commit()

                except Exception as e:
                    logger.warning(f"Ошибка при обработке резюме {resume_id}: {e}")
                    run.scanned = i + 1
                    await session.commit()
                    continue

            # ЭТАП 3: Приглашения
            run.stage = "invite"
            await session.commit()

            # Сортируем по баллу и отбираем лучших
            threshold = params.get("threshold", 70)
            invite_m = params.get("invite_m", 10)

            good_candidates = [
                c for c in evaluated_candidates
                if c["candidate_data"]["ai_score"] >= threshold
            ]
            good_candidates.sort(key=lambda x: x["candidate_data"]["ai_score"], reverse=True)

            invited_candidates = []
            has_paid_access = params.get("has_paid_access", False)
            can_invite = has_paid_access and vacancy.hh_vacancy_id

            if can_invite:
                # Режим с приглашениями - создаём кандидатов и заявки в воронку
                for candidate_data in good_candidates[:invite_m]:
                    try:
                        resume_id = candidate_data["resume_id"]
                        ai_data = candidate_data["candidate_data"]
                        full_resume = candidate_data["full_resume"]

                        # Проверяем дедубликацию
                        existing = await _find_existing_candidate(session, resume_id, full_resume, company_id)
                        if existing:
                            logger.info(f"Кандидат {resume_id} уже существует, пропускаем приглашение")
                            continue

                        # Отправляем приглашение через hh.ru (используем реальный hh_vacancy_id)
                        invitation = await hh_client.invite_to_vacancy(
                            access_token,
                            str(resume_id),
                            vacancy.hh_vacancy_id,
                            message="Приглашение от Глафира Рекрутёр"
                        )

                        # Создаем кандидата и заявку
                        candidate = _create_candidate_from_resume(full_resume, company_id)
                        candidate.source = "hh"  # Источник "Умный подбор/hh" через extra
                        candidate.extra = {"smart_search": True, "run_id": str(run_id), "hh_resume_id": str(resume_id)}
                        session.add(candidate)
                        await session.flush()

                        # Создаем заявку
                        negotiation_id = _extract_negotiation_id(invitation)
                        application = Application(
                            candidate_id=candidate.id,
                            vacancy_id=vacancy.id,
                            company_id=company_id,
                            stage="response",
                            hh_negotiation_id=negotiation_id
                        )
                        session.add(application)

                        # Audit записи
                        await audit(
                            session,
                            action="smart_search_invite",
                            entity_type="candidate",
                            entity_id=candidate.id,
                            after={
                                "vacancy_id": str(vacancy.id),
                                "ai_score": ai_data["ai_score"],
                                "run_id": str(run_id)
                            },
                            actor_type="ai",
                            company_id=company_id
                        )

                        # Добавляем в список приглашенных
                        invited_candidates.append(InvitedCandidate(
                            candidate_id=candidate.id,
                            name=f"{candidate.first_name} {candidate.last_name}".strip(),
                            age=_calculate_age(candidate.birth_date),
                            experience_years=_extract_experience_years(full_resume),
                            last_company=candidate.last_company,
                            city=candidate.city,
                            score=ai_data["ai_score"],
                            verdict=ai_data["verdict"]
                        ))

                        await session.commit()

                    except Exception as e:
                        logger.error(f"Ошибка при приглашении кандидата {resume_id}: {e}")
                        continue

                run.invites_skipped = False
            else:
                # Режим превью - НЕ создаём кандидатов, только показываем топовых
                logger.info(f"Умный поиск {run_id}: режим превью (платный доступ={has_paid_access}, hh_vacancy_id={'есть' if vacancy.hh_vacancy_id else 'НЕТ'})")

                for candidate_data in good_candidates[:invite_m]:
                    resume_id = candidate_data["resume_id"]
                    ai_data = candidate_data["candidate_data"]
                    full_resume = candidate_data["full_resume"]

                    # Извлекаем имя из резюме
                    first_name = (full_resume.get("first_name") or "").strip() or "Неизвестно"
                    last_name = (full_resume.get("last_name") or "").strip() or ""
                    name = f"{first_name} {last_name}".strip()

                    # Создаем превью без candidate_id
                    invited_candidates.append(InvitedCandidate(
                        candidate_id=None,
                        name=name,
                        age=_calculate_age_from_resume(full_resume),
                        experience_years=_extract_experience_years(full_resume),
                        last_company=(full_resume.get("experience", [{}])[0].get("company") if full_resume.get("experience") else None),
                        city=(full_resume.get("area") or {}).get("name"),
                        score=ai_data["ai_score"],
                        verdict=ai_data["verdict"]
                    ))

                run.invites_skipped = True

            # Финализируем поиск
            run.stage = "done"
            run.status = "done"
            run.invited = len(invited_candidates) if can_invite else 0  # invited = реальные приглашения
            run.invited_candidates = [c.dict() for c in invited_candidates]
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()

        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче поиска {run_id}: {e}")
            run = await session.get(SmartSearchRun, run_id)
            if run:
                run.status = "error"
                run.error = str(e)[:500]
                await session.commit()


def _create_candidate_from_resume(resume: dict, company_id: UUID) -> Candidate:
    """Создает кандидата из данных резюме hh.ru"""

    first_name = (resume.get("first_name") or "").strip() or "Неизвестно"
    last_name = (resume.get("last_name") or "").strip() or ""
    middle_name = (resume.get("middle_name") or "").strip() or None

    candidate = Candidate(
        company_id=company_id,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        source="hh",
        city=(resume.get("area") or {}).get("name"),
        phone=_extract_phone(resume.get("contact", [])),
        email=_extract_email(resume.get("contact", [])),
        last_position=resume.get("title"),
        resume_text=_build_resume_text(resume)
    )

    return candidate


def _extract_phone(contacts: list) -> Optional[str]:
    """Извлекает телефон из контактов"""
    for contact in contacts or []:
        if (contact.get("type") or {}).get("id") in ("cell", "home", "work"):
            value = contact.get("value")
            if isinstance(value, dict):
                return value.get("formatted") or value.get("number")
            if isinstance(value, str):
                return value
    return None


def _extract_email(contacts: list) -> Optional[str]:
    """Извлекает email из контактов"""
    for contact in contacts or []:
        if (contact.get("type") or {}).get("id") == "email":
            value = contact.get("value")
            if isinstance(value, str):
                return value
    return None


def _build_resume_text(resume: dict) -> str:
    """Строит текст резюме для скоринга"""
    parts = []

    if resume.get("title"):
        parts.append(f"Желаемая должность: {resume['title']}")

    if resume.get("skills"):
        parts.append(f"Навыки: {resume['skills']}")

    # Опыт работы
    experiences = resume.get("experience", [])
    if experiences:
        parts.append("Опыт работы:")
        for exp in experiences[:3]:  # Топ-3
            exp_text = f"• {exp.get('position', 'Должность не указана')}"
            if exp.get("company"):
                exp_text += f" в {exp['company']}"
            if exp.get("description"):
                exp_text += f"\n  {exp['description'][:200]}..."
            parts.append(exp_text)

    return "\n\n".join(parts)


def _extract_negotiation_id(invitation: dict) -> Optional[str]:
    """Извлекает negotiation_id из ответа приглашения"""
    # hh.ru возвращает путь вида /negotiations/{id}
    url = invitation.get("url", "")
    if "/negotiations/" in url:
        return url.split("/negotiations/")[-1]
    return None


def _calculate_age(birth_date) -> Optional[int]:
    """Вычисляет возраст"""
    if not birth_date:
        return None
    try:
        today = datetime.now().date()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    except:
        return None


def _calculate_age_from_resume(resume: dict) -> Optional[int]:
    """Вычисляет возраст из данных резюме hh.ru"""
    birth_date = resume.get("birth_date")
    if not birth_date:
        return None
    try:
        # birth_date в формате "YYYY-MM-DD"
        from datetime import date
        birth_year, birth_month, birth_day = map(int, birth_date.split("-"))
        birth_date_obj = date(birth_year, birth_month, birth_day)
        return _calculate_age(birth_date_obj)
    except:
        return None


def _extract_experience_years(resume: dict) -> Optional[int]:
    """Извлекает общий стаж из резюме"""
    # Простая эвристика - считаем по первой записи
    experiences = resume.get("experience", [])
    if not experiences:
        return None

    first_exp = experiences[0]
    start = first_exp.get("start")
    end = first_exp.get("end")

    if start:
        try:
            start_year = int(start[:4])
            end_year = datetime.now().year if not end else int(end[:4])
            return max(0, end_year - start_year)
        except:
            pass

    return None


async def _find_existing_candidate(session: AsyncSession, resume_id: str, resume: dict, company_id: UUID) -> Optional[Candidate]:
    """Ищет существующего кандидата по данным резюме"""

    # ПЕРВЫЙ приоритет: поиск по hh_resume_id (надёжный дедуп)
    result = await session.execute(
        select(Candidate).where(
            Candidate.company_id == company_id,
            Candidate.extra["hh_resume_id"].astext == str(resume_id),
            Candidate.deleted_at.is_(None)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # FALLBACK: поиск по email/phone (если контакты есть)
    email = _extract_email(resume.get("contact", []))
    phone = _extract_phone(resume.get("contact", []))

    if email:
        result = await session.execute(
            select(Candidate).where(
                Candidate.company_id == company_id,
                Candidate.email == email,
                Candidate.deleted_at.is_(None)
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    if phone:
        result = await session.execute(
            select(Candidate).where(
                Candidate.company_id == company_id,
                Candidate.phone == phone,
                Candidate.deleted_at.is_(None)
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    return None


async def get_run_status(session: AsyncSession, run_id: UUID, company_id: UUID) -> Optional[SmartSearchRun]:
    """Получает статус выполнения поиска"""

    result = await session.execute(
        select(SmartSearchRun).where(
            SmartSearchRun.id == run_id,
            SmartSearchRun.company_id == company_id
        )
    )
    return result.scalar_one_or_none()


async def get_run_history(session: AsyncSession, company_id: UUID, limit: int = 20) -> list[SmartSearchRun]:
    """Получает историю поисков"""

    result = await session.execute(
        select(SmartSearchRun)
        .options(joinedload(SmartSearchRun.vacancy))
        .where(SmartSearchRun.company_id == company_id)
        .order_by(desc(SmartSearchRun.created_at))
        .limit(limit)
    )
    return result.unique().scalars().all()


async def derive_vacancy_filters(session: AsyncSession, company_id: UUID, vacancy_id: UUID) -> dict:
    """
    Извлекает AI-фильтры для умного подбора из вакансии

    Args:
        session: Сессия БД
        company_id: ID компании
        vacancy_id: ID вакансии

    Returns:
        dict: {area: str, professional_role: str, experience: str, skills: list[str]}

    Raises:
        NotFoundError: Если вакансия не найдена или не принадлежит компании
    """
    # Загрузить вакансию (company-scoped, не удалённую)
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
            Vacancy.deleted_at.is_(None)
        )
    )
    vacancy = result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия")

    try:
        # Подготовка данных для промпта
        vacancy_description = _strip_html(vacancy.description) if vacancy.description else ""
        recruiter_instructions = vacancy.recruiter_scoring_instructions or ""

        # Формирование промпта
        system_prompt = """Ты - эксперт по рекрутингу. Проанализируй вакансию и определи оптимальные параметры для поиска резюме на hh.ru.

Верни JSON с полями:
- area: ОДНА проф-область в формулировке hh.ru (например: "Информационные технологии", "Продажи", "Транспорт, логистика")
- professional_role: ОДНА проф-роль в формулировке hh.ru (например: "Программист, разработчик", "Тестировщик", "Менеджер по продажам")
- experience: уровень опыта, одно из: "Без опыта", "1–3 года", "3–6 лет", "более 6 лет"
- skills: 5-8 ключевых навыков в виде строк

ВАЖНО:
- Выводи ТОЛЬКО из текста вакансии, НЕ выдумывай
- Если область неочевидна - выбирай самую общую разумную
- НЕ выдумывай навыки, которых нет в описании/требованиях
- Бери навыки именно из требований и описания вакансии"""

        user_prompt = f"""ВАКАНСИЯ:
Название: {vacancy.name}
Описание: {vacancy_description or "описание отсутствует"}

Дополнительные инструкции рекрутёра: {recruiter_instructions or "отсутствуют"}

Определи оптимальные фильтры для поиска резюме на hh.ru."""

        # Вызов LLM
        response_data = await call_json(
            system=system_prompt,
            user=user_prompt,
            max_tokens=2000
        )

        # Валидация ответа
        if not isinstance(response_data, dict):
            raise GlafiraParseError(details={"reason": "Response is not a dict", "got": type(response_data)})

        required_fields = ['area', 'professional_role', 'experience', 'skills']
        for field in required_fields:
            if field not in response_data:
                raise GlafiraParseError(details={"reason": f"Missing field: {field}", "got": list(response_data.keys())})

        # Проверка типов
        if not isinstance(response_data['area'], str):
            raise GlafiraParseError(details={"reason": "area must be string", "got": type(response_data['area'])})
        if not isinstance(response_data['professional_role'], str):
            raise GlafiraParseError(details={"reason": "professional_role must be string", "got": type(response_data['professional_role'])})
        if not isinstance(response_data['experience'], str):
            raise GlafiraParseError(details={"reason": "experience must be string", "got": type(response_data['experience'])})
        if not isinstance(response_data['skills'], list) or len(response_data['skills']) > 8:
            raise GlafiraParseError(details={"reason": "skills must be list with ≤8 items", "got": type(response_data['skills'])})

        return {
            "area": response_data["area"],
            "professional_role": response_data["professional_role"],
            "experience": response_data["experience"],
            "skills": response_data["skills"]
        }

    except (GlafiraParseError, Exception) as e:
        # Graceful fallback при ошибке LLM - форма не должна ломаться
        logger.warning(f"AI-извлечение фильтров вакансии {vacancy_id} не удалось: {e}")

        return {
            "area": "",
            "professional_role": vacancy.name,
            "experience": "",
            "skills": []
        }