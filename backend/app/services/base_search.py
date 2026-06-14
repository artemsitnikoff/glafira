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
from ..core.errors import NotFoundError, GlafiraParseError, OpenRouterNotConfiguredError
from ..database import AsyncSessionLocal
from ..models import (
    Candidate, CandidateSkill, CandidateExperience, Consent, Vacancy, BaseSearchRun, CandidateEmbedding
)
from ..services.embeddings import build_candidate_text, source_hash, embed_query, embed_texts
from ..services.glafira.client import call_json
from ..services.glafira.scoring import score_resume_dict
from ..services.settings.glafira import get_company_openrouter_key
from ..services.smart_search import derive_vacancy_filters
from ..services.candidate_format import _compute_age, _compute_full_name

logger = logging.getLogger(__name__)


def cosine_to_percent(distance: float) -> int:
    """
    Конвертирует косинусную дистанцию в процент совпадения

    Args:
        distance: Косинусная дистанция (0.0 - идеальное совпадение, 1.0 - полная противоположность)

    Returns:
        int: Процент совпадения (0-100)
    """
    return max(0, min(100, round((1.0 - distance) * 100)))


async def _calculate_evaluate_timeout(n: int) -> int:
    """
    Вычисляет таймаут для фазы EVALUATE на основе числа кандидатов для LLM-оценки

    Args:
        n: Количество кандидатов для оценки

    Returns:
        int: Таймаут в секундах
    """
    # Реалистичный таймаут: базовые 900с + по 200с на каждого кандидата
    # (LLM score_resume_dict с ретраями до ~180с + накладные расходы)
    return max(900, n * 200)


async def parse_query_to_criteria(query: str, api_key: str) -> dict:
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
            api_key=api_key,
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
            Candidate.salary_from,
            Candidate.salary_to,
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
            "salary_from": candidate.salary_from,
            "salary_to": candidate.salary_to,
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
# Предохранитель расхода: верхний предел N для ручной AI-оценки (фаза EVALUATE).
# Защита от опечатки/runaway (каждый = LLM-вызов = деньги). Пользователь выбирает N в инпуте.
GLAFIRA_MAX_EVALUATE = int(getattr(settings, 'GLAFIRA_MAX_EVALUATE', 100))


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

        # Проверяем наличие эмбеддингов в базе (EXISTS вместо COUNT для производительности)
        exists_stmt = select(CandidateEmbedding.id).where(
            CandidateEmbedding.company_id == company_id
        ).limit(1)
        exists_result = await session.execute(exists_stmt)
        has_embeddings = exists_result.first() is not None

        if not has_embeddings:
            logger.info(f"Нет эмбеддингов для компании {company_id}, возвращаем пустой список")
            return []

        # Устанавливаем ef_search для HNSW (должно быть >= k для полного top-k)
        ef = max(int(getattr(settings, 'GLAFIRA_HNSW_EF_SEARCH', 300)), k)
        await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef)}"))

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


async def vector_retrieve_scored(
    session: AsyncSession,
    company_id: UUID,
    query_text: str,
    k: int = GLAFIRA_RETRIEVE_CAP
) -> list[tuple[UUID, float]]:
    """
    Векторный поиск кандидатов с возвратом дистанций

    Args:
        session: Сессия БД
        company_id: ID компании
        query_text: Текст запроса
        k: Количество ближайших кандидатов

    Returns:
        list[tuple[UUID, float]]: Список пар (candidate_id, distance), отсортированных по возрастанию дистанции
    """
    try:
        # Создаём эмбеддинг для запроса
        query_embedding = await embed_query(query_text)
        if not query_embedding:
            logger.warning("Не удалось создать эмбеддинг для запроса, возвращаем пустой список")
            return []

        # Проверяем наличие эмбеддингов в базе (EXISTS вместо COUNT для производительности)
        exists_stmt = select(CandidateEmbedding.id).where(
            CandidateEmbedding.company_id == company_id
        ).limit(1)
        exists_result = await session.execute(exists_stmt)
        has_embeddings = exists_result.first() is not None

        if not has_embeddings:
            logger.info(f"Нет эмбеддингов для компании {company_id}, возвращаем пустой список")
            return []

        # Устанавливаем ef_search для HNSW (должно быть >= k для полного top-k)
        ef = max(int(getattr(settings, 'GLAFIRA_HNSW_EF_SEARCH', 300)), k)
        await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef)}"))

        # Выполняем векторный поиск с возвратом дистанций
        stmt = (
            select(
                CandidateEmbedding.candidate_id,
                CandidateEmbedding.embedding.cosine_distance(query_embedding).label('distance')
            )
            .join(Candidate, Candidate.id == CandidateEmbedding.candidate_id)
            .where(
                CandidateEmbedding.company_id == company_id,
                Candidate.deleted_at.is_(None),
            )
            .order_by(CandidateEmbedding.embedding.cosine_distance(query_embedding))
            .limit(k)
        )

        result = await session.execute(stmt)
        candidates_with_distances = [(row.candidate_id, row.distance) for row in result.fetchall()]

        logger.info(f"Векторный поиск нашёл {len(candidates_with_distances)} кандидатов с дистанциями для компании {company_id}")
        return candidates_with_distances

    except Exception as e:
        logger.error(f"Ошибка векторного поиска с дистанциями: {e}")
        return []


def _candidate_to_resume_dict(candidate_data: dict) -> dict:
    """Конвертирует данные кандидата в формат hh_resume для score_resume_dict.
    Используется живым _rerank_candidates_with_progress (промт-метод поиска по базе)."""
    candidate = candidate_data["candidate"]
    skills = candidate_data["skills"]
    experience = candidate_data["experience"]

    resume_dict = {
        "first_name": candidate.first_name or "",
        "last_name": candidate.last_name or "",
        "area": {"name": candidate.city or ""},
        "skills": [skill.skill for skill in skills if skill.skill],
        "title": candidate.last_position or "",
        "description": candidate.resume_summary or candidate.resume_text or "",
        "experience": []
    }

    for exp in experience:
        resume_dict["experience"].append({
            "position": exp.position or "",
            "company": exp.company or "",
            "description": exp.description or ""
        })

    if candidate.salary_expectation:
        resume_dict["salary"] = {
            "from": candidate.salary_expectation,
            "currency": candidate.currency or "RUB"
        }

    return resume_dict


def _create_synthetic_vacancy_for_scoring(query_text: str):
    """Синтетическая вакансия из query_text для скоринга (живой rerank промт-метода)."""
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
    # Guard против двойного запуска
    if company_id in _reindex_in_progress:
        logger.info(f"Переиндексация для компании {company_id} уже идёт — пропускаем повторный запуск")
        return None

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

                        # Собираем тексты всего батча для batch-эмбеддинга
                        batch_texts = []
                        batch_candidates_data = []
                        for candidate in candidates:
                            try:
                                candidate_text = build_candidate_text(candidate, candidate.skills, candidate.experience)
                                if candidate_text:
                                    new_hash = source_hash(candidate_text)

                                    # Проверяем, нужно ли обновление (hash-skip)
                                    existing_stmt = select(CandidateEmbedding).where(
                                        CandidateEmbedding.candidate_id == candidate.id,
                                        CandidateEmbedding.company_id == candidate.company_id
                                    )
                                    existing_result = await session.execute(existing_stmt)
                                    existing_embedding = existing_result.scalar_one_or_none()

                                    if existing_embedding and existing_embedding.source_hash == new_hash:
                                        logger.debug(f"Хеш кандидата {candidate.id} не изменился, пропускаем")
                                        continue

                                    batch_texts.append(candidate_text)
                                    batch_candidates_data.append({
                                        'candidate': candidate,
                                        'text': candidate_text,
                                        'hash': new_hash,
                                        'existing': existing_embedding
                                    })
                            except Exception as e:
                                logger.error(f"Ошибка подготовки кандидата {candidate.id}: {e}")
                                continue

                        # Батчевый вызов embed_texts ОДИН РАЗ на весь батч
                        if batch_texts:
                            try:
                                embeddings = await embed_texts(batch_texts)

                                # Upsert эмбеддингов по порядку
                                for idx, candidate_data in enumerate(batch_candidates_data):
                                    if idx < len(embeddings) and embeddings[idx]:
                                        try:
                                            candidate = candidate_data['candidate']
                                            embedding_vector = embeddings[idx]
                                            new_hash = candidate_data['hash']
                                            existing_embedding = candidate_data['existing']

                                            if existing_embedding:
                                                # Обновляем существующий
                                                update_stmt = (
                                                    update(CandidateEmbedding)
                                                    .where(CandidateEmbedding.candidate_id == candidate.id)
                                                    .values(
                                                        embedding=embedding_vector,
                                                        source_hash=new_hash,
                                                        updated_at=func.now()
                                                    )
                                                )
                                                await session.execute(update_stmt)
                                                logger.debug(f"Обновлён эмбеддинг для кандидата {candidate.id}")
                                            else:
                                                # Создаём новый
                                                new_embedding = CandidateEmbedding(
                                                    company_id=candidate.company_id,
                                                    candidate_id=candidate.id,
                                                    embedding=embedding_vector,
                                                    source_hash=new_hash
                                                )
                                                session.add(new_embedding)
                                                logger.debug(f"Создан эмбеддинг для кандидата {candidate.id}")

                                            processed += 1

                                        except Exception as e:
                                            logger.error(f"Ошибка upsert эмбеддинга {candidate.id}: {e}")
                                            continue

                            except Exception as e:
                                logger.error(f"Ошибка batch embed_texts: {e}")
                                continue

                        if processed % 50 == 0 and processed > 0:
                            logger.info(f"Проиндексировано {processed}/{total_candidates} кандидатов")

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
    # Общее количество кандидатов С ТЕКСТОМ РЕЗЮМЕ (индексируемых)
    total_stmt = select(func.count(Candidate.id)).where(
        Candidate.company_id == company_id,
        Candidate.deleted_at.is_(None),
        Candidate.resume_text.is_not(None),
        Candidate.resume_text != ""
    )
    total_result = await session.execute(total_stmt)
    total_candidates = total_result.scalar_one()

    # Проиндексировано — считаем эмбеддинги ТОЙ ЖЕ популяции (живые кандидаты с текстом
    # резюме), иначе indexed может превысить total (эмбеддинги создаются и по skills/
    # должности без resume_text) → на фронте >100% / «−N в очереди».
    indexed_stmt = (
        select(func.count(CandidateEmbedding.id))
        .join(Candidate, Candidate.id == CandidateEmbedding.candidate_id)
        .where(
            CandidateEmbedding.company_id == company_id,
            Candidate.deleted_at.is_(None),
            Candidate.resume_text.is_not(None),
            Candidate.resume_text != ""
        )
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


# === ДВУХФАЗНЫЙ ПОИСК (новая версия) ===

async def retrieve_base(
    session: AsyncSession,
    company_id: UUID,
    search_type: str,
    query: str,
    vacancy_id: Optional[UUID],
    override: Optional[dict] = None
) -> dict:
    """
    Фаза RETRIEVE (лёгкая): резолвит критерии и создаёт прогон (status='retrieved').
    Сам косинус по всей базе + AI-оценка — на фазе EVALUATE, когда известно N.

    Returns:
        dict: {run_id, total} — total = размер базы, доступной для поиска (эмбеддинги).
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
        # Ключ компании для LLM-парсинга запроса. Без ключа НЕ падаем жёстко:
        # parse_query_to_criteria деградирует на keyword-фолбэк, поэтому поиск по
        # СВОЕЙ базе остаётся доступен и без LLM-ключа компании (мгновенный косинус).
        try:
            api_key = await get_company_openrouter_key(session, company_id)
        except OpenRouterNotConfiguredError:
            api_key = ""
        criteria = await parse_query_to_criteria(query, api_key)

    # Размер базы, доступной для семантического поиска (проиндексированные эмбеддинги).
    total_stmt = select(func.count(CandidateEmbedding.id)).where(
        CandidateEmbedding.company_id == company_id
    )
    total_result = await session.execute(total_stmt)
    total_indexed = total_result.scalar_one()

    # Создаём прогон. РЕТРИВ (косинус по ВСЕЙ базе, HNSW, без кэпа 150) и AI-оценка
    # происходят на фазе EVALUATE, когда известно N: cosine top-N → оцениваем эти N.
    search_run = BaseSearchRun(
        company_id=company_id,
        search_type=search_type,
        query_text=query,
        vacancy_id=vacancy_id,
        status="retrieved",
        stage="retrieve",
        query_echo=query_echo,
        vacancy_title=vacancy_title,
        criteria=criteria,
        found=total_indexed,
        to_evaluate=0,
        evaluated=0,
        results=[]
    )
    session.add(search_run)
    await session.commit()
    await session.refresh(search_run)

    return {
        "run_id": search_run.id,
        "total": total_indexed,
    }


async def _load_candidates_for_rerank(
    session: AsyncSession,
    company_id: UUID,
    candidate_ids: list[UUID]
) -> list[dict]:
    """Загружает полные данные кандидатов для rerank (живой двухфазный путь
    retrieve_base → _run_base_evaluate → _rerank_candidates_with_progress)."""
    if not candidate_ids:
        return []

    has_pdn_subq = (
        select(Consent.id)
        .where(Consent.candidate_id == Candidate.id, Consent.status == "signed")
        .exists()
    )

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





async def _rerank_candidates_with_progress(
    candidates_data: list[dict],
    vacancy: Optional["Vacancy"],
    query_text: Optional[str],
    company_id: UUID,
    run_id: UUID,
    rerank_cap: Optional[int] = None
) -> list[dict]:
    """
    Ранжирует кандидатов с помощью LLM с обновлением прогресса.
    rerank_cap — сколько кандидатов реально оценить LLM (по умолчанию GLAFIRA_RERANK_CAP).
    Фаза EVALUATE передаёт ВЫБРАННОЕ ПОЛЬЗОВАТЕЛЕМ N — иначе оценка молча резалась бы до 24.
    """
    if not candidates_data:
        return candidates_data

    # Ограничиваем для rerank (N задаётся вызовом; фаза EVALUATE передаёт выбор пользователя)
    cap = rerank_cap if rerank_cap is not None else GLAFIRA_RERANK_CAP
    rerank_candidates = candidates_data[:cap]
    remaining_candidates = candidates_data[cap:]

    if not rerank_candidates:
        return candidates_data

    logger.info(f"Rerank для {len(rerank_candidates)} кандидатов")

    # Резолвим API-ключ компании один раз для всех LLM-вызовов
    async with AsyncSessionLocal() as key_session:
        api_key = await get_company_openrouter_key(key_session, company_id)

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
                    score_data = await asyncio.wait_for(
                        score_resume_dict(resume_dict, vacancy, company_id, api_key), timeout=180
                    )
                else:
                    # Скоринг против query как синтетической вакансии
                    synthetic_vacancy = _create_synthetic_vacancy_for_scoring(query_text or "")
                    score_data = await asyncio.wait_for(
                        score_resume_dict(resume_dict, synthetic_vacancy, company_id, api_key), timeout=180
                    )

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
        # Гарантия выхода из running: терминальный error БЕЗ results отдельной сессией
        # (если сами results не записались — иначе прогон навсегда зависнет в running).
        try:
            async with AsyncSessionLocal() as session2:
                run2 = await session2.get(BaseSearchRun, run_id)
                if run2 and run2.status == "running":
                    run2.status = "error"
                    run2.error = f"Сбой финализации: {type(e).__name__}"[:500]
                    run2.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    await session2.commit()
        except Exception as e2:
            logger.error(f"Не удалось записать терминальный error base search {run_id}: {e2}")


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


async def _run_base_evaluate(run_id: UUID, company_id: UUID, n: int):
    """
    Фоновая задача фазы EVALUATE: LLM-оценка топ-N кандидатов с внешним таймаутом
    """
    timeout_s = await _calculate_evaluate_timeout(n)

    async def _run_base_evaluate_inner():
        """Внутренняя функция с основной логикой оценки"""
        # Загружаем run короткой сессией: критерии + из чего строить косинус-запрос
        async with AsyncSessionLocal() as session:
            run = await session.get(BaseSearchRun, run_id)
            if not run:
                logger.error(f"BaseSearchRun {run_id} не найден")
                return

            criteria = run.criteria or {}
            vacancy_id = run.vacancy_id
            search_type = run.search_type
            query_text = run.query_text or ""

        # query_for_vector: промт → текст промта; вакансия → роль+навыки+город
        if search_type == "prompt":
            query_for_vector = query_text
        else:
            query_for_vector = f"{criteria.get('role', '')} {' '.join(criteria.get('skills', []))} {criteria.get('city', '')}".strip()

        # КОСИНУС ПО ВСЕЙ БАЗЕ (pgvector HNSW, без кэпа 150): берём top-N ближайших.
        # HNSW = приближённый поиск за ~log(N) — на сотнях тысяч резюме остаётся быстрым.
        distance_map = {}
        top_ids = []
        async with AsyncSessionLocal() as session:
            scored = await vector_retrieve_scored(session, company_id, query_for_vector, n)
            distance_map = {cid: dist for cid, dist in scored}
            top_ids = [cid for cid, _ in scored]

            # Fallback (нет эмбеддингов / вектор недоступен) — SQL top-N (заход A не ломаем).
            if not top_ids:
                sql_res = await search_base(
                    session, company_id,
                    role=criteria.get("role", ""),
                    skills=criteria.get("skills", []),
                    city=criteria.get("city", ""),
                    salary_from=criteria.get("salary_from"),
                    salary_to=criteria.get("salary_to"),
                )
                top_ids = [c["id"] for c in sql_res["results"][:n]]

        if not top_ids:
            logger.warning(f"BaseSearchRun {run_id}: косинус и SQL не дали кандидатов")
            await _finalize_base_search(run_id, "done", "done", results=[], found=0, evaluated=0)
            return

        # Короткой сессией: загружаем данные кандидатов и вакансию
        async with AsyncSessionLocal() as session:
            candidates_data = await _load_candidates_for_rerank(session, company_id, top_ids)

            vacancy = None
            if vacancy_id:
                vacancy_stmt = select(Vacancy).where(
                    Vacancy.id == vacancy_id,
                    Vacancy.company_id == company_id,
                    Vacancy.deleted_at.is_(None)
                )
                vacancy_result = await session.execute(vacancy_stmt)
                vacancy = vacancy_result.scalar_one_or_none()

        # Фактическое число к оценке (косинус мог вернуть < N) — точный прогресс-бар.
        if len(candidates_data) != n:
            await _update_base_search_progress(run_id, to_evaluate=len(candidates_data))

        # LLM-оценка БЕЗ открытой сессии. rerank_cap=len(candidates_data) — оцениваем ВСЕХ N.
        query_for_llm = query_for_vector if not vacancy else None
        ranked_candidates = await _rerank_candidates_with_progress(
            candidates_data, vacancy, query_for_llm, company_id, run_id,
            rerank_cap=len(candidates_data)
        )

        # Собираем AI-словари из ranked
        ai_results = []
        evaluated_count = 0
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

            # Процент совпадения и scored_by
            llm_score = candidate_data.get("llm_score")
            if llm_score is not None:
                match_percent = llm_score
                scored_by = "ai"
                evaluated_count += 1
            else:
                # LLM не дал балл → fallback на косинус-близость (если был в вектор-канале), иначе overlap
                if candidate.id in distance_map:
                    match_percent = cosine_to_percent(distance_map[candidate.id])
                elif skills:
                    match_percent = round(len(matched_skills) / len(skills) * 100)
                else:
                    match_percent = None
                scored_by = "cosine"

            ai_results.append({
                "id": str(candidate.id),
                "full_name": _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name),
                "age": _compute_age(candidate.birth_date),
                "last_position": candidate.last_position,
                "last_company": candidate.last_company,
                "last_period": candidate.last_period,
                "city": candidate.city,
                "ai_score": candidate.ai_score,
                "source": candidate.source,
                "salary_expectation": candidate.salary_expectation,
                "salary_from": candidate.salary_from,
                "salary_to": candidate.salary_to,
                "matched_skills": matched_skills,
                "all_skills": [skill.skill for skill in candidate_skills],
                "match_percent": match_percent,
                "has_pdn": candidate_data.get("has_pdn", False),
                "scored_by": scored_by
            })

        # Сортируем AI-оценённых по убыванию match_percent, затем добавляем хвост
        ai_scored = [r for r in ai_results if r["scored_by"] == "ai"]
        ai_scored.sort(key=lambda x: x["match_percent"] or 0, reverse=True)

        cosine_scored = [r for r in ai_results if r["scored_by"] == "cosine"]

        final_results = ai_scored + cosine_scored

        # Финализируем
        await _finalize_base_search(
            run_id, "done", "done",
            results=final_results,
            found=len(final_results),
            evaluated=evaluated_count
        )

    try:
        await asyncio.wait_for(_run_base_evaluate_inner(), timeout=timeout_s)
    except asyncio.TimeoutError:
        # Финализация по таймауту в отдельной короткой сессии
        try:
            await asyncio.wait_for(
                _finalize_base_search(
                    run_id,
                    status="error",
                    stage="evaluate",
                    error="Оценка прервана по таймауту (LLM не ответил вовремя). Попробуйте уменьшить количество кандидатов для оценки."
                ),
                timeout=15
            )
        except Exception as e:
            logger.error(f"Не удалось финализировать run {run_id} по таймауту: {e}")
    except Exception as e:
        # Финализация любых других ошибок в отдельной короткой сессии
        try:
            await asyncio.wait_for(
                _finalize_base_search(
                    run_id,
                    status="error",
                    stage="evaluate",
                    error=str(e)[:500]
                ),
                timeout=15
            )
        except Exception as finalize_error:
            logger.error(f"Не удалось финализировать run {run_id} после ошибки: {finalize_error}")
    finally:
        _active_tasks.discard(asyncio.current_task())