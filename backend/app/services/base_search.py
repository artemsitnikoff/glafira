"""Сервис поиска по собственной базе кандидатов"""

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, exists, and_, or_, func, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..core.errors import NotFoundError, GlafiraParseError
from ..database import AsyncSessionLocal
from ..models import (
    Candidate, CandidateSkill, CandidateExperience, Consent, Vacancy, BaseSearchRun, CandidateEmbedding
)
from ..services.embeddings import build_candidate_text, source_hash, embed_query, embed_texts
from ..services.glafira.client import call_json
from ..services.glafira.scoring import score_resume_dict
from ..services.smart_search import derive_vacancy_filters
from ..services.candidate_format import _compute_age, _compute_full_name

logger = logging.getLogger(__name__)


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
    vacancy_id: UUID,
    override: Optional[dict] = None,
) -> dict:
    """
    Поиск кандидатов по критериям вакансии.

    Args:
        session: Сессия БД
        company_id: ID компании
        vacancy_id: ID вакансии
        override: критерии {role, skills, city, salary_from, salary_to} от фронта
            (отредактированные рекрутёром автофильтры). Если None — derive из вакансии.

    Returns:
        dict: {total, results, criteria(BaseSearchCriteria-форма), vacancy_title}
    """
    # Название вакансии (и проверка принадлежности company)
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

    # Критерии: либо присланные фронтом (правленые автофильтры), либо derive из вакансии.
    # В ЛЮБОМ случае приводим к форме BaseSearchCriteria (role/skills/city/salary_*),
    # иначе Pydantic-валидация ответа упадёт → 500.
    if override is not None:
        criteria = {
            "role": override.get("role") or "",
            "skills": override.get("skills") or [],
            "city": override.get("city") or "",
            "salary_from": override.get("salary_from"),
            "salary_to": override.get("salary_to"),
        }
    else:
        filters = await derive_vacancy_filters(session, company_id, vacancy_id)
        criteria = {
            "role": filters.get("professional_role", ""),
            "skills": filters.get("skills", []),
            "city": filters.get("city", ""),
            "salary_from": filters.get("salary_from"),
            "salary_to": filters.get("salary_to"),
        }

    search_result = await search_base(
        session,
        company_id,
        role=criteria["role"],
        skills=criteria["skills"],
        city=criteria["city"],
        salary_from=criteria["salary_from"],
        salary_to=criteria["salary_to"],
    )

    return {
        **search_result,
        "criteria": criteria,
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


# === СЕМАНТИЧЕСКИЙ ПОИСК (Retrieve→Rerank) ===

# Глобальные фоновые задачи для GC-защиты
_active_tasks = set()

# Константы
GLAFIRA_RETRIEVE_CAP = int(getattr(settings, 'GLAFIRA_RETRIEVE_CAP', 150))
GLAFIRA_RERANK_CAP = int(getattr(settings, 'GLAFIRA_RERANK_CAP', 24))


async def vector_retrieve(
    session: AsyncSession,
    company_id: UUID,
    query_text: str,
    k: int = GLAFIRA_RETRIEVE_CAP
) -> list[UUID]:
    """
    Векторный поиск кандидатов по семантической близости

    Args:
        session: Сессия БД
        company_id: ID компании
        query_text: Текст запроса
        k: Количество ближайших кандидатов

    Returns:
        list[UUID]: Список ID кандидатов, отсортированных по релевантности
    """
    try:
        # Создаём эмбеддинг для запроса
        query_embedding = await embed_query(query_text)
        if not query_embedding:
            logger.warning("Не удалось создать эмбеддинг для запроса, возвращаем пустой список")
            return []

        # Проверяем наличие эмбеддингов в базе
        count_stmt = select(func.count(CandidateEmbedding.id)).where(
            CandidateEmbedding.company_id == company_id
        )
        count_result = await session.execute(count_stmt)
        embeddings_count = count_result.scalar_one()

        if embeddings_count == 0:
            logger.info(f"Нет эмбеддингов для компании {company_id}, возвращаем пустой список")
            return []

        # Выполняем векторный поиск (cosine distance). JOIN на Candidate с deleted_at IS NULL,
        # чтобы удалённые кандидаты (их эмбеддинги ещё могут висеть) не занимали слоты шорт-листа.
        stmt = (
            select(CandidateEmbedding.candidate_id)
            .join(Candidate, Candidate.id == CandidateEmbedding.candidate_id)
            .where(
                CandidateEmbedding.company_id == company_id,
                Candidate.deleted_at.is_(None),
            )
            .order_by(CandidateEmbedding.embedding.cosine_distance(query_embedding))
            .limit(k)
        )

        result = await session.execute(stmt)
        candidate_ids = [row[0] for row in result.fetchall()]

        logger.info(f"Векторный поиск нашёл {len(candidate_ids)} кандидатов для компании {company_id}")
        return candidate_ids

    except Exception as e:
        logger.error(f"Ошибка векторного поиска: {e}")
        return []


async def search_base_semantic(
    session: AsyncSession,
    company_id: UUID,
    *,
    role: str = "",
    skills: list[str] = None,
    city: str = "",
    salary_from: Optional[int] = None,
    salary_to: Optional[int] = None,
    query_text: Optional[str] = None,
    vacancy: Optional["Vacancy"] = None
) -> dict:
    """
    Гибридный поиск кандидатов: SQL-фильтры + векторный поиск + LLM rerank

    Args:
        session: Сессия БД
        company_id: ID компании
        role: Должность для поиска
        skills: Список навыков
        city: Город
        salary_from: Минимальная зарплата
        salary_to: Максимальная зарплата
        query_text: Текст для семантического поиска
        vacancy: Вакансия для скоринга (если есть)

    Returns:
        dict: {total: int, results: list[dict]}
    """
    if skills is None:
        skills = []

    # 1. SQL-канал (существующий фильтровый поиск)
    try:
        sql_search_result = await search_base(
            session, company_id,
            role=role, skills=skills, city=city,
            salary_from=salary_from, salary_to=salary_to
        )
        sql_candidate_ids = [candidate["id"] for candidate in sql_search_result["results"]]
        logger.info(f"SQL-канал нашёл {len(sql_candidate_ids)} кандидатов")
    except Exception as e:
        logger.error(f"Ошибка SQL-канала: {e}")
        sql_candidate_ids = []

    # 2. Векторный канал (если есть query_text)
    vector_candidate_ids = []
    if query_text:
        try:
            vector_candidate_ids = await vector_retrieve(session, company_id, query_text, GLAFIRA_RETRIEVE_CAP)
            logger.info(f"Векторный канал нашёл {len(vector_candidate_ids)} кандидатов")
        except Exception as e:
            logger.error(f"Ошибка векторного канала: {e}")

    # 3. Объединение каналов (UNION + дедупликация)
    all_candidate_ids = list(dict.fromkeys(sql_candidate_ids + vector_candidate_ids))
    shortlist_candidate_ids = all_candidate_ids[:GLAFIRA_RETRIEVE_CAP]

    if not shortlist_candidate_ids:
        logger.info("Объединённый шорт-лист пуст, возвращаем fallback на SQL")
        return sql_search_result

    logger.info(f"Шорт-лист после объединения: {len(shortlist_candidate_ids)} кандидатов (лимит {GLAFIRA_RETRIEVE_CAP})")

    # 4. Загружаем полные данные кандидатов для rerank
    candidates_data = await _load_candidates_for_rerank(session, company_id, shortlist_candidate_ids)

    # 5. LLM Rerank (если есть вакансия или query_text для скоринга)
    if vacancy or query_text:
        try:
            ranked_candidates = await _rerank_candidates(
                candidates_data, vacancy, query_text, company_id, shortlist_candidate_ids
            )
        except Exception as e:
            logger.error(f"Ошибка rerank: {e}")
            # Fallback: возвращаем кандидатов без LLM-скоринга
            ranked_candidates = candidates_data

    else:
        # Без rerank — просто возвращаем в порядке shortlist
        ranked_candidates = candidates_data

    # 6. Формируем результат
    total = len(ranked_candidates)
    results = []

    for candidate_data in ranked_candidates:
        candidate = candidate_data["candidate"]
        candidate_skills = candidate_data["skills"]

        # Подсчёт совпадающих навыков (как в оригинальном search_base)
        matched_skills = []
        if skills:
            for req_skill in skills:
                for cand_skill in candidate_skills:
                    if req_skill.lower() in cand_skill.skill.lower():
                        matched_skills.append(cand_skill.skill)
                        break

        # Процент совпадения (LLM score если есть, иначе overlap как в SQL)
        match_percent = candidate_data.get("llm_score")
        if match_percent is None and skills:
            match_percent = round(len(matched_skills) / len(skills) * 100)

        results.append({
            "id": candidate.id,
            "full_name": _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name),
            "age": _compute_age(candidate.birth_date),
            "last_position": candidate.last_position,
            "last_company": candidate.last_company,
            "last_period": candidate.last_period,
            "city": candidate.city,
            "ai_score": candidate.ai_score,
            "source": candidate.source,
            "salary_expectation": candidate.salary_expectation,
            "matched_skills": matched_skills,
            "all_skills": [skill.skill for skill in candidate_skills],
            "match_percent": match_percent,
            "has_pdn": candidate_data.get("has_pdn", False),
        })

    return {
        "total": total,
        "results": results
    }


async def _load_candidates_for_rerank(
    session: AsyncSession,
    company_id: UUID,
    candidate_ids: list[UUID]
) -> list[dict]:
    """Загружает полные данные кандидатов для rerank"""
    if not candidate_ids:
        return []

    # has_pdn subquery
    has_pdn_subq = (
        select(Consent.id)
        .where(Consent.candidate_id == Candidate.id, Consent.status == "signed")
        .exists()
    )

    # Загружаем кандидатов
    stmt = (
        select(
            Candidate,
            has_pdn_subq.label("has_pdn")
        )
        .where(
            Candidate.id.in_(candidate_ids),
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
        .options(
            selectinload(Candidate.skills),
            selectinload(Candidate.experience)
        )
    )

    result = await session.execute(stmt)
    rows = result.fetchall()

    candidates_data = []
    for row in rows:
        candidate = row.Candidate
        candidates_data.append({
            "candidate": candidate,
            "skills": candidate.skills,
            "experience": candidate.experience,
            "has_pdn": row.has_pdn
        })

    # Сортируем в том же порядке, что и в candidate_ids
    id_to_data = {data["candidate"].id: data for data in candidates_data}
    ordered_data = []
    for cand_id in candidate_ids:
        if cand_id in id_to_data:
            ordered_data.append(id_to_data[cand_id])

    return ordered_data


async def _rerank_candidates(
    candidates_data: list[dict],
    vacancy: Optional["Vacancy"],
    query_text: Optional[str],
    company_id: UUID,
    original_order: list[UUID]
) -> list[dict]:
    """
    Ранжирует кандидатов с помощью LLM (конкурентно с семафором)

    Обрезает до GLAFIRA_RERANK_CAP для синхронного выполнения в HTTP-таймауте
    """
    if not candidates_data:
        return candidates_data

    # Ограничиваем количество для rerank (синхронный запрос, не async job)
    rerank_candidates = candidates_data[:GLAFIRA_RERANK_CAP]
    remaining_candidates = candidates_data[GLAFIRA_RERANK_CAP:]

    if not rerank_candidates:
        return candidates_data

    logger.info(f"Rerank для {len(rerank_candidates)} кандидатов (лимит {GLAFIRA_RERANK_CAP})")

    # Семафор для ограничения конкурентных LLM запросов
    semaphore = asyncio.Semaphore(6)

    async def score_candidate(candidate_data):
        async with semaphore:
            try:
                # Собираем candidate → hh_resume_dict для score_resume_dict
                candidate = candidate_data["candidate"]
                resume_dict = _candidate_to_resume_dict(candidate_data)

                if vacancy:
                    # Скоринг против вакансии
                    score_data = await score_resume_dict(resume_dict, vacancy, company_id)
                else:
                    # Скоринг против query_text как синтетической вакансии
                    synthetic_vacancy = _create_synthetic_vacancy_for_scoring(query_text)
                    score_data = await score_resume_dict(resume_dict, synthetic_vacancy, company_id)

                candidate_data["llm_score"] = score_data.get("score", 0)
                candidate_data["llm_verdict"] = score_data.get("verdict", "unknown")
                candidate_data["requirements_match"] = score_data.get("requirements_match", [])

                return candidate_data

            except Exception as e:
                logger.error(f"Ошибка скоринга кандидата {candidate_data['candidate'].id}: {e}")
                # При ошибке одного кандидата — пропускаем его, не ломаем весь rerank
                candidate_data["llm_score"] = None
                return candidate_data

    # Выполняем скоринг конкурентно
    scored_candidates = await asyncio.gather(*[score_candidate(data) for data in rerank_candidates])

    # Фильтруем кандидатов, у которых сломался скоринг
    valid_scored = [data for data in scored_candidates if data["llm_score"] is not None]

    # C2: если ВСЕ оценки провалились (пустой OPENROUTER_API_KEY / системный отказ OpenRouter) —
    # НЕ возвращаем пустоту, а деградируем на заход A (overlap%): отдать кандидатов без балла,
    # result builder посчитает overlap. Иначе промт-поиск молча вернул бы 0 результатов.
    if not valid_scored:
        logger.warning("Rerank: ВСЕ LLM-оценки провалились — fallback на overlap (заход A)")
        return candidates_data

    # Сортируем по LLM score (убывание)
    valid_scored.sort(key=lambda x: x["llm_score"], reverse=True)

    # Добавляем оставшихся кандидатов (сверх rerank-лимита) в исходном порядке
    return valid_scored + remaining_candidates


def _candidate_to_resume_dict(candidate_data: dict) -> dict:
    """Конвертирует данные кандидата в формат hh_resume для score_resume_dict"""
    candidate = candidate_data["candidate"]
    skills = candidate_data["skills"]
    experience = candidate_data["experience"]

    # Формат как hh.ru resume
    resume_dict = {
        "first_name": candidate.first_name or "",
        "last_name": candidate.last_name or "",
        "area": {"name": candidate.city or ""},
        "skills": [skill.skill for skill in skills if skill.skill],
        "title": candidate.last_position or "",
        "description": candidate.resume_summary or candidate.resume_text or "",
        "experience": []
    }

    # Добавляем опыт работы
    for exp in experience:
        exp_dict = {
            "position": exp.position or "",
            "company": exp.company or "",
            "description": exp.description or ""
        }
        resume_dict["experience"].append(exp_dict)

    # Зарплата
    if candidate.salary_expectation:
        resume_dict["salary"] = {
            "from": candidate.salary_expectation,
            "currency": candidate.currency or "RUB"
        }

    return resume_dict


def _create_synthetic_vacancy_for_scoring(query_text: str):
    """Создаёт синтетическую вакансию из query_text для скоринга"""
    # Простая заглушка — в реальности можно сделать LLM-парсинг query → vacancy fields
    class SyntheticVacancy:
        def __init__(self, query):
            self.name = f"Поиск: {query}"
            self.description = query
            self.salary_from = None
            self.salary_to = None
            self.currency = "RUB"
            self.city = None
            # score_resume_dict читает и эти поля — без них AttributeError → весь rerank
            # промт-метода отсеивался бы в None → пустая выдача.
            self.recruiter_scoring_instructions = None
            self.glafira_mode = None
            self.auto_move = False
            self.auto_move_threshold = None

    return SyntheticVacancy(query_text)


# === ИНДЕКСАЦИЯ ЭМБЕДДИНГОВ ===

async def reindex_candidate(
    session: AsyncSession,
    company_id: UUID,
    candidate_id: UUID
) -> None:
    """
    Инкрементальная переиндексация одного кандидата
    (вызывается при создании/изменении кандидата)

    Args:
        session: Сессия БД
        company_id: ID компании
        candidate_id: ID кандидата
    """
    try:
        # Загружаем кандидата с навыками и опытом
        stmt = (
            select(Candidate)
            .where(
                Candidate.id == candidate_id,
                Candidate.company_id == company_id,
                Candidate.deleted_at.is_(None)
            )
            .options(
                selectinload(Candidate.skills),
                selectinload(Candidate.experience)
            )
        )
        result = await session.execute(stmt)
        candidate = result.scalar_one_or_none()

        if not candidate:
            logger.warning(f"Кандидат {candidate_id} не найден для переиндексации")
            return

        # Строим текст кандидата
        candidate_text = build_candidate_text(candidate, candidate.skills, candidate.experience)
        if not candidate_text:
            logger.info(f"Пустой текст для кандидата {candidate_id}, пропускаем индексацию")
            return

        new_hash = source_hash(candidate_text)

        # Проверяем существующий эмбеддинг
        existing_stmt = select(CandidateEmbedding).where(
            CandidateEmbedding.candidate_id == candidate_id,
            CandidateEmbedding.company_id == company_id
        )
        existing_result = await session.execute(existing_stmt)
        existing_embedding = existing_result.scalar_one_or_none()

        # Если хеш не изменился — пропускаем
        if existing_embedding and existing_embedding.source_hash == new_hash:
            logger.debug(f"Хеш кандидата {candidate_id} не изменился, пропускаем переиндексацию")
            return

        # Создаём новый эмбеддинг
        embeddings = await embed_texts([candidate_text])
        if not embeddings or not embeddings[0]:
            logger.error(f"Не удалось создать эмбеддинг для кандидата {candidate_id}")
            return

        embedding_vector = embeddings[0]

        # Upsert эмбеддинга
        if existing_embedding:
            # Обновляем существующий
            update_stmt = (
                update(CandidateEmbedding)
                .where(CandidateEmbedding.candidate_id == candidate_id)
                .values(
                    embedding=embedding_vector,
                    source_hash=new_hash,
                    updated_at=func.now()
                )
            )
            await session.execute(update_stmt)
            logger.info(f"Обновлён эмбеддинг для кандидата {candidate_id}")
        else:
            # Создаём новый
            new_embedding = CandidateEmbedding(
                company_id=company_id,
                candidate_id=candidate_id,
                embedding=embedding_vector,
                source_hash=new_hash
            )
            session.add(new_embedding)
            logger.info(f"Создан эмбеддинг для кандидата {candidate_id}")

        await session.flush()

    except Exception as e:
        logger.error(f"Ошибка переиндексации кандидата {candidate_id}: {e}")


# company_id'ы, для которых СЕЙЧАС идёт полная переиндексация. Нужен, чтобы index-status
# отдавал indexing=true/false, а фронт останавливал поллинг по ФЛАГУ, а НЕ по indexed==total:
# часть кандидатов без текста резюме никогда не индексируется → indexed<total это норма.
_reindex_in_progress: set = set()


async def reindex_all_embeddings(company_id: Optional[UUID] = None) -> None:
    """
    Фоновая задача полной переиндексации эмбеддингов
    (паттерн как в candidate_import)

    Args:
        company_id: ID компании (если None — все компании)
    """

    async def _run_reindex():
        try:
            logger.info(f"Начинаем полную переиндексацию эмбеддингов для компании {company_id}")

            # Короткие сессии для батчей
            async with AsyncSessionLocal() as session:
                # Определяем общее количество кандидатов
                count_filter = [Candidate.deleted_at.is_(None)]
                if company_id:
                    count_filter.append(Candidate.company_id == company_id)

                count_stmt = select(func.count(Candidate.id)).where(and_(*count_filter))
                count_result = await session.execute(count_stmt)
                total_candidates = count_result.scalar_one()

                logger.info(f"Найдено {total_candidates} кандидатов для индексации")

                if total_candidates == 0:
                    logger.info("Нет кандидатов для индексации")
                    return

            # Батчевая обработка
            batch_size = 200
            processed = 0

            for offset in range(0, total_candidates, batch_size):
                try:
                    async with AsyncSessionLocal() as session:
                        # Загружаем батч кандидатов
                        stmt = (
                            select(Candidate)
                            .where(and_(*count_filter))
                            .options(
                                selectinload(Candidate.skills),
                                selectinload(Candidate.experience)
                            )
                            .offset(offset)
                            .limit(batch_size)
                        )
                        result = await session.execute(stmt)
                        candidates = result.scalars().all()

                        # Обрабатываем каждого кандидата в батче
                        for candidate in candidates:
                            try:
                                await reindex_candidate(session, candidate.company_id, candidate.id)
                                processed += 1

                                if processed % 50 == 0:
                                    logger.info(f"Проиндексировано {processed}/{total_candidates} кандидатов")

                            except Exception as e:
                                logger.error(f"Ошибка индексации кандидата {candidate.id}: {e}")
                                continue

                        await session.commit()

                except Exception as e:
                    logger.error(f"Ошибка обработки батча offset={offset}: {e}")
                    continue

            logger.info(f"Завершена переиндексация: {processed}/{total_candidates} кандидатов")

        except Exception as e:
            logger.error(f"Критическая ошибка переиндексации: {e}")

        finally:
            # Снимаем флаг «идёт индексация» + задачу из активных (GC-защита)
            _reindex_in_progress.discard(company_id)
            _active_tasks.discard(asyncio.current_task())

    # Помечаем «идёт индексация» ДО старта задачи (status сразу отдаст indexing=true)
    _reindex_in_progress.add(company_id)
    # Создаём фоновую задачу
    task = asyncio.create_task(_run_reindex())
    _active_tasks.add(task)

    # Автоудаление при завершении
    task.add_done_callback(lambda t: _active_tasks.discard(t))

    return task


async def get_embeddings_index_status(
    session: AsyncSession,
    company_id: UUID
) -> dict:
    """
    Получает статус индексации эмбеддингов для компании

    Args:
        session: Сессия БД
        company_id: ID компании

    Returns:
        dict: {"total_candidates": int, "indexed_candidates": int}
    """
    # Общее количество кандидатов
    total_stmt = select(func.count(Candidate.id)).where(
        Candidate.company_id == company_id,
        Candidate.deleted_at.is_(None)
    )
    total_result = await session.execute(total_stmt)
    total_candidates = total_result.scalar_one()

    # Количество проиндексированных
    indexed_stmt = select(func.count(CandidateEmbedding.id)).where(
        CandidateEmbedding.company_id == company_id
    )
    indexed_result = await session.execute(indexed_stmt)
    indexed_candidates = indexed_result.scalar_one()

    return {
        "total_candidates": total_candidates,
        "indexed_candidates": indexed_candidates,
        # idle/indexing для остановки поллинга на фронте (не по indexed==total)
        "indexing": company_id in _reindex_in_progress,
        # для (пока disabled) селектора модели в админ-вкладке AI
        "model": settings.GLAFIRA_MODEL,
        "embed_model": settings.GLAFIRA_EMBED_MODEL,
    }


# === АСИНХРОННЫЙ ПОИСК (паттерн как smart_search) ===

async def start_base_search(
    session: AsyncSession,
    company_id: UUID,
    search_type: str,
    query: str,
    vacancy_id: Optional[UUID],
    override: Optional[dict] = None
) -> UUID:
    """
    Запускает асинхронный поиск по собственной базе

    Args:
        session: Сессия БД
        company_id: ID компании
        search_type: 'prompt' или 'vacancy'
        query: Текст запроса
        vacancy_id: ID вакансии (для search_type='vacancy')
        override: Критерии поиска (отредактированные автофильтры)

    Returns:
        UUID: ID созданного run'а
    """
    # Получаем название вакансии и критерии для промпта
    vacancy_title = None
    query_echo = query
    criteria = None

    if search_type == "vacancy":
        # Проверяем вакансию
        vacancy_stmt = select(Vacancy.name).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
            Vacancy.deleted_at.is_(None)
        )
        vacancy_result = await session.execute(vacancy_stmt)
        vacancy_name = vacancy_result.scalar_one_or_none()
        if not vacancy_name:
            raise NotFoundError("Вакансия")

        vacancy_title = vacancy_name
        query_echo = vacancy_name

        # Критерии: либо переданные (override), либо derive из вакансии
        if override:
            criteria = {
                "role": override.get("role", ""),
                "skills": override.get("skills", []),
                "city": override.get("city", ""),
                "salary_from": override.get("salary_from"),
                "salary_to": override.get("salary_to"),
            }
        else:
            filters = await derive_vacancy_filters(session, company_id, vacancy_id)
            criteria = {
                "role": filters.get("professional_role", ""),
                "skills": filters.get("skills", []),
                "city": filters.get("city", ""),
                "salary_from": filters.get("salary_from"),
                "salary_to": filters.get("salary_to"),
            }

    elif search_type == "prompt":
        # Парсим запрос через LLM
        criteria = await parse_query_to_criteria(query)

    # Создаём run
    search_run = BaseSearchRun(
        company_id=company_id,
        search_type=search_type,
        query_text=query,
        vacancy_id=vacancy_id,
        status="running",
        stage="retrieve",
        query_echo=query_echo,
        vacancy_title=vacancy_title,
        criteria=criteria
    )
    session.add(search_run)
    await session.commit()
    await session.refresh(search_run)

    # Запускаем фоновую задачу
    task = asyncio.create_task(_run_base_search(search_run.id, company_id, search_type, query, vacancy_id, override))
    _active_tasks.add(task)

    # Автоудаление при завершении
    task.add_done_callback(lambda t: _active_tasks.discard(t))

    return search_run.id


async def _run_base_search(
    run_id: UUID,
    company_id: UUID,
    search_type: str,
    query: str,
    vacancy_id: Optional[UUID],
    override: Optional[dict]
):
    """
    Фоновая задача выполнения поиска по базе
    """
    try:
        # Загружаем run и критерии
        async with AsyncSessionLocal() as session:
            run = await session.get(BaseSearchRun, run_id)
            if not run:
                logger.error(f"BaseSearchRun {run_id} не найден")
                return

            criteria = run.criteria or {}

        # Этап retrieve: SQL + векторный поиск + шорт-лист
        try:
            async with AsyncSessionLocal() as session:
                # SQL-канал
                sql_search_result = await search_base(
                    session, company_id,
                    role=criteria.get("role", ""),
                    skills=criteria.get("skills", []),
                    city=criteria.get("city", ""),
                    salary_from=criteria.get("salary_from"),
                    salary_to=criteria.get("salary_to")
                )
                sql_candidate_ids = [candidate["id"] for candidate in sql_search_result["results"]]
                logger.info(f"SQL-канал нашёл {len(sql_candidate_ids)} кандидатов")

                # Векторный канал (если есть query для семантического поиска)
                vector_candidate_ids = []
                if search_type == "prompt" or (search_type == "vacancy" and query):
                    try:
                        vector_candidate_ids = await vector_retrieve(session, company_id, query, GLAFIRA_RETRIEVE_CAP)
                        logger.info(f"Векторный канал нашёл {len(vector_candidate_ids)} кандидатов")
                    except Exception as e:
                        logger.error(f"Ошибка векторного канала: {e}")

                # Объединение каналов
                all_candidate_ids = list(dict.fromkeys(sql_candidate_ids + vector_candidate_ids))
                shortlist_candidate_ids = all_candidate_ids[:GLAFIRA_RETRIEVE_CAP]

                if not shortlist_candidate_ids:
                    # Graceful: возвращаем SQL результаты без rerank
                    await _finalize_base_search(
                        run_id, "done", "done",
                        results=sql_search_result["results"],
                        found=len(sql_search_result["results"]),
                        to_evaluate=0, evaluated=0
                    )
                    return

                # Обновляем прогресс
                await _update_base_search_progress(
                    run_id,
                    found=len(shortlist_candidate_ids),
                    to_evaluate=min(len(shortlist_candidate_ids), GLAFIRA_RERANK_CAP),
                    stage="rerank"
                )

        except Exception as e:
            logger.error(f"Ошибка на этапе retrieve: {e}")
            await _finalize_base_search(run_id, "error", "retrieve", error=str(e)[:500])
            return

        # Этап rerank: загружаем кандидатов и оцениваем через LLM
        try:
            async with AsyncSessionLocal() as session:
                # Загружаем полные данные кандидатов
                candidates_data = await _load_candidates_for_rerank(session, company_id, shortlist_candidate_ids)

                # Получаем вакансию для скоринга (если нужно)
                vacancy = None
                if vacancy_id:
                    vacancy_stmt = select(Vacancy).where(
                        Vacancy.id == vacancy_id,
                        Vacancy.company_id == company_id,
                        Vacancy.deleted_at.is_(None)
                    )
                    vacancy_result = await session.execute(vacancy_stmt)
                    vacancy = vacancy_result.scalar_one_or_none()

                # Rerank с прогрессом
                ranked_candidates = await _rerank_candidates_with_progress(
                    candidates_data, vacancy, query if search_type == "prompt" else None,
                    company_id, run_id
                )

                # Формируем результат в том же формате, что и search_base_semantic
                results = []
                for candidate_data in ranked_candidates:
                    candidate = candidate_data["candidate"]
                    candidate_skills = candidate_data["skills"]

                    # Подсчёт совпадающих навыков
                    matched_skills = []
                    skills = criteria.get("skills", [])
                    if skills:
                        for req_skill in skills:
                            for cand_skill in candidate_skills:
                                if req_skill.lower() in cand_skill.skill.lower():
                                    matched_skills.append(cand_skill.skill)
                                    break

                    # Процент совпадения
                    match_percent = candidate_data.get("llm_score")
                    if match_percent is None and skills:
                        match_percent = round(len(matched_skills) / len(skills) * 100)

                    results.append({
                        "id": candidate.id,
                        "full_name": _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name),
                        "age": _compute_age(candidate.birth_date),
                        "last_position": candidate.last_position,
                        "last_company": candidate.last_company,
                        "last_period": candidate.last_period,
                        "city": candidate.city,
                        "ai_score": candidate.ai_score,
                        "source": candidate.source,
                        "salary_expectation": candidate.salary_expectation,
                        "matched_skills": matched_skills,
                        "all_skills": [skill.skill for skill in candidate_skills],
                        "match_percent": match_percent,
                        "has_pdn": candidate_data.get("has_pdn", False),
                    })

                # Финализируем
                await _finalize_base_search(
                    run_id, "done", "done",
                    results=results,
                    found=len(shortlist_candidate_ids),
                    to_evaluate=len(candidates_data[:GLAFIRA_RERANK_CAP]),
                    evaluated=len(ranked_candidates)
                )

        except Exception as e:
            logger.error(f"Ошибка на этапе rerank: {e}")
            # Graceful: возвращаем результаты без LLM-скоринга
            try:
                async with AsyncSessionLocal() as session:
                    candidates_data = await _load_candidates_for_rerank(session, company_id, shortlist_candidate_ids)

                    # Формируем результат без rerank
                    results = []
                    for candidate_data in candidates_data:
                        candidate = candidate_data["candidate"]
                        candidate_skills = candidate_data["skills"]

                        matched_skills = []
                        skills = criteria.get("skills", [])
                        if skills:
                            for req_skill in skills:
                                for cand_skill in candidate_skills:
                                    if req_skill.lower() in cand_skill.skill.lower():
                                        matched_skills.append(cand_skill.skill)
                                        break

                        match_percent = None
                        if skills:
                            match_percent = round(len(matched_skills) / len(skills) * 100)

                        results.append({
                            "id": candidate.id,
                            "full_name": _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name),
                            "age": _compute_age(candidate.birth_date),
                            "last_position": candidate.last_position,
                            "last_company": candidate.last_company,
                            "last_period": candidate.last_period,
                            "city": candidate.city,
                            "ai_score": candidate.ai_score,
                            "source": candidate.source,
                            "salary_expectation": candidate.salary_expectation,
                            "matched_skills": matched_skills,
                            "all_skills": [skill.skill for skill in candidate_skills],
                            "match_percent": match_percent,
                            "has_pdn": candidate_data.get("has_pdn", False),
                        })

                    await _finalize_base_search(
                        run_id, "done", "done",
                        results=results,
                        found=len(shortlist_candidate_ids),
                        to_evaluate=len(candidates_data[:GLAFIRA_RERANK_CAP]),
                        evaluated=0  # Без rerank
                    )
            except Exception as fallback_error:
                logger.error(f"Ошибка graceful fallback: {fallback_error}")
                await _finalize_base_search(run_id, "error", "rerank", error=str(e)[:500])

    except Exception as e:
        logger.error(f"Критическая ошибка базового поиска {run_id}: {e}")
        await _finalize_base_search(run_id, "error", None, error=str(e)[:500])
    finally:
        # Убираем задачу из активных
        _active_tasks.discard(asyncio.current_task())


async def _rerank_candidates_with_progress(
    candidates_data: list[dict],
    vacancy: Optional["Vacancy"],
    query_text: Optional[str],
    company_id: UUID,
    run_id: UUID
) -> list[dict]:
    """
    Ранжирует кандидатов с помощью LLM с обновлением прогресса
    """
    if not candidates_data:
        return candidates_data

    # Ограничиваем для rerank
    rerank_candidates = candidates_data[:GLAFIRA_RERANK_CAP]
    remaining_candidates = candidates_data[GLAFIRA_RERANK_CAP:]

    if not rerank_candidates:
        return candidates_data

    logger.info(f"Rerank для {len(rerank_candidates)} кандидатов")

    # Семафор для ограничения конкурентных LLM запросов
    semaphore = asyncio.Semaphore(6)
    evaluated_count = 0

    async def score_candidate(candidate_data):
        nonlocal evaluated_count
        async with semaphore:
            try:
                candidate = candidate_data["candidate"]
                resume_dict = _candidate_to_resume_dict(candidate_data)

                if vacancy:
                    score_data = await score_resume_dict(resume_dict, vacancy, company_id)
                else:
                    # Скоринг против query как синтетической вакансии
                    synthetic_vacancy = _create_synthetic_vacancy_for_scoring(query_text or "")
                    score_data = await score_resume_dict(resume_dict, synthetic_vacancy, company_id)

                candidate_data["llm_score"] = score_data.get("score", 0)
                candidate_data["llm_verdict"] = score_data.get("verdict", "unknown")
                candidate_data["requirements_match"] = score_data.get("requirements_match", [])

                # Обновляем прогресс
                evaluated_count += 1
                if evaluated_count % 3 == 0:  # Каждые 3 кандидата
                    await _update_base_search_progress(run_id, evaluated=evaluated_count)

                return candidate_data

            except Exception as e:
                logger.error(f"Ошибка скоринга кандидата {candidate_data['candidate'].id}: {e}")
                candidate_data["llm_score"] = None
                return candidate_data

    # Выполняем скоринг конкурентно
    scored_candidates = await asyncio.gather(*[score_candidate(data) for data in rerank_candidates])

    # Финальное обновление прогресса
    await _update_base_search_progress(run_id, evaluated=evaluated_count)

    # Фильтруем успешные оценки
    valid_scored = [data for data in scored_candidates if data["llm_score"] is not None]

    # Если все провалились - graceful fallback
    if not valid_scored:
        logger.warning("Rerank: ВСЕ LLM-оценки провалились — fallback без балла")
        return candidates_data

    # Сортируем по LLM score
    valid_scored.sort(key=lambda x: x["llm_score"], reverse=True)

    return valid_scored + remaining_candidates


async def _update_base_search_progress(run_id: UUID, **updates):
    """Обновляет прогресс выполнения поиска короткой сессией"""
    try:
        async with AsyncSessionLocal() as session:
            run = await session.get(BaseSearchRun, run_id)
            if not run:
                return

            for key, value in updates.items():
                setattr(run, key, value)

            await session.commit()
    except Exception as e:
        logger.warning(f"Ошибка обновления прогресса base search run {run_id}: {e}")


async def _finalize_base_search(
    run_id: UUID,
    status: str,
    stage: Optional[str],
    error: Optional[str] = None,
    results: Optional[list] = None,
    **extra_fields
):
    """Финализирует поиск короткой сессией"""
    try:
        async with AsyncSessionLocal() as session:
            run = await session.get(BaseSearchRun, run_id)
            if not run:
                logger.error(f"BaseSearchRun {run_id} не найден при финализации")
                return

            run.status = status
            if stage:
                run.stage = stage
            if error:
                run.error = error[:500]
            if results is not None:
                run.results = results

            # Время завершения (naive UTC как в SmartSearchRun)
            run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Применяем дополнительные поля
            for key, value in extra_fields.items():
                setattr(run, key, value)

            await session.commit()
    except Exception as e:
        logger.error(f"Ошибка финализации base search run {run_id}: {e}")


async def get_base_search_run_status(
    session: AsyncSession,
    run_id: UUID,
    company_id: UUID
) -> Optional[BaseSearchRun]:
    """Получает статус выполнения поиска по базе"""
    stmt = select(BaseSearchRun).where(
        BaseSearchRun.id == run_id,
        BaseSearchRun.company_id == company_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def sweep_orphaned_base_search_runs():
    """Очистка осиротевших поисков по базе при старте сервера"""
    try:
        async with AsyncSessionLocal() as session:
            # Находим running поиски старше 60 минут
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=60)

            result = await session.execute(
                update(BaseSearchRun)
                .where(
                    and_(
                        BaseSearchRun.status == "running",
                        BaseSearchRun.updated_at < cutoff_time
                    )
                )
                .values(
                    status="error",
                    error="Прервано (зависание/перезапуск)",
                    finished_at=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                .returning(BaseSearchRun.id)
            )

            orphaned_ids = result.scalars().all()
            if orphaned_ids:
                await session.commit()
                logger.info(f"Очищено {len(orphaned_ids)} осиротевших поисков базы")

    except Exception as e:
        logger.warning(f"Ошибка очистки осиротевших поисков базы: {e}")