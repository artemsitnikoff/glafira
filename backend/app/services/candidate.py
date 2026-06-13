import asyncio
import logging
import math
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

def _parse_comma_separated_uuids(value: str | None) -> list[UUID]:
    """Parse comma-separated UUIDs, skip invalid ones"""
    if not value:
        return []

    uuids = []
    for item in value.split(','):
        item = item.strip()
        if item:
            try:
                uuids.append(UUID(item))
            except ValueError:
                # Skip invalid UUIDs
                continue
    return uuids

def _parse_comma_separated_strings(value: str | None) -> list[str]:
    """Parse comma-separated strings, skip empty ones"""
    if not value:
        return []

    return [item.strip() for item in value.split(',') if item.strip()]

from sqlalchemy import and_, asc, case, delete, desc, exists, false, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.errors import NotFoundError, ValidationError, ConflictError
from ..core.stages import STAGES
from ..models import (
    Application,
    Candidate,
    CandidateEmbedding,
    CandidateTag,
    CandidateExperience,
    CandidateSkill,
    CandidateEducation,
    Client,
    Consent,
    Event,
    SmartSearchRun,
    Tag,
    User,
    Vacancy,
    VacancyStage
)
from ..schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateDetail,
    CandidateGridItem,
    CandidateCardVacancy,
    ApplicationHistoryItem,
    TagOut,
    CandidateExperienceOut,
    CandidateEducationOut,
    DuplicateCheckResponse,
    DuplicateMatch,
    DuplicateVacancy
)
from ..schemas.base import Paginated
from ..services.audit import audit
from ..services.candidate_format import _compute_age, _compute_full_name
from ..services.base_search import reindex_candidate
from ..services.candidate_dedup import find_duplicate_candidates, _fio_match_level, _normalize_contact
from ..database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Удерживаем ссылки на фоновые задачи переиндексации — иначе GC может убить задачу
# (паттерн проекта, как _active_tasks в импорте/индексации).
_reindex_tasks: set = set()


def _schedule_reindex(company_id: UUID, candidate_id: UUID):
    """Best-effort фоновая переиндексация эмбеддинга кандидата (не ломает основную логику).
    Импорты top-level: цикл candidate↔base_search разорван через candidate_format."""
    async def _reindex_task():
        try:
            # Небольшая задержка: дать вызывающему запросу закоммитить транзакцию,
            # иначе фоновая (отдельная) сессия не увидит свежесозданного/обновлённого
            # кандидата (read-before-commit) и пропустит индексацию (best-effort фон).
            await asyncio.sleep(2)
            async with AsyncSessionLocal() as session:
                await reindex_candidate(session, company_id, candidate_id)
                await session.commit()
        except Exception as e:
            logger.error(f"Ошибка переиндексации кандидата {candidate_id}: {e}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # нет running loop (например, в тестах) — пропускаем
    task = loop.create_task(_reindex_task())
    _reindex_tasks.add(task)
    task.add_done_callback(_reindex_tasks.discard)

_STAGE_COLORS = {key: stage.color for key, stage in STAGES.items()}


import re as _re


def _exp_recency_key(period: str | None) -> tuple[int, int]:
    """Ключ свежести записи опыта: (текущая работа?, последний год периода). Больше = новее."""
    if not period:
        return (0, 0)
    p = period.lower()
    ongoing = 1 if any(k in p for k in ("наст", "н.в", "present", "current", "сейчас")) else 0
    years = _re.findall(r"(?:19|20)\d{2}", period)
    last_year = int(years[-1]) if years else 0
    return (ongoing, last_year)


def pick_latest_experience(experiences):
    """Самая свежая запись опыта (текущая работа, иначе с наибольшим годом окончания).

    Нужна потому, что денормализованные last_position/last_company/last_period могут
    рассинхрониться с experience (сид ставит их независимо, парсер — только если NULL),
    а порядок experience не гарантирован хронологически.
    """
    items = [e for e in (experiences or [])]
    if not items:
        return None
    return max(items, key=lambda e: _exp_recency_key(getattr(e, "period", None)))


_RU_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


def _parse_period_point(s: str, *, is_end: bool):
    """'Мар 2024' / '2024' / 'наст. время' → (year, month). None если не распознано."""
    s = s.strip().lower()
    if any(k in s for k in ("наст", "present", "сейчас", "н.в", "текущ")):
        t = date.today()
        return (t.year, t.month)
    m = _re.search(r"([а-яё]{3,})\.?\s*(\d{4})", s)
    if m and (mon := _RU_MONTHS.get(m.group(1)[:3])):
        return (int(m.group(2)), mon)
    y = _re.search(r"(19|20)\d{2}", s)
    if y:
        return (int(y.group(0)), 1)  # год без месяца → январь (чтобы «2020-2022» = 2 года)
    return None


def _period_to_months(period: str | None) -> int:
    """Длительность периода в месяцах (0 если не распарсилось)."""
    if not period:
        return 0
    parts = _re.split(r"\s*[—–-]\s*|\s+по\s+", period, maxsplit=1)
    if len(parts) < 2:
        return 0
    start = _parse_period_point(parts[0], is_end=False)
    end = _parse_period_point(parts[1], is_end=True)
    if not start or not end:
        return 0
    return max(0, (end[0] - start[0]) * 12 + (end[1] - start[1]))


def _plural_years(n: int) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return "год"
    if 2 <= n10 <= 4 and not (12 <= n100 <= 14):
        return "года"
    return "лет"


def format_duration(months: int) -> str | None:
    """Месяцы → '2 года 3 мес' (как в эталоне). None если 0/неизвестно."""
    if months <= 0:
        return None
    years, mons = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} {_plural_years(years)}")
    if mons:
        parts.append(f"{mons} мес")
    return " ".join(parts) if parts else None


def last_job_tenure(experiences) -> str | None:
    """Длительность на последнем (самом свежем) месте работы."""
    latest = pick_latest_experience(experiences)
    return format_duration(_period_to_months(getattr(latest, "period", None))) if latest else None


def total_experience(experiences) -> str | None:
    """Общий стаж = сумма длительностей всех записей опыта."""
    total = sum(_period_to_months(getattr(e, "period", None)) for e in (experiences or []))
    return format_duration(total)


def _normalize_salary(salary_from: int | None, salary_to: int | None) -> tuple[int | None, int | None]:
    """Нормализация зарплатной вилки по HR-правилу.

    Args:
        salary_from: нижняя граница зарплаты
        salary_to: верхняя граница зарплаты

    Returns:
        tuple (salary_from, salary_to)

    Raises:
        ValidationError: если salary_from > salary_to

    HR-правило:
    - оба None → (None, None)
    - одно задано, другое None → дублировать (from=to=заданное)
    - оба заданы и from > to → ValidationError
    """
    if salary_from is None and salary_to is None:
        return (None, None)

    if salary_from is None:
        return (salary_to, salary_to)

    if salary_to is None:
        return (salary_from, salary_from)

    if salary_from > salary_to:
        raise ValidationError("Зарплата «от» не может быть больше «до»")

    return (salary_from, salary_to)


async def compute_has_pdn(session: AsyncSession, candidate_id: UUID) -> bool:
    """True если у кандидата есть Consent со status='signed'."""
    result = await session.execute(
        select(exists().where(and_(
            Consent.candidate_id == candidate_id,
            Consent.status == "signed"
        )))
    )
    return result.scalar_one()


async def get_candidates_paginated(
    session: AsyncSession,
    company_id: UUID,
    page: int = 1,
    page_size: int = 24,
    search: str | None = None,
    city: str | None = None,
    exp: int | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    source: str | None = None,
    vacancy_id: str | None = None,
    stage: str | None = None,
    tags: str | None = None,
    added_period: str | None = None,
    sort: str | None = None,
    order: str = "desc",
) -> Paginated[CandidateGridItem]:
    """Get paginated candidates list with filters"""

    # has_pdn subquery
    has_pdn_subq = (
        select(Consent.id)
        .where(Consent.candidate_id == Candidate.id, Consent.status == "signed")
        .exists()
    )

    # Base query with filters
    base_filters = [
        Candidate.company_id == company_id,
        Candidate.deleted_at.is_(None)
    ]

    if search:
        like = f"%{search}%"
        base_filters.append(
            or_(
                Candidate.last_name.ilike(like),
                Candidate.first_name.ilike(like),
                Candidate.phone.ilike(like),
                Candidate.email.ilike(like)
            )
        )

    if city:
        base_filters.append(Candidate.city.ilike(f"%{city}%"))

    if source:
        sources = _parse_comma_separated_strings(source)
        if sources:
            base_filters.append(Candidate.source.in_(sources))

    if score_min is not None:
        base_filters.append(Candidate.ai_score >= score_min)

    if score_max is not None:
        base_filters.append(Candidate.ai_score <= score_max)

    if vacancy_id:
        vacancy_uuids = _parse_comma_separated_uuids(vacancy_id)
        if vacancy_uuids:
            base_filters.append(
                exists().where(
                    and_(
                        Application.candidate_id == Candidate.id,
                        Application.vacancy_id.in_(vacancy_uuids)
                    )
                )
            )
        else:
            # vacancy_id передан, но все значения — мусор (невалидные UUID). Fail-closed:
            # фильтр задан → ничего не матчим (а не возвращаем всю базу).
            base_filters.append(false())

    if stage:
        stages = _parse_comma_separated_strings(stage)
        if stages:
            pool_selected = 'pool' in stages
            real_stages = [s for s in stages if s != 'pool']

            stage_conditions = []

            # Real stages condition
            if real_stages:
                stage_conditions.append(
                    exists().where(
                        and_(
                            Application.candidate_id == Candidate.id,
                            Application.stage.in_(real_stages)
                        )
                    )
                )

            # Pool condition - candidates without any applications
            if pool_selected:
                stage_conditions.append(
                    ~exists().where(Application.candidate_id == Candidate.id)
                )

            # Combine conditions with OR if both present, otherwise use the single one
            if len(stage_conditions) == 1:
                base_filters.append(stage_conditions[0])
            elif len(stage_conditions) > 1:
                base_filters.append(or_(*stage_conditions))

    if tags:
        tag_uuids = _parse_comma_separated_uuids(tags)
        if tag_uuids:
            base_filters.append(
                exists().where(
                    and_(
                        CandidateTag.candidate_id == Candidate.id,
                        CandidateTag.tag_id.in_(tag_uuids)
                    )
                )
            )

    if added_period:
        now = datetime.now(timezone.utc)
        if added_period == "7d":
            base_filters.append(Candidate.created_at >= now - timedelta(days=7))
        elif added_period == "30d":
            base_filters.append(Candidate.created_at >= now - timedelta(days=30))
        elif added_period == "3m":
            base_filters.append(Candidate.created_at >= now - timedelta(days=90))

    # Count total
    count_stmt = select(func.count(Candidate.id)).where(and_(*base_filters))
    total = (await session.execute(count_stmt)).scalar_one()

    # Simplified query - we'll fetch last application separately after
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
            Candidate.ai_score,
            Candidate.is_duplicate,
            has_pdn_subq.label("has_pdn")
        )
        .where(and_(*base_filters))
    )

    # Apply sorting
    sort_column = Candidate.created_at
    if sort == "name":
        sort_column = Candidate.last_name
    elif sort == "score":
        sort_column = Candidate.ai_score
    elif sort == "activity":
        sort_column = Candidate.updated_at

    stmt = stmt.order_by(asc(sort_column) if order == "asc" else desc(sort_column))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = (await session.execute(stmt)).all()

    # Get candidate IDs from current page
    candidate_ids = [row.id for row in rows]

    # Batch-запрос всех applications этих кандидатов с JOIN vacancy
    apps_stmt = (
        select(
            Application.id,
            Application.candidate_id,
            Application.vacancy_id,
            Application.stage,
            Application.created_at,
            Vacancy.name.label('vacancy_name')
        )
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(Application.candidate_id.in_(candidate_ids))
        .order_by(Application.candidate_id, Application.created_at.desc())
    )
    apps_rows = (await session.execute(apps_stmt)).all()

    # Сгруппируй по candidate_id
    from collections import defaultdict
    apps_by_candidate = defaultdict(list)
    for app_row in apps_rows:
        apps_by_candidate[app_row.candidate_id].append(app_row)

    # Batch-запрос опыта страницы — мета «последнее место»/стаж выводится из реального опыта,
    # а не из устаревших last_* (как и в детальной карточке).
    exp_stmt = select(
        CandidateExperience.candidate_id,
        CandidateExperience.position,
        CandidateExperience.company,
        CandidateExperience.period,
    ).where(CandidateExperience.candidate_id.in_(candidate_ids))
    exp_by_candidate = defaultdict(list)
    for e in (await session.execute(exp_stmt)).all():
        exp_by_candidate[e.candidate_id].append(e)

    # Build items
    items = []
    for row in rows:
        full_name = _compute_full_name(row.last_name, row.first_name, row.middle_name)
        age = _compute_age(row.birth_date)

        # Последнее место — из самой свежей записи опыта (fallback на сохранённые last_*).
        latest_exp = pick_latest_experience(exp_by_candidate[row.id])
        row_last_position = (latest_exp.position if latest_exp else None) or row.last_position
        row_last_company = (latest_exp.company if latest_exp else None) or row.last_company
        row_last_period = (latest_exp.period if latest_exp else None) or row.last_period
        row_last_tenure = format_duration(_period_to_months(row_last_period))

        # Получаем applications этого кандидата
        candidate_apps = apps_by_candidate[row.id]

        # last_vacancy - первый (самый свежий по created_at)
        last_vacancy = None
        other_vacancies_count = 0

        if candidate_apps:
            last_app = candidate_apps[0]  # первый в отсортированном списке
            stage_color = STAGES.get(last_app.stage, STAGES['added']).color

            last_vacancy = CandidateCardVacancy(
                application_id=last_app.id,
                vacancy_id=last_app.vacancy_id,
                vacancy_name=last_app.vacancy_name,
                stage=last_app.stage,
                stage_color=stage_color,
                is_last=True
            )

            other_vacancies_count = max(0, len(candidate_apps) - 1)

        items.append(CandidateGridItem(
            id=row.id,
            display_number=row.display_number,
            full_name=full_name,
            age=age,
            last_position=row_last_position,
            last_company=row_last_company,
            last_period=row_last_period,
            last_tenure=row_last_tenure,
            ai_score=row.ai_score,
            avatar_url=None,  # No avatar_url field in Candidate model
            is_duplicate=row.is_duplicate,
            has_pdn=bool(row.has_pdn),
            last_vacancy=last_vacancy,
            other_vacancies_count=other_vacancies_count
        ))

    pages = math.ceil(total / page_size) if total > 0 else 0

    return Paginated[CandidateGridItem](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


async def get_candidate(session: AsyncSession, candidate_id: UUID, company_id: UUID) -> Candidate:
    """Get candidate by ID"""
    result = await session.execute(
        select(Candidate)
        .options(
            selectinload(Candidate.tags).selectinload(CandidateTag.tag),
            selectinload(Candidate.experience),
            selectinload(Candidate.education),
            selectinload(Candidate.skills)
        )
        .where(Candidate.id == candidate_id, Candidate.company_id == company_id, Candidate.deleted_at.is_(None))
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise NotFoundError("Кандидат")
    return candidate


async def get_candidate_detail(session: AsyncSession, candidate_id: UUID, company_id: UUID) -> CandidateDetail:
    """Get candidate with all details"""
    candidate = await get_candidate(session, candidate_id, company_id)

    # Check has_pdn
    has_pdn = await compute_has_pdn(session, candidate_id)

    # Build tags
    tags = [TagOut.model_validate(ct.tag) for ct in candidate.tags]

    # Build experience
    experience = [CandidateExperienceOut.model_validate(exp) for exp in candidate.experience]

    # Build education
    education = [CandidateEducationOut.model_validate(e) for e in candidate.education]

    # Build skills
    skills = [skill.skill for skill in candidate.skills]

    # Build full name
    full_name = _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name)
    age = _compute_age(candidate.birth_date)

    # «Последнее место работы» для меты — из самой свежей записи опыта (а не из устаревших
    # денормализованных полей, которые могли рассинхрониться при сиде/парсинге).
    latest_exp = pick_latest_experience(candidate.experience)
    last_position = (latest_exp.position if latest_exp else None) or candidate.last_position
    last_company = (latest_exp.company if latest_exp else None) or candidate.last_company
    last_period = (latest_exp.period if latest_exp else None) or candidate.last_period
    # Вычисленные длительности (как в эталоне): стаж на последнем месте + общий стаж по резюме.
    last_tenure = last_job_tenure(candidate.experience)
    total_exp = total_experience(candidate.experience)

    # «Найден Умным подбором»: hh-resume-id кандидата (из extra.hh_resume_id для
    # smart-invite или external_id для импорта откликов) есть среди scored_candidates
    # любого смарт-прогона компании. Надёжно независимо от способа создания кандидата.
    from_smart_search = False
    resume_hh_id = (candidate.extra or {}).get("hh_resume_id") or candidate.external_id
    if resume_hh_id:
        ss = await session.execute(
            select(SmartSearchRun.id).where(
                SmartSearchRun.company_id == company_id,
                SmartSearchRun.scored_candidates.contains([{"hh_resume_id": str(resume_hh_id)}]),
            ).limit(1)
        )
        from_smart_search = ss.first() is not None

    return CandidateDetail(
        id=candidate.id,
        display_number=candidate.display_number,
        last_name=candidate.last_name,
        first_name=candidate.first_name,
        middle_name=candidate.middle_name,
        full_name=full_name,
        age=age,
        birth_date=candidate.birth_date,
        gender=candidate.gender,
        city=candidate.city,
        region=candidate.region,
        phone=candidate.phone,
        email=candidate.email,
        messengers=candidate.messengers or [],
        salary_expectation=candidate.salary_expectation,
        salary_from=candidate.salary_from,
        salary_to=candidate.salary_to,
        currency=candidate.currency,
        last_position=last_position,
        last_company=last_company,
        last_period=last_period,
        last_tenure=last_tenure,
        total_experience=total_exp,
        source=candidate.source,
        source_url=candidate.source_url,
        preferred_channel=candidate.preferred_channel,
        resume_text=candidate.resume_text,
        resume_summary=candidate.resume_summary,
        ai_score=candidate.ai_score,
        has_pdn=has_pdn,
        is_duplicate=candidate.is_duplicate,
        duplicate_of=candidate.duplicate_of,
        is_anonymized=candidate.is_anonymized,
        tags=tags,
        experience=experience,
        education=education,
        skills=skills,
        extra=candidate.extra,
        from_smart_search=from_smart_search,
        created_at=candidate.created_at
    )


async def _build_duplicate_match(
    session: AsyncSession,
    company_id: UUID,
    candidate: Candidate,
    input_phone: str | None,
    input_last_name: str | None,
    input_first_name: str | None,
    input_middle_name: str | None,
) -> DuplicateMatch:
    """Собирает DuplicateMatch для найденного дубля.

    Единый источник логики для check_candidate_duplicates (выдаёт Pydantic) и
    create_candidate (сериализует в dict для details 409) — чтобы не было двух
    расходящихся реализаций.
    - matched_by: 'phone', если нормализованный входной телефон совпал с телефоном
      кандидата; иначе совпадение по email.
    - match_level: по входному ФИО (см. _fio_match_level).
    - vacancies: до 3 участий, СТРОГО company-scoped.
    """
    matched_by = 'email'
    if input_phone:
        normalized_phone = _normalize_contact(input_phone)
        candidate_phone = _normalize_contact(candidate.phone or "")
        if normalized_phone and candidate_phone and normalized_phone == candidate_phone:
            matched_by = 'phone'

    match_level = _fio_match_level(input_last_name, input_first_name, input_middle_name, candidate)

    vacancies_result = await session.execute(
        select(Vacancy.name.label('vacancy_name'), Application.stage)
        .join(Vacancy, Application.vacancy_id == Vacancy.id)
        .where(
            Application.candidate_id == candidate.id,
            Application.company_id == company_id,
            Vacancy.deleted_at.is_(None)
        )
        .order_by(Application.created_at.desc())
        .limit(3)
    )
    vacancies = [
        DuplicateVacancy(
            vacancy_name=row.vacancy_name,
            stage_label=STAGES[row.stage].label if row.stage in STAGES else row.stage,
        )
        for row in vacancies_result.fetchall()
    ]

    return DuplicateMatch(
        id=candidate.id,
        full_name=candidate.full_name,
        phone=candidate.phone,
        email=candidate.email,
        created_at=candidate.created_at,
        match_level=match_level,
        matched_by=matched_by,
        vacancies=vacancies,
    )


async def check_candidate_duplicates(
    session: AsyncSession,
    company_id: UUID,
    phone: str | None = None,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    middle_name: str | None = None
) -> DuplicateCheckResponse:
    """Проверка дубликатов кандидата по телефону и/или email.

    Args:
        session: Сессия БД
        company_id: ID компании (строгая изоляция)
        phone: Телефон для проверки
        email: Email для проверки
        first_name: Имя (для уточнения match_level)
        last_name: Фамилия (для уточнения match_level)
        middle_name: Отчество (для уточнения match_level)

    Returns:
        Результат проверки с найденными дубликатами (до 3)
    """
    candidates = await find_duplicate_candidates(session, company_id, phone, email)

    if not candidates:
        return DuplicateCheckResponse(found=False, match_count=0, matches=[])

    matches = [
        await _build_duplicate_match(
            session, company_id, candidate, phone, last_name, first_name, middle_name
        )
        for candidate in candidates[:3]
    ]

    return DuplicateCheckResponse(found=True, match_count=len(candidates), matches=matches)


async def create_candidate(
    session: AsyncSession,
    candidate_data: CandidateCreate,
    company_id: UUID,
    actor_user_id: UUID
) -> CandidateDetail:
    """Create new candidate"""
    # Validate required fields
    if not candidate_data.last_name or not candidate_data.first_name or not candidate_data.source:
        raise ValidationError("Обязательные поля: last_name, first_name, source")

    # Проверка дубликатов (если не принудительное создание)
    duplicate_ids = []
    if not candidate_data.force_duplicate:
        duplicates = await find_duplicate_candidates(
            session, company_id, candidate_data.phone, candidate_data.email
        )
        if duplicates:
            # Детали для 409 — через тот же билдер, что и check (mode="json" сериализует
            # UUID→str и datetime→ISO, чтобы тело ошибки прошло в JSONResponse).
            matches_details = [
                (await _build_duplicate_match(
                    session, company_id, candidate, candidate_data.phone,
                    candidate_data.last_name, candidate_data.first_name, candidate_data.middle_name
                )).model_dump(mode="json")
                for candidate in duplicates[:3]
            ]

            raise ConflictError(
                message="Кандидат с такими контактными данными уже существует",
                details={"match_count": len(duplicates), "matches": matches_details},
                code="DUPLICATE_CANDIDATE"
            )

    # Если force_duplicate=True и есть дубли - запомним их ID для audit
    elif candidate_data.force_duplicate:
        duplicates = await find_duplicate_candidates(
            session, company_id, candidate_data.phone, candidate_data.email
        )
        duplicate_ids = [str(dup.id) for dup in duplicates[:3]]

    # Create candidate
    full_name = _compute_full_name(candidate_data.last_name, candidate_data.first_name, candidate_data.middle_name)

    # Prepare extra data
    extra = {}
    if candidate_data.comment:
        extra["comment"] = candidate_data.comment
    if candidate_data.add_type and candidate_data.add_type != "manual":
        extra["add_type"] = candidate_data.add_type

    # Prepare messengers data
    messengers_data = []
    if candidate_data.messengers:
        messengers_data = [msg.model_dump() for msg in candidate_data.messengers]

    # Нормализация зарплатной вилки с фолбэком на старое поле
    salary_from_input = candidate_data.salary_from
    salary_to_input = candidate_data.salary_to

    # Фолбэк: если новые поля не заданы, используем старое salary_expectation
    if salary_from_input is None and salary_to_input is None and candidate_data.salary_expectation is not None:
        salary_from_input = candidate_data.salary_expectation
        salary_to_input = candidate_data.salary_expectation

    salary_from, salary_to = _normalize_salary(salary_from_input, salary_to_input)

    candidate = Candidate(
        company_id=company_id,
        last_name=candidate_data.last_name,
        first_name=candidate_data.first_name,
        middle_name=candidate_data.middle_name,
        source=candidate_data.source,
        phone=candidate_data.phone,
        email=candidate_data.email,
        gender=candidate_data.gender,
        birth_date=candidate_data.birth_date,
        city=candidate_data.city,
        region=candidate_data.region,
        salary_expectation=salary_from,  # синхронизация: salary_expectation = salary_from
        salary_from=salary_from,
        salary_to=salary_to,
        currency=candidate_data.currency,
        last_position=candidate_data.last_position,
        last_company=candidate_data.last_company,
        last_period=candidate_data.last_period,
        messengers=messengers_data,
        source_url=(candidate_data.source_url or None),
        extra=extra
    )

    session.add(candidate)
    await session.flush()

    # Create related records (experience, skills, education)
    # Опыт работы - пропускаем записи с пустым position
    if candidate_data.experience:
        created_exp = []
        for idx, exp_data in enumerate(candidate_data.experience):
            if exp_data.position:  # position required, проверка в схеме
                experience = CandidateExperience(
                    candidate_id=candidate.id,
                    company_id=company_id,
                    position=exp_data.position,
                    company=exp_data.company,
                    period=exp_data.period,
                    description=exp_data.description,
                    order_index=idx
                )
                session.add(experience)
                created_exp.append(experience)

        # Синк last_* полей с последней записью опыта, если они не были заданы
        if created_exp and (not candidate_data.last_position or not candidate_data.last_company or not candidate_data.last_period):
            latest = pick_latest_experience(created_exp)
            if latest:
                if not candidate.last_position:
                    candidate.last_position = latest.position
                if not candidate.last_company:
                    candidate.last_company = latest.company
                if not candidate.last_period:
                    candidate.last_period = latest.period

    # Навыки
    if candidate_data.skills:
        for idx, skill in enumerate(candidate_data.skills):
            if skill:  # Пропустить пустые
                candidate_skill = CandidateSkill(
                    candidate_id=candidate.id,
                    company_id=company_id,
                    skill=skill,
                    order_index=idx
                )
                session.add(candidate_skill)

    # Образование
    if candidate_data.education:
        for idx, edu_data in enumerate(candidate_data.education):
            # Пропускаем полностью пустые записи (консистентно с фронт-фильтром и skip опыта)
            if not (edu_data.institution or edu_data.specialty or edu_data.years):
                continue
            education = CandidateEducation(
                candidate_id=candidate.id,
                company_id=company_id,
                institution=edu_data.institution,
                specialty=edu_data.specialty,
                years=edu_data.years,
                order_index=idx
            )
            session.add(education)

    # If vacancy_id provided, create application
    if candidate_data.vacancy_id:
        from ..models import Application, Vacancy  # Avoid circular import

        # Ensure vacancy exists and belongs to company
        vacancy_result = await session.execute(
            select(Vacancy).where(Vacancy.id == candidate_data.vacancy_id, Vacancy.company_id == company_id, Vacancy.deleted_at.is_(None))
        )
        if not vacancy_result.scalar_one_or_none():
            raise NotFoundError("Вакансия")

        now = datetime.now(timezone.utc)
        application = Application(
            company_id=company_id,
            candidate_id=candidate.id,
            vacancy_id=candidate_data.vacancy_id,
            stage="added",
            created_at=now,
            # «Дата отбора» = дата привязки кандидата к вакансии (ручное создание).
            selected_at=now,
        )
        session.add(application)

    # Audit
    audit_after = {
        "full_name": full_name,
        "source": candidate_data.source,
        "vacancy_id": str(candidate_data.vacancy_id) if candidate_data.vacancy_id else None
    }
    # Если создан как дубль - указываем ID существующих кандидатов
    if duplicate_ids:
        audit_after["duplicate_of"] = duplicate_ids

    await audit(
        session,
        action="create",
        entity_type="candidate",
        entity_id=candidate.id,
        after=audit_after,
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()

    # Планируем переиндексацию эмбеддингов
    _schedule_reindex(company_id, candidate.id)

    return await get_candidate_detail(session, candidate.id, company_id)


async def update_candidate(
    session: AsyncSession,
    candidate_id: UUID,
    candidate_data: CandidateUpdate,
    company_id: UUID,
    actor_user_id: UUID
) -> CandidateDetail:
    """Update candidate"""
    candidate = await get_candidate(session, candidate_id, company_id)

    # Save old values for audit
    before = {
        "phone": candidate.phone,
        "email": candidate.email,
        "city": candidate.city,
        "source": candidate.source,
        "source_url": candidate.source_url,
        "messengers": candidate.messengers,
        "salary_expectation": candidate.salary_expectation,
        "salary_from": candidate.salary_from,
        "salary_to": candidate.salary_to,
    }

    # Update fields
    if candidate_data.last_name is not None:
        candidate.last_name = candidate_data.last_name
    if candidate_data.first_name is not None:
        candidate.first_name = candidate_data.first_name
    if candidate_data.middle_name is not None:
        candidate.middle_name = candidate_data.middle_name
    if candidate_data.phone is not None:
        candidate.phone = candidate_data.phone
    if candidate_data.email is not None:
        candidate.email = candidate_data.email
    if candidate_data.gender is not None:
        candidate.gender = candidate_data.gender
    if candidate_data.birth_date is not None:
        candidate.birth_date = candidate_data.birth_date
    if candidate_data.city is not None:
        candidate.city = candidate_data.city
    if candidate_data.region is not None:
        candidate.region = candidate_data.region
    # Обновление зарплатных полей - партиальное через model_fields_set
    salary_fields_updated = False
    current_salary_from = candidate.salary_from
    current_salary_to = candidate.salary_to

    if candidate_data.model_fields_set:
        if 'salary_from' in candidate_data.model_fields_set:
            current_salary_from = candidate_data.salary_from
            salary_fields_updated = True
        if 'salary_to' in candidate_data.model_fields_set:
            current_salary_to = candidate_data.salary_to
            salary_fields_updated = True
        # Поддержка старого поля для совместимости
        if 'salary_expectation' in candidate_data.model_fields_set and not salary_fields_updated:
            current_salary_from = candidate_data.salary_expectation
            current_salary_to = candidate_data.salary_expectation
            salary_fields_updated = True

    if salary_fields_updated:
        salary_from, salary_to = _normalize_salary(current_salary_from, current_salary_to)
        candidate.salary_from = salary_from
        candidate.salary_to = salary_to
        candidate.salary_expectation = salary_from  # синхронизация

    if candidate_data.currency is not None:
        candidate.currency = candidate_data.currency
    if candidate_data.source is not None:
        candidate.source = candidate_data.source
    if candidate_data.source_url is not None:
        # Пустая строка → очистка (NULL), иначе сохраняем ссылку
        candidate.source_url = candidate_data.source_url.strip() or None
    if candidate_data.messengers is not None:
        # None — не трогаем (сохраняем существующие); [] — очистить; список — заменить.
        # Формат как в create_candidate: [{type, url}].
        candidate.messengers = [m.model_dump() for m in candidate_data.messengers]
    if candidate_data.last_position is not None:
        candidate.last_position = candidate_data.last_position
    if candidate_data.last_company is not None:
        candidate.last_company = candidate_data.last_company
    if candidate_data.last_period is not None:
        candidate.last_period = candidate_data.last_period
    if candidate_data.preferred_channel is not None:
        candidate.preferred_channel = candidate_data.preferred_channel
    if candidate_data.resume_text is not None:
        candidate.resume_text = candidate_data.resume_text
    if candidate_data.resume_summary is not None:
        candidate.resume_summary = candidate_data.resume_summary

    # full_name is computed from name components - no need to update a field

    candidate.updated_at = datetime.now(timezone.utc)

    # Audit
    await audit(
        session,
        action="update",
        entity_type="candidate",
        entity_id=candidate.id,
        before=before,
        after={
            "phone": candidate.phone,
            "email": candidate.email,
            "city": candidate.city,
            "source": candidate.source,
            "source_url": candidate.source_url,
            "messengers": candidate.messengers,
            "salary_expectation": candidate.salary_expectation,
            "salary_from": candidate.salary_from,
            "salary_to": candidate.salary_to,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()

    # Планируем переиндексацию эмбеддингов
    _schedule_reindex(company_id, candidate_id)

    return await get_candidate_detail(session, candidate_id, company_id)


async def delete_candidate(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> None:
    """Soft delete candidate"""
    candidate = await get_candidate(session, candidate_id, company_id)

    candidate.deleted_at = datetime.now(timezone.utc)

    # Отвязка из воронки: удаляем заявки кандидата (bulk DELETE → срабатывают БД-каскады
    # FK ondelete=CASCADE: stage_history/comments/evaluations/messages; pulse-employee → SET NULL).
    # Сам кандидат остаётся soft-deleted (deleted_at) для аудита/152-ФЗ.
    await session.execute(
        delete(Application).where(
            Application.candidate_id == candidate_id,
            Application.company_id == company_id,
        )
    )

    # Физически удаляем эмбеддинг, чтобы удалённый кандидат не занимал слот HNSW top-k
    await session.execute(
        delete(CandidateEmbedding).where(
            CandidateEmbedding.candidate_id == candidate_id,
            CandidateEmbedding.company_id == company_id,
        )
    )

    # Audit
    await audit(
        session,
        action="delete",
        entity_type="candidate",
        entity_id=candidate.id,
        before={"deleted_at": None},
        after={"deleted_at": candidate.deleted_at.isoformat()},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()


async def get_candidate_applications(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID
) -> list[ApplicationHistoryItem]:
    """Get candidate's application history"""
    await get_candidate(session, candidate_id, company_id)  # Ensure candidate exists

    stmt = (
        select(
            Application.id.label("application_id"),
            Application.vacancy_id,
            Application.stage,
            Application.ai_score,
            Application.selected_at,
            Application.stage_changed_at,
            Application.reject_reason,
            Vacancy.name.label("vacancy_name"),
            Vacancy.status.label("vacancy_status"),
            User.full_name.label("recruiter_name"),
            Client.name.label("client_name")
        )
        .select_from(Application)
        .join(Vacancy, Application.vacancy_id == Vacancy.id)
        .outerjoin(User, Vacancy.responsible_user_id == User.id)
        .outerjoin(Client, Vacancy.client_id == Client.id)
        .where(
            Application.candidate_id == candidate_id,
            Application.company_id == company_id,
            Vacancy.company_id == company_id
        )
        .order_by(desc(Application.created_at))
    )

    rows = (await session.execute(stmt)).all()

    return [
        ApplicationHistoryItem(
            application_id=row.application_id,
            vacancy_id=row.vacancy_id,
            vacancy_name=row.vacancy_name,
            vacancy_status=row.vacancy_status,
            stage=row.stage,
            stage_color=_STAGE_COLORS.get(row.stage, "#9AA3AE"),
            client_name=row.client_name,
            recruiter_name=row.recruiter_name,
            ai_score=row.ai_score,
            selected_at=row.selected_at,
            stage_changed_at=row.stage_changed_at,
            reject_reason=row.reject_reason
        )
        for row in rows
    ]


async def add_candidate_tag(
    session: AsyncSession,
    candidate_id: UUID,
    tag_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> None:
    """Add tag to candidate"""
    candidate = await get_candidate(session, candidate_id, company_id)

    # Check if tag exists and belongs to company
    tag_result = await session.execute(
        select(Tag).where(Tag.id == tag_id, Tag.company_id == company_id)
    )
    tag = tag_result.scalar_one_or_none()
    if not tag:
        raise NotFoundError("Тег")

    # Check if relation already exists
    existing = await session.execute(
        select(CandidateTag).where(
            CandidateTag.candidate_id == candidate_id,
            CandidateTag.tag_id == tag_id
        )
    )
    if existing.scalar_one_or_none():
        return  # Already exists, no-op

    # Add relation
    candidate_tag = CandidateTag(
        candidate_id=candidate_id,
        tag_id=tag_id
    )
    session.add(candidate_tag)

    # Audit
    await audit(
        session,
        action="add_tag",
        entity_type="candidate",
        entity_id=candidate_id,
        after={"tag_id": str(tag_id), "tag_name": tag.name},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()


async def remove_candidate_tag(
    session: AsyncSession,
    candidate_id: UUID,
    tag_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> None:
    """Remove tag from candidate"""
    candidate = await get_candidate(session, candidate_id, company_id)

    # Find and delete relation
    result = await session.execute(
        select(CandidateTag).where(
            CandidateTag.candidate_id == candidate_id,
            CandidateTag.tag_id == tag_id
        )
    )
    candidate_tag = result.scalar_one_or_none()
    if not candidate_tag:
        raise NotFoundError("Связь с тегом")

    await session.delete(candidate_tag)

    # Audit
    await audit(
        session,
        action="remove_tag",
        entity_type="candidate",
        entity_id=candidate_id,
        before={"tag_id": str(tag_id)},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()


async def assign_candidate_to_vacancy(
    session: AsyncSession,
    candidate_id: UUID,
    vacancy_id: UUID,
    stage: str,
    company_id: UUID,
    actor_user_id: UUID
):
    """Assign existing candidate to vacancy"""
    from ..schemas.application import ApplicationRow  # Import here to avoid circular dependency

    # Ensure candidate exists and belongs to company
    candidate = await get_candidate(session, candidate_id, company_id)

    # Ensure vacancy exists and belongs to company
    vacancy_result = await session.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id, Vacancy.company_id == company_id, Vacancy.deleted_at.is_(None))
    )
    vacancy = vacancy_result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия")

    # Резолвим целевой этап в РЕАЛЬНЫЙ этап воронки ИМЕННО ЭТОЙ вакансии. Если запрошенного
    # этапа в её воронке нет (напр. 'added' отсутствует в шаблоне «массовый») — берём первый
    # непустой этап по порядку, чтобы кандидат не попал в «призрачный» этап вне доски.
    vac_stages = (await session.execute(
        select(VacancyStage)
        .where(VacancyStage.vacancy_id == vacancy_id)
        .order_by(VacancyStage.order_index)
    )).scalars().all()
    if vac_stages:
        valid_keys = {vs.stage_key for vs in vac_stages}
        if stage not in valid_keys:
            non_terminal = [vs for vs in vac_stages if vs.stage_key not in ("hired", "rejected")]
            if not non_terminal:
                raise ValidationError("В воронке вакансии нет доступных этапов для назначения")
            stage = non_terminal[0].stage_key
    elif stage not in STAGES:
        # У вакансии нет кастомных этапов в БД — принимаем только системный этап
        raise ValidationError(f"Неверная стадия: {stage}")

    # Check if application already exists
    existing_result = await session.execute(
        select(Application).where(
            Application.candidate_id == candidate_id,
            Application.vacancy_id == vacancy_id,
            Application.company_id == company_id
        )
    )
    existing_app = existing_result.scalar_one_or_none()
    if existing_app:
        stage_def = STAGES.get(existing_app.stage)
        stage_name = stage_def.label if stage_def else existing_app.stage
        raise ConflictError(f"Кандидат уже назначен на эту вакансию в стадии '{stage_name}'")

    # Create application
    now = datetime.now(timezone.utc)
    application = Application(
        company_id=company_id,
        candidate_id=candidate_id,
        vacancy_id=vacancy_id,
        stage=stage,
        selected_at=now,
        created_at=now
    )
    session.add(application)
    await session.flush()

    # Audit
    await audit(
        session,
        action="assign",
        entity_type="application",
        entity_id=application.id,
        after={
            "candidate_id": str(candidate_id),
            "vacancy_id": str(vacancy_id),
            "stage": stage
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    # Событие для ленты «Все действия» (Event != audit — лента читает таблицу events).
    # type='new' — уже в CHECK Event.type и рендерится на фронте (миграция не нужна).
    session.add(
        Event(
            company_id=company_id,
            type="new",
            actor_type="human",
            actor_user_id=actor_user_id,
            text=f"Кандидат {candidate.full_name} назначен на вакансию «{vacancy.name}»",
            candidate_id=candidate_id,
            vacancy_id=vacancy_id,
        )
    )

    # Return ApplicationRow format
    full_name = _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name)
    age = _compute_age(candidate.birth_date)

    return ApplicationRow(
        id=application.id,
        candidate_id=candidate_id,
        display_number=candidate.display_number,
        full_name=full_name,
        avatar_url=None,  # No avatar field in candidate model
        age=age,
        last_position=candidate.last_position,
        ai_score=candidate.ai_score,
        has_pdn=await compute_has_pdn(session, candidate_id),
        phone=candidate.phone,
        messengers=candidate.messengers or [],
        salary_expectation=candidate.salary_expectation,
        salary_from=candidate.salary_from,
        salary_to=candidate.salary_to,
        currency=candidate.currency,
        city=candidate.city,
        stage=stage,
        # Этап может быть КАСТОМНЫМ (резолв выше берёт первый этап воронки) — голый
        # STAGES[stage] упал бы KeyError→500. Безопасный резолв как в строке 786.
        stage_color=_STAGE_COLORS.get(stage, "#9AA3AE"),
        selected_at=application.selected_at
    )


async def list_company_tags(
    session: AsyncSession,
    company_id: UUID
) -> list[Tag]:
    """Get all tags for a company"""
    query = (
        select(Tag)
        .filter(Tag.company_id == company_id)
        .order_by(Tag.name)
    )
    result = await session.execute(query)
    return result.scalars().all()