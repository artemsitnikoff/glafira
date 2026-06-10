"""Сервис поиска по собственной базе кандидатов"""

import re
from typing import Optional
from uuid import UUID

from sqlalchemy import select, exists, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError, GlafiraParseError
from ..models import (
    Candidate, CandidateSkill, Consent, Vacancy, BaseSearchRun
)
from ..services.glafira.client import call_json
from ..services.smart_search import derive_vacancy_filters
from ..services.candidate import _compute_age, _compute_full_name


async def parse_query_to_criteria(query: str) -> dict:
    """
    Парсит текстовый запрос в критерии поиска через LLM

    Args:
        query: Текстовый запрос пользователя

    Returns:
        dict: {role: str, skills: list[str], experience: str, city: str, salary_from: int|None, salary_to: int|None}
    """
    system_prompt = """Ты - эксперт по рекрутингу. Проанализируй поисковый запрос и извлеки из него критерии поиска кандидатов.

Верни JSON с полями:
- role: должность/позиция (строка, пустая если не указана)
- skills: навыки/технологии (массив строк, максимум 8)
- experience: опыт работы (строка, пустая если не указан)
- city: город (строка, пустая если не указан)
- salary_from: минимальная зарплата (число или null)
- salary_to: максимальная зарплата (число или null)

ВАЖНО:
- Извлекай ТОЛЬКО из текста запроса, НЕ выдумывай
- Если критерий не указан - оставляй пустым/null
- Навыки - только технические/профессиональные
- Зарплата в рублях (если указана в других валютах - конвертируй примерно)
- НЕ добавляй критерии, которых нет в запросе"""

    user_prompt = f"Запрос: {query}"

    try:
        response_data = await call_json(
            system=system_prompt,
            user=user_prompt,
            max_tokens=1500
        )

        # Валидация ответа
        if not isinstance(response_data, dict):
            raise GlafiraParseError(details={"reason": "Response is not a dict"})

        # Проверка обязательных полей с дефолтами
        result = {
            "role": response_data.get("role", ""),
            "skills": response_data.get("skills", []),
            "experience": response_data.get("experience", ""),
            "city": response_data.get("city", ""),
            "salary_from": response_data.get("salary_from"),
            "salary_to": response_data.get("salary_to")
        }

        # Валидация типов
        if not isinstance(result["role"], str):
            result["role"] = ""
        if not isinstance(result["skills"], list):
            result["skills"] = []
        if not isinstance(result["experience"], str):
            result["experience"] = ""
        if not isinstance(result["city"], str):
            result["city"] = ""

        # Ограничение навыков
        result["skills"] = result["skills"][:8]

        return result

    except Exception:
        # Fallback (любой сбой LLM/парса, вкл. GlafiraParseError) - токенизация в ключевые слова.
        # Это НЕ фейк: честный деградированный поиск по словам запроса, не выдуманные данные.
        words = re.findall(r'\b\w{3,}\b', query.lower())
        # Убираем стоп-слова
        stop_words = {'и', 'или', 'для', 'нужен', 'ищу', 'требуется', 'кандидат', 'опыт', 'работа', 'год', 'лет', 'месяц'}
        keywords = [w for w in words if w not in stop_words][:8]

        return {
            "role": query,  # Весь запрос как должность
            "skills": keywords,
            "experience": "",
            "city": "",
            "salary_from": None,
            "salary_to": None
        }


async def search_base(
    session: AsyncSession,
    company_id: UUID,
    *,
    role: str = "",
    skills: list[str] = None,
    city: str = "",
    salary_from: Optional[int] = None,
    salary_to: Optional[int] = None
) -> dict:
    """
    Поиск кандидатов в собственной базе по критериям

    Args:
        session: Сессия БД
        company_id: ID компании
        role: Должность для поиска
        skills: Список навыков
        city: Город
        salary_from: Минимальная зарплата
        salary_to: Максимальная зарплата

    Returns:
        dict: {total: int, results: list[dict]}
    """
    if skills is None:
        skills = []

    # has_pdn subquery
    has_pdn_subq = (
        select(Consent.id)
        .where(Consent.candidate_id == Candidate.id, Consent.status == "signed")
        .exists()
    )

    # Базовые фильтры (обязательные)
    base_filters = [
        Candidate.company_id == company_id,
        Candidate.deleted_at.is_(None)
    ]

    # Фильтр по должности
    if role:
        base_filters.append(
            Candidate.last_position.ilike(f"%{role}%")
        )

    # Фильтр по городу
    if city:
        base_filters.append(
            Candidate.city.ilike(f"%{city}%")
        )

    # Фильтр по зарплате
    # Кандидаты без указанной зарплаты не отсекаем жёстко
    if salary_from is not None:
        base_filters.append(
            or_(
                Candidate.salary_expectation.is_(None),  # NULL включаем
                Candidate.salary_expectation >= salary_from
            )
        )

    if salary_to is not None:
        base_filters.append(
            or_(
                Candidate.salary_expectation.is_(None),  # NULL включаем
                Candidate.salary_expectation <= salary_to
            )
        )

    # Фильтр по навыкам (если указаны)
    if skills:
        skill_filters = []
        for skill in skills:
            skill_filters.append(
                exists().where(
                    and_(
                        CandidateSkill.candidate_id == Candidate.id,
                        CandidateSkill.company_id == company_id,
                        CandidateSkill.skill.ilike(f"%{skill}%")
                    )
                )
            )
        # Кандидат должен иметь хотя бы один из навыков
        base_filters.append(or_(*skill_filters))

    # Подсчёт общего количества
    count_stmt = select(func.count(Candidate.id)).where(and_(*base_filters))
    total = (await session.execute(count_stmt)).scalar_one()

    # Основной запрос с навыками кандидата
    stmt = (
        select(
            Candidate.id,
            Candidate.display_number,
            Candidate.last_name,
            Candidate.first_name,
            Candidate.middle_name,
            Candidate.birth_date,
            Candidate.last_position,
            Candidate.last_company,
            Candidate.last_period,
            Candidate.city,
            Candidate.ai_score,
            Candidate.source,
            Candidate.salary_expectation,
            has_pdn_subq.label("has_pdn")
        )
        .where(and_(*base_filters))
    )

    # Сортировка: ai_score desc (nulls last) -> created_at desc
    stmt = stmt.order_by(
        Candidate.ai_score.desc().nulls_last(),
        Candidate.created_at.desc()
    )

    # Ограничение результатов
    stmt = stmt.limit(100)

    result = await session.execute(stmt)
    candidates = result.fetchall()

    # Загружаем навыки для всех кандидатов одним запросом
    if candidates:
        candidate_ids = [c.id for c in candidates]
        skills_stmt = (
            select(
                CandidateSkill.candidate_id,
                CandidateSkill.skill
            )
            .where(
                and_(
                    CandidateSkill.candidate_id.in_(candidate_ids),
                    CandidateSkill.company_id == company_id
                )
            )
            .order_by(CandidateSkill.order_index)
        )
        skills_result = await session.execute(skills_stmt)

        # Группируем навыки по кандидату
        candidate_skills = {}
        for skill_row in skills_result:
            candidate_id = skill_row.candidate_id
            if candidate_id not in candidate_skills:
                candidate_skills[candidate_id] = []
            candidate_skills[candidate_id].append(skill_row.skill)
    else:
        candidate_skills = {}

    # Формируем результат
    results = []
    for candidate in candidates:
        candidate_skill_list = candidate_skills.get(candidate.id, [])

        # Подсчёт совпадающих навыков
        matched_skills = []
        if skills:
            for req_skill in skills:
                for cand_skill in candidate_skill_list:
                    if req_skill.lower() in cand_skill.lower():
                        matched_skills.append(cand_skill)
                        break  # Один навык кандидата может покрыть только один требуемый

        # Подсчёт процента совпадения
        match_percent = None
        if skills:
            match_percent = round(len(matched_skills) / len(skills) * 100)
        else:
            # Если навыки не запрошены, считаем по другим критериям
            matched_criteria = 0
            total_criteria = 0

            if role:
                total_criteria += 1
                if candidate.last_position and role.lower() in candidate.last_position.lower():
                    matched_criteria += 1

            if city:
                total_criteria += 1
                if candidate.city and city.lower() in candidate.city.lower():
                    matched_criteria += 1

            if salary_from is not None or salary_to is not None:
                total_criteria += 1
                if candidate.salary_expectation is not None:
                    salary_matches = True
                    if salary_from and candidate.salary_expectation < salary_from:
                        salary_matches = False
                    if salary_to and candidate.salary_expectation > salary_to:
                        salary_matches = False
                    if salary_matches:
                        matched_criteria += 1
                else:
                    # NULL зарплата считается совпадением
                    matched_criteria += 1

            if total_criteria > 0:
                match_percent = round(matched_criteria / total_criteria * 100)

        results.append({
            "id": candidate.id,
            "full_name": _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name),
            "age": _compute_age(candidate.birth_date),
            "last_position": candidate.last_position,
            "last_company": candidate.last_company,
            "last_period": candidate.last_period,  # Используем как last_tenure
            "city": candidate.city,
            "ai_score": candidate.ai_score,
            "source": candidate.source,
            "salary_expectation": candidate.salary_expectation,
            "matched_skills": matched_skills,
            "all_skills": candidate_skill_list,
            "match_percent": match_percent,
            "has_pdn": candidate.has_pdn
        })

    # Сортировка «больше совпало — выше» (ТЗ): по match_percent desc (None в конец),
    # затем по ai_score desc. SQL-сортировки по ai_score недостаточно — % считается в Python.
    results.sort(
        key=lambda r: (
            r["match_percent"] if r["match_percent"] is not None else -1,
            r["ai_score"] if r["ai_score"] is not None else -1,
        ),
        reverse=True,
    )

    return {
        "total": total,
        "results": results
    }


async def search_by_vacancy(
    session: AsyncSession,
    company_id: UUID,
    vacancy_id: UUID
) -> dict:
    """
    Поиск кандидатов по критериям вакансии

    Args:
        session: Сессия БД
        company_id: ID компании
        vacancy_id: ID вакансии

    Returns:
        dict: {total: int, results: list[dict], criteria: dict, vacancy_title: str}
    """
    # Получаем критерии из вакансии
    filters = await derive_vacancy_filters(session, company_id, vacancy_id)

    # Получаем название вакансии
    vacancy_result = await session.execute(
        select(Vacancy.name).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
            Vacancy.deleted_at.is_(None)
        )
    )
    vacancy = vacancy_result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия")

    # Выполняем поиск
    search_result = await search_base(
        session,
        company_id,
        role=filters.get("professional_role", ""),
        skills=filters.get("skills", []),
        city="",  # Город из вакансии не используем
        salary_from=None,  # ЗП из вакансии не используем для фильтрации
        salary_to=None
    )

    # Приводим фильтры вакансии (area/professional_role/experience/skills)
    # к форме BaseSearchCriteria (role/skills/city/salary_from/salary_to),
    # иначе Pydantic-валидация ответа упадёт → 500 на vacancy-поиске.
    return {
        **search_result,
        "criteria": {
            "role": filters.get("professional_role", ""),
            "skills": filters.get("skills", []),
            "city": "",
            "salary_from": None,
            "salary_to": None,
        },
        "vacancy_title": vacancy,
    }


async def create_search_run(
    session: AsyncSession,
    company_id: UUID,
    search_type: str,
    query_text: str,
    vacancy_id: Optional[UUID],
    found_count: int
) -> BaseSearchRun:
    """Создаёт запись истории поиска"""
    run = BaseSearchRun(
        company_id=company_id,
        search_type=search_type,
        query_text=query_text,
        vacancy_id=vacancy_id,
        found=found_count
    )
    session.add(run)
    await session.flush()
    return run


async def increment_added_to_funnel(
    session: AsyncSession,
    company_id: UUID,
    run_id: UUID
) -> None:
    """Увеличивает счётчик added_to_funnel для записи поиска"""
    result = await session.execute(
        select(BaseSearchRun).where(
            BaseSearchRun.id == run_id,
            BaseSearchRun.company_id == company_id
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundError("Запись поиска")

    run.added_to_funnel += 1
    await session.flush()


async def get_search_runs(
    session: AsyncSession,
    company_id: UUID,
    limit: int = 20
) -> list[BaseSearchRun]:
    """Получает историю поиска компании"""
    stmt = (
        select(BaseSearchRun)
        .where(BaseSearchRun.company_id == company_id)
        .order_by(BaseSearchRun.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_candidates_count(
    session: AsyncSession,
    company_id: UUID
) -> int:
    """Возвращает количество кандидатов в базе компании"""
    stmt = select(func.count(Candidate.id)).where(
        Candidate.company_id == company_id,
        Candidate.deleted_at.is_(None)
    )
    result = await session.execute(stmt)
    return result.scalar_one()