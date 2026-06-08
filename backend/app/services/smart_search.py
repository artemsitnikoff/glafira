"""Сервис умного подбора кандидатов через hh.ru"""

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..models import (
    SmartSearchRun, Vacancy, Candidate, Application, AuditLog, Company
)
from ..schemas.smart import (
    SmartSearchRequest, SmartVacancyItem, InvitedCandidate, SmartCountRequest
)
from ..core.errors import ValidationError, NotFoundError
from ..services.integrations.hh import service as hh_service
from ..services.integrations.hh import client as hh_client
from ..services.glafira.scoring import score_resume_dict, _strip_html
from ..services.glafira.client import call_json
from ..core.errors import GlafiraParseError
from ..services.audit import audit
from .smart_search_log import log_smart_search, log_and_append_to_run

logger = logging.getLogger(__name__)

# Константы
FREE_SCAN_LIMIT = 50
MAX_PAGES_LIMIT = 20  # Защитный потолок страниц


async def _calculate_search_timeout(run_id: UUID, company_id: UUID) -> int:
    """Вычисляет таймаут поиска на основе параметров"""
    from ..database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            run = await session.get(SmartSearchRun, run_id)
            if run and run.params:
                scan_n = run.params.get("scan_n", 50)
                # Реалистичный таймаут: базовые 900с + по 200с на каждое резюме
                # (get_resume ~35с + score_resume с ретраями до ~180с)
                return max(900, scan_n * 200)
    except Exception:
        pass

    return 900  # Fallback 15 минут


async def sweep_orphaned_runs(max_age_minutes: int = 60):
    """
    Очистка осиротевших поисков при старте сервера и зависших по времени

    Args:
        max_age_minutes: максимальный возраст running поиска без обновлений (по умолчанию 60 мин)
    """
    from ..database import AsyncSessionLocal
    from sqlalchemy import update, and_

    try:
        async with AsyncSessionLocal() as session:
            # Находим running поиски старше max_age_minutes без обновлений
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

            result = await session.execute(
                update(SmartSearchRun)
                .where(
                    and_(
                        SmartSearchRun.status == "running",
                        SmartSearchRun.updated_at < cutoff_time
                    )
                )
                .values(
                    status="error",
                    error="Прервано (зависание/перезапуск)",
                    note="Поиск был прерван из-за зависания или перезапуска сервера",
                    finished_at=datetime.now(timezone.utc)
                )
                .returning(SmartSearchRun.id)
            )

            orphaned_ids = result.scalars().all()
            if orphaned_ids:
                await session.commit()
                logger.info(f"Очищено {len(orphaned_ids)} осиротевших поисков: {[str(id)[:6] for id in orphaned_ids]}")
            else:
                logger.info("Осиротевших поисков не найдено")

    except Exception as e:
        # Не падаем при ошибках sweep - старт сервера должен продолжиться
        logger.warning(f"Ошибка очистки осиротевших поисков: {e}")
        pass

# Глобальное хранилище для активных задач (предотвращает GC)
_active_tasks = {}


def _compact_resume_for_display(full_resume: dict) -> dict:
    """Возвращает компактный dict резюме для UI (ограничивает размер)"""
    # Зарплата
    salary = None
    salary_data = full_resume.get('salary')
    if salary_data:
        salary_from = salary_data.get('from')
        salary_to = salary_data.get('to')
        currency = salary_data.get('currency', 'RUR')
        if salary_from and salary_to:
            salary = f"{salary_from:,} - {salary_to:,} {currency}"
        elif salary_from:
            salary = f"от {salary_from:,} {currency}"
        elif salary_to:
            salary = f"до {salary_to:,} {currency}"
        else:
            salary = f"{currency}"

    # Опыт работы (до 6 элементов)
    experience = []
    for exp in (full_resume.get("experience") or [])[:6]:
        if not isinstance(exp, dict):
            continue

        position = exp.get('position', '')
        company = exp.get('company', '')
        start = exp.get('start', '')
        end = exp.get('end', '')
        description = exp.get('description', '')

        # Период
        period = start
        if end:
            period = f"{start} - {end}" if start else end
        elif start:
            period = f"{start} - по наст.вр."

        experience.append({
            "position": position,
            "company": company,
            "period": period,
            "description": description[:400] if description else ""  # Обрезаем до 400 символов
        })

    # Навыки (до 40)
    skills = []
    skills_raw = full_resume.get('skills')
    if isinstance(skills_raw, str):
        skills = [skills_raw]
    elif isinstance(skills_raw, list):
        # Навыки могут быть строками или объектами с полем name/skill
        for skill in skills_raw:
            if isinstance(skill, str):
                skills.append(skill)
            elif isinstance(skill, dict):
                skill_name = skill.get('name') or skill.get('skill') or str(skill)
                skills.append(skill_name)

    # Из key_skills если есть
    key_skills = full_resume.get('key_skills', [])
    for skill in key_skills[:40-len(skills)]:  # Дополняем до лимита 40
        if isinstance(skill, dict):
            skill_name = skill.get('name', '')
            if skill_name and skill_name not in skills:
                skills.append(skill_name)
        elif isinstance(skill, str) and skill not in skills:
            skills.append(skill)

    skills = skills[:40]  # Финальный лимит

    # Образование
    education = None
    education_data = full_resume.get("education")
    if isinstance(education_data, dict):
        level = education_data.get("level", {})
        if isinstance(level, dict):
            education = level.get("name")

    return {
        "title": full_resume.get("title"),
        "total_experience_months": (full_resume.get("total_experience") or {}).get("months"),
        "city": (full_resume.get("area") or {}).get("name"),
        "age": full_resume.get("age"),
        "salary": salary,
        "experience": experience,
        "skills": skills,
        "education": education
    }


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

    # Проверяем подтверждение расхода для больших объёмов
    if request.scan_n > FREE_SCAN_LIMIT and not request.confirm_cost:
        raise ValidationError(
            f"Планируется просмотр {request.scan_n} резюме (свыше {FREE_SCAN_LIMIT} бесплатных). "
            f"Это потратит платные запросы к hh.ru. Подтвердите расход установкой confirm_cost=true."
        )

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
            "area_id": request.area_id,
            "period": request.period,
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


def build_search_params(params: dict, vacancy) -> dict:
    """
    Строит параметры поиска резюме на hh.ru из фильтров умного подбора

    Args:
        params: словарь параметров поиска от клиента
        vacancy: объект вакансии

    Returns:
        dict: параметры для hh API БЕЗ page/per_page (их добавляет вызывающий)
    """
    # Собираем text из роли + навыков (осмысленный поиск)
    text_parts = []
    professional_role = params.get("professional_role") or vacancy.name
    if professional_role:
        text_parts.append(professional_role)

    skills = params.get("skills", [])
    if skills:
        text_parts.extend(skills)

    search_text = " ".join(filter(None, text_parts)).strip()

    base_search_params = {
        "text": search_text or vacancy.name,  # Fallback на название вакансии
    }

    # Добавляем структурные фильтры ТОЛЬКО при валидных значениях
    if params.get("area_id"):
        # area: берём из area_id (ID региона из справочника hh)
        area_id = params["area_id"]
        if str(area_id).strip().isdigit():
            base_search_params["area"] = area_id

    if params.get("professional_role"):
        # professional_role: только если числовое (id роли из справочника hh)
        role_value = params["professional_role"]
        if str(role_value).strip().isdigit():
            base_search_params["professional_role"] = role_value
        # Иначе НЕ передаём - роль уже в text

    if params.get("experience"):
        # experience: только если валидный enum hh
        exp_value = params["experience"]
        valid_experience = ["noExperience", "between1And3", "between3And6", "moreThan6"]
        if exp_value in valid_experience:
            base_search_params["experience"] = exp_value
        # Иначе НЕ передаём - опыт может быть в text

    if params.get("skills") and isinstance(params["skills"], list):
        # skill: только если все элементы - числовые id навыков
        skills_list = params["skills"]
        if all(str(skill).strip().isdigit() for skill in skills_list):
            base_search_params["skill"] = skills_list
        # Иначе НЕ передаём - навыки уже в text

    # Зарплатные фильтры - всегда валидны
    if params.get("salary_from"):
        base_search_params["salary_from"] = params["salary_from"]
    if params.get("salary_to"):
        base_search_params["salary_to"] = params["salary_to"]
    if params.get("include_no_salary"):
        base_search_params["only_with_salary"] = "false"

    # Фильтр свежести резюме
    period = params.get("period")
    if period is not None and isinstance(period, int) and period > 0:
        base_search_params["period"] = period

    return base_search_params


async def _run_search_background(run_id: UUID, company_id: UUID, user_id: UUID):
    """Фоновая задача выполнения поиска"""
    try:
        timeout_s = await _calculate_search_timeout(run_id, company_id)
        await asyncio.wait_for(_run_search_inner(run_id, company_id, user_id), timeout=timeout_s)
    except asyncio.TimeoutError:
        # Финализируем СВЕЖЕЙ сессией с таймаутом (старая могла зависнуть)
        try:
            await asyncio.wait_for(
                _finalize_run(
                    run_id,
                    status="error",
                    error="timeout",
                    note="Поиск прерван по таймауту (hh не ответил вовремя). Попробуйте ещё раз."
                ),
                timeout=15
            )
        except Exception as e:
            logger.error(f"Не удалось финализировать run {run_id} по таймауту: {e}")
    except asyncio.CancelledError:
        # Обязательная финализация при отмене
        try:
            await asyncio.wait_for(
                _finalize_run(
                    run_id,
                    status="error",
                    error="cancelled",
                    note="Поиск был отменён"
                ),
                timeout=15
            )
        except Exception as e:
            logger.error(f"Не удалось финализировать отменённый run {run_id}: {e}")
        raise
    except Exception as e:
        # Финализируем любые другие ошибки
        try:
            await asyncio.wait_for(
                _finalize_run(
                    run_id,
                    status="error",
                    error=str(e)[:500],
                    note=f"Неожиданная ошибка: {str(e)[:200]}"
                ),
                timeout=15
            )
        except Exception as finalize_error:
            logger.error(f"Не удалось финализировать run {run_id} после ошибки: {finalize_error}")
        raise


async def _update_run_progress(run_id: UUID, **updates):
    """Обновляет прогресс выполнения поиска короткой сессией"""
    from ..database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            run = await session.get(SmartSearchRun, run_id)
            if not run:
                return

            for key, value in updates.items():
                if key == "log_append":
                    # Специальный case для добавления в лог
                    current_log = run.log if isinstance(run.log, list) else []
                    run.log = current_log + [value]
                else:
                    setattr(run, key, value)

            # Обёрнутый commit с таймаутом
            await asyncio.wait_for(session.commit(), timeout=20)
    except Exception as e:
        logger.warning(f"Ошибка обновления прогресса run {run_id}: {e}")
        # Не пробрасываем исключение - прогресс не критичен для основного flow


async def _finalize_run(run_id: UUID, status: str, stage: str = None, error: str = None, note: str = None, **extra_fields):
    """Финализирует поиск короткой сессией с гарантией записи"""
    from ..database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            run = await session.get(SmartSearchRun, run_id)
            if not run:
                logger.error(f"Run {run_id} не найден при финализации")
                return False

            run.status = status
            if stage:
                run.stage = stage
            if error:
                run.error = error[:500]
            if note:
                run.note = note
            run.finished_at = datetime.now(timezone.utc)

            # Применяем дополнительные поля
            for key, value in extra_fields.items():
                setattr(run, key, value)

            # Добавляем лог-запись о финализации
            current_log = run.log if isinstance(run.log, list) else []
            run.log = current_log + [f"Финализация: {status} ({datetime.now(timezone.utc).strftime('%H:%M:%S')})"]

            # Обёрнутый commit с таймаутом - главная защита от зависания финала
            await asyncio.wait_for(session.commit(), timeout=30)
            logger.info(f"Run {run_id} финализирован: {status}")
            return True

    except Exception as e:
        logger.error(f"Ошибка финализации run {run_id}: {e}", exc_info=True)
        return False


async def _run_search_inner(run_id: UUID, company_id: UUID, user_id: UUID):
    """Внутренняя логика выполнения поиска с короткоживущими сессиями"""
    from ..database import AsyncSessionLocal

    try:
        # Инициализация: загружаем run и базовые данные
        async with AsyncSessionLocal() as init_session:
            run = await init_session.get(SmartSearchRun, run_id)
            if not run:
                return

            # Инициализируем новые поля если они пустые
            if not hasattr(run, 'log') or run.log is None:
                run.log = []
            if not hasattr(run, 'scored_candidates') or run.scored_candidates is None:
                run.scored_candidates = []

            # Получаем токен и вакансию
            access_token = await hh_service.get_valid_access_token(init_session, company_id)
            vacancy = await init_session.get(Vacancy, run.vacancy_id)

            # Сохраняем нужные данные в локальные переменные до закрытия сессии
            params = run.params
            vacancy_id = run.vacancy_id  # Сохраняем ID отдельно

            # Создаём полную копию нужных атрибутов vacancy для использования вне сессии
            vacancy_data = {
                'name': vacancy.name,
                'city': vacancy.city,
                'salary_from': vacancy.salary_from,
                'salary_to': vacancy.salary_to,
                'currency': vacancy.currency,
                'description': vacancy.description,
                'recruiter_scoring_instructions': vacancy.recruiter_scoring_instructions
            }
            # Создаём объект-заглушку с нужными атрибутами для score_resume_dict
            vacancy_for_scoring = type('VacancyProxy', (), vacancy_data)()

            await init_session.commit()  # Сохраняем инициализацию

        # Логируем старт без открытой сессии
        await log_smart_search(run_id, f"Запуск умного подбора для вакансии {vacancy_id}")
        await log_smart_search(run_id, f"Вакансия: {vacancy_data['name']}")

        # ЭТАП 1: Поиск резюме с пагинацией (БЕЗ открытой DB сессии)
        base_search_params = build_search_params(params, vacancy_for_scoring)
        base_search_params["per_page"] = 50

        logger.info("[smart] search_params=%s", base_search_params)
        await log_smart_search(run_id, f"Параметры поиска: {base_search_params}")

        # Пагинация: собираем резюме по страницам
        accumulated_items = []
        found_count = 0
        scan_n = params.get("scan_n", 50)

        for page in range(MAX_PAGES_LIMIT):
            search_params = base_search_params.copy()
            search_params["page"] = page

            # Сетевой вызов БЕЗ открытой DB сессии с таймаутом
            search_result = await asyncio.wait_for(
                hh_client.search_resumes(access_token, search_params),
                timeout=45
            )
            page_found = search_result.get("found", 0)
            page_items = search_result.get("items", [])

            if page == 0:
                found_count = page_found

            await log_smart_search(run_id, f"Страница {page + 1}/{MAX_PAGES_LIMIT}: {len(page_items)} резюме, всего найдено: {found_count}")

            if not page_items:
                await log_smart_search(run_id, f"Страница {page + 1} пустая, завершаем поиск")
                break

            accumulated_items.extend(page_items)

            if len(accumulated_items) >= scan_n:
                await log_smart_search(run_id, f"Набрали достаточно резюме: {len(accumulated_items)} >= {scan_n}")
                break

            if len(accumulated_items) >= found_count:
                await log_smart_search(run_id, f"Собрали все доступные резюме: {len(accumulated_items)} из {found_count}")
                break

        resume_items = accumulated_items

        # Обновляем счетчик найденных короткой сессией
        await _update_run_progress(
            run_id,
            found=found_count,
            stage="eval",
            log_append=f"Всего найдено: {found_count}, собрано: {len(resume_items)}"
        )

        # ЭТАП 2: Оценка резюме
        scan_n = min(params.get("scan_n", 50), len(resume_items))
        threshold = params.get("threshold", 70)
        evaluated_candidates = []

        await log_smart_search(run_id, f"Начинаем оценку {scan_n} резюме с порогом {threshold}")

        for i, resume_item in enumerate(resume_items[:scan_n]):
            try:
                resume_id = resume_item.get("id")
                if not resume_id:
                    # Обновляем прогресс короткой сессией
                    await _update_run_progress(
                        run_id,
                        scanned=i + 1,
                        log_append=f"Резюме {i + 1}/{scan_n}: нет ID, пропускаем"
                    )
                    continue

                # Получаем полное резюме (ПЛАТНО) БЕЗ открытой DB сессии с таймаутом
                full_resume = await asyncio.wait_for(
                    hh_client.get_resume_by_id(access_token, str(resume_id)),
                    timeout=35
                )

                # Извлекаем имя для логирования
                first_name = (full_resume.get("first_name") or "").strip() or "Неизвестно"
                last_name = (full_resume.get("last_name") or "").strip() or ""
                name = f"{first_name} {last_name}".strip()

                try:
                    # Оцениваем резюме БЕЗ открытой DB сессии с таймаутом
                    score_result = await asyncio.wait_for(
                        score_resume_dict(full_resume, vacancy_for_scoring, company_id),
                        timeout=180  # LLM-вызов может быть долгим с ретраями
                    )
                    score = score_result["score"]
                    verdict = score_result["verdict"]
                    passed = score >= threshold

                    evaluated_candidates.append({
                        "resume_id": resume_id,
                        "candidate_data": {
                            "resume": full_resume,
                            "ai_score": score,
                            "verdict": verdict,
                            "summary": score_result["summary"]
                        },
                        "full_resume": full_resume
                    })

                    # Формируем scored_candidate для отчётности
                    scored_candidate = {
                        "candidate_id": None,
                        "name": name,
                        "age": _calculate_age_from_resume(full_resume),
                        "experience_years": _extract_experience_years(full_resume),
                        "last_company": (full_resume.get("experience", [{}])[0].get("company") if full_resume.get("experience") else None),
                        "city": (full_resume.get("area") or {}).get("name"),
                        "score": score,
                        "verdict": verdict,
                        "passed": passed,
                        "summary": score_result.get("summary"),
                        "strengths": score_result.get("strengths") or [],
                        "risks": score_result.get("risks") or [],
                        "requirements_match": score_result.get("requirements_match") or [],
                        "forecast": score_result.get("forecast"),
                        "resume": _compact_resume_for_display(full_resume),
                        "hh_resume_id": str(resume_id),
                        "invited": False
                    }

                    status = "✓ прошёл" if passed else "✗ не прошёл"
                    log_message = f"Резюме {resume_id} • {name} • score {score} ({verdict}) • {status}"
                    await log_smart_search(run_id, log_message)

                    # Обновляем прогресс с результатом оценки короткой сессией
                    async with AsyncSessionLocal() as eval_session:
                        run = await eval_session.get(SmartSearchRun, run_id)
                        if run:
                            # Добавляем новый scored_candidate
                            current_scored = run.scored_candidates.copy() if run.scored_candidates else []
                            current_scored.append(scored_candidate)
                            run.scored_candidates = current_scored
                            run.evaluated = len(evaluated_candidates)
                            run.scanned = i + 1

                            # Добавляем в лог
                            current_log = run.log if isinstance(run.log, list) else []
                            run.log = current_log + [log_message]

                            await asyncio.wait_for(eval_session.commit(), timeout=20)

                except GlafiraParseError as e:
                    error_msg = f"Резюме {resume_id} • {name} • ошибка оценки AI: {str(e)[:100]}"
                    logger.warning(f"Ошибка парсинга AI-оценки резюме {resume_id}: {e}")
                    await log_smart_search(run_id, error_msg)

                    await _update_run_progress(
                        run_id,
                        scanned=i + 1,
                        log_append=error_msg
                    )

            except (asyncio.TimeoutError, ConnectionError, OSError, ValueError) as e:
                # Сетевые и ожидаемые ошибки - логируем и продолжаем
                error_msg = f"Резюме {resume_id or i+1} • ошибка загрузки: {str(e)[:100]}"
                logger.warning(f"Сетевая/timeout ошибка при обработке резюме {resume_id}: {e}")
                await log_smart_search(run_id, error_msg)

                await _update_run_progress(
                    run_id,
                    scanned=i + 1,
                    log_append=error_msg
                )
                continue
            except Exception as e:
                # Неожиданные системные ошибки - пробрасываем вверх для финализации
                logger.error(f"Неожиданная ошибка при обработке резюме {resume_id}: {e}", exc_info=True)
                raise

        # Подсчёт прошедших порог
        passed_threshold = len([
            c for c in evaluated_candidates
            if c["candidate_data"]["ai_score"] >= threshold
        ])

        # Формируем финальное сообщение
        if len(evaluated_candidates) == 0:
            final_note = "Не удалось оценить ни одного резюме"
        elif passed_threshold == 0:
            final_note = f"Оценено {len(evaluated_candidates)} резюме, никто не набрал ≥{threshold} — снизьте порог или расширьте фильтры."
        else:
            final_note = f"Оценка завершена. Прошли порог: {passed_threshold}. Выберите кандидатов для приглашения."

        await log_smart_search(run_id, "Оценка завершена, готово к выбору приглашений")

        # Финализация короткой сессией с гарантией записи
        success = await _finalize_run(
            run_id,
            status="done",
            stage="done",
            note=final_note,
            passed_threshold=passed_threshold,
            invites_skipped=True,
            invited=0
        )

        if not success:
            logger.error(f"Финализация run {run_id} не удалась, but task completed")

    except Exception as e:
        logger.error(f"Ошибка в фоновой задаче поиска {run_id}: {e}", exc_info=True)

        # Гарантированная финализация с ошибкой
        await _finalize_run(
            run_id,
            status="error",
            error=str(e)[:500],
            note=f"Ошибка выполнения: {str(e)[:200]}"
        )


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


async def invite_selected(session: AsyncSession, company_id: UUID, user_id: UUID, run_id: UUID, resume_ids: list[str]) -> dict:
    """
    Отправляет приглашения выбранным кандидатам

    Args:
        session: DB сессия
        company_id: ID компании
        user_id: ID пользователя (рекрутёр)
        run_id: ID поиска
        resume_ids: Список hh_resume_id для приглашения

    Returns:
        dict с results и invited_count
    """
    from ..database import AsyncSessionLocal

    # Загружаем базовые данные и проверяем доступ
    run = await session.get(SmartSearchRun, run_id)
    if not run or run.company_id != company_id:
        raise NotFoundError("Поиск")

    vacancy = await session.get(Vacancy, run.vacancy_id)
    if not vacancy:
        raise NotFoundError("Вакансия")

    # Гейты fail-closed
    if not vacancy.hh_vacancy_id:
        raise ValidationError("Вакансия не опубликована на hh.ru — приглашать некуда.")

    has_access, has_paid_access, _ = await check_access(session, company_id)
    if not has_paid_access:
        raise ValidationError("Нет платного доступа к базе резюме hh — отправка приглашений недоступна.")

    # Множество разрешённых резюме
    allowed = {
        c.get("hh_resume_id") for c in (run.scored_candidates or [])
        if c.get("passed") and c.get("hh_resume_id")
    }

    valid_resume_ids = [rid for rid in resume_ids if rid in allowed]

    # Получаем токен доступа
    access_token = await hh_service.get_valid_access_token(session, company_id)

    # Сохраняем данные для использования вне сессии
    vacancy_id = vacancy.id
    hh_vacancy_id = vacancy.hh_vacancy_id

    results = []
    invited_count = 0

    for resume_id in valid_resume_ids:
        try:
            # Проверка дедубликации короткой сессией
            async with AsyncSessionLocal() as check_session:
                existing = await _find_existing_candidate(check_session, resume_id, {}, company_id)
                if existing:
                    results.append({
                        "resume_id": resume_id,
                        "status": "already",
                        "message": "Кандидат уже в базе",
                        "candidate_id": existing.id,
                        "name": f"{existing.first_name} {existing.last_name}".strip()
                    })
                    continue

            # Получаем полное резюме БЕЗ открытой DB сессии
            try:
                full_resume = await asyncio.wait_for(
                    hh_client.get_resume_by_id(access_token, resume_id),
                    timeout=25
                )
            except asyncio.TimeoutError:
                results.append({
                    "resume_id": resume_id,
                    "status": "error",
                    "message": "Таймаут получения резюме (25с)"
                })
                continue
            except Exception as e:
                results.append({
                    "resume_id": resume_id,
                    "status": "error",
                    "message": f"Ошибка получения резюме: {str(e)[:100]}"
                })
                continue

            # Отправляем приглашение БЕЗ открытой DB сессии
            try:
                invitation = await asyncio.wait_for(
                    hh_client.invite_to_vacancy(
                        access_token,
                        resume_id,
                        hh_vacancy_id,
                        message="Приглашение от Глафира Рекрутёр"
                    ),
                    timeout=25
                )
            except asyncio.TimeoutError:
                results.append({
                    "resume_id": resume_id,
                    "status": "error",
                    "message": "Таймаут отправки приглашения (25с)"
                })
                continue
            except Exception as e:
                results.append({
                    "resume_id": resume_id,
                    "status": "error",
                    "message": f"Ошибка отправки приглашения: {str(e)[:100]}"
                })
                continue

            # Создаём кандидата и заявку короткой сессией
            try:
                async with AsyncSessionLocal() as create_session:
                    candidate = _create_candidate_from_resume(full_resume, company_id)
                    candidate.source = "hh"
                    candidate.extra = {
                        "smart_search": True,
                        "run_id": str(run_id),
                        "hh_resume_id": str(resume_id)
                    }
                    create_session.add(candidate)
                    await create_session.flush()

                    # Создаём заявку
                    negotiation_id = _extract_negotiation_id(invitation)
                    application = Application(
                        candidate_id=candidate.id,
                        vacancy_id=vacancy_id,
                        company_id=company_id,
                        stage="response",
                        hh_negotiation_id=negotiation_id
                    )
                    create_session.add(application)

                    # Audit запись
                    await audit(
                        create_session,
                        action="smart_search_invite",
                        entity_type="candidate",
                        entity_id=candidate.id,
                        after={
                            "vacancy_id": str(vacancy_id),
                            "run_id": str(run_id),
                            "hh_resume_id": str(resume_id)
                        },
                        actor_type="human",
                        actor_user_id=user_id,
                        company_id=company_id
                    )

                    # Обновляем run статистику
                    run_obj = await create_session.get(SmartSearchRun, run_id)
                    if run_obj and run_obj.scored_candidates:
                        for candidate_data in run_obj.scored_candidates:
                            if candidate_data.get("hh_resume_id") == resume_id:
                                candidate_data["invited"] = True
                                break
                        run_obj.scored_candidates = run_obj.scored_candidates.copy()

                    run_obj.invited = (run_obj.invited or 0) + 1

                    await create_session.commit()

                    candidate_id = candidate.id
                    candidate_name = f"{candidate.first_name} {candidate.last_name}".strip()

                invited_count += 1

                results.append({
                    "resume_id": resume_id,
                    "status": "invited",
                    "candidate_id": candidate_id,
                    "name": candidate_name
                })

            except Exception as e:
                logger.error(f"Ошибка создания кандидата {resume_id}: {e}")
                results.append({
                    "resume_id": resume_id,
                    "status": "error",
                    "message": f"Ошибка создания кандидата: {str(e)[:100]}"
                })
                continue

        except Exception as e:
            logger.error(f"Ошибка при приглашении кандидата {resume_id}: {e}")
            results.append({
                "resume_id": resume_id,
                "status": "error",
                "message": f"Внутренняя ошибка: {str(e)[:100]}"
            })
            continue

    return {
        "results": results,
        "invited_count": invited_count
    }


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


async def preview_found_count(session: AsyncSession, company_id: UUID, request: SmartCountRequest) -> Optional[int]:
    """
    Предварительный подсчёт количества резюме по фильтрам (БЕЗ денежных трат)

    Args:
        session: сессия БД
        company_id: ID компании
        request: запрос с фильтрами

    Returns:
        Optional[int]: количество найденных резюме или None при ошибке

    Raises:
        NotFoundError: если вакансия не найдена
    """
    try:
        # Загружаем вакансию (company-scoped, активную, не удалённую)
        result = await session.execute(
            select(Vacancy).where(
                Vacancy.id == request.vacancy_id,
                Vacancy.company_id == company_id,
                Vacancy.status == "active",
                Vacancy.deleted_at.is_(None)
            )
        )
        vacancy = result.scalar_one_or_none()
        if not vacancy:
            raise NotFoundError("Вакансия")

        # Собираем параметры фильтров из запроса
        params = {
            "area": request.area,
            "professional_role": request.professional_role,
            "experience": request.experience,
            "skills": request.skills,
            "salary_from": request.salary_from,
            "salary_to": request.salary_to,
            "include_no_salary": request.include_no_salary,
            "area_id": request.area_id,
            "period": request.period,
        }

        # Используем общую функцию построения search_params
        search_params = build_search_params(params, vacancy)
        search_params["per_page"] = 1  # Минимум для получения found
        search_params["page"] = 0

        try:
            # Получаем токен hh
            access_token = await hh_service.get_valid_access_token(session, company_id)

            # Делаем поисковый запрос (БЕСПЛАТНО - только found, без детализации резюме)
            search_result = await hh_client.search_resumes(access_token, search_params)
            found = search_result.get("found")

            return found

        except Exception as e:
            # При ЛЮБОЙ ошибке с hh возвращаем None (превью не должен ронять UI)
            logger.warning(f"Ошибка превью подсчёта резюме: {e}")
            return None

    except NotFoundError:
        # Пробрасываем дальше - это валидная бизнес-ошибка 404
        raise
    except Exception as e:
        # Любые другие ошибки логируем и возвращаем None
        logger.warning(f"Ошибка превью подсчёта резюме: {e}")
        return None


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


async def suggest_areas(session: AsyncSession, company_id: UUID, text: str) -> list[dict]:
    """
    Получает подсказки регионов/городов из справочника hh.ru

    Args:
        session: сессия БД
        company_id: ID компании
        text: текст для поиска

    Returns:
        list[dict]: список подсказок с полями id и text

    Note:
        При любой ошибке возвращает пустой список - подсказки не должны ронять форму
    """
    if len(text.strip()) < 2:
        return []

    try:
        # Получаем токен hh
        access_token = await hh_service.get_valid_access_token(session, company_id)

        # Вызываем hh API
        return await hh_client.suggest_areas(access_token, text)

    except Exception as e:
        # При ЛЮБОЙ ошибке возвращаем пустой список (подсказки не должны ронять форму)
        logger.warning(f"Ошибка получения подсказок регионов hh: {e}")
        return []