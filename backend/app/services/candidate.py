import math
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import and_, asc, case, desc, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.errors import NotFoundError, ValidationError, ConflictError
from ..core.stages import STAGES
from ..models import (
    Application,
    Candidate,
    CandidateTag,
    CandidateExperience,
    CandidateSkill,
    Client,
    Consent,
    Tag,
    User,
    Vacancy
)
from ..schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateDetail,
    CandidateGridItem,
    CandidateCardVacancy,
    ApplicationHistoryItem,
    TagOut,
    CandidateExperienceOut
)
from ..schemas.base import Paginated
from ..services.audit import audit

_STAGE_COLORS = {key: stage.color for key, stage in STAGES.items()}


def _compute_age(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _compute_full_name(last_name: str, first_name: str, middle_name: str | None) -> str:
    return " ".join(part for part in (last_name, first_name, middle_name) if part)


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
    vacancy_id: UUID | None = None,
    stage: str | None = None,
    tags: list[UUID] | None = None,
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
        base_filters.append(Candidate.source == source)

    if score_min is not None:
        base_filters.append(Candidate.ai_score >= score_min)

    if score_max is not None:
        base_filters.append(Candidate.ai_score <= score_max)

    if vacancy_id:
        base_filters.append(
            exists().where(
                and_(
                    Application.candidate_id == Candidate.id,
                    Application.vacancy_id == vacancy_id
                )
            )
        )

    if stage:
        base_filters.append(
            exists().where(
                and_(
                    Application.candidate_id == Candidate.id,
                    Application.stage == stage
                )
            )
        )

    if tags:
        base_filters.append(
            exists().where(
                and_(
                    CandidateTag.candidate_id == Candidate.id,
                    CandidateTag.tag_id.in_(tags)
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

    # Build items
    items = []
    for row in rows:
        full_name = _compute_full_name(row.last_name, row.first_name, row.middle_name)
        age = _compute_age(row.birth_date)

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
            last_position=row.last_position,
            last_company=row.last_company,
            last_period=row.last_period,
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

    # Build skills
    skills = [skill.skill for skill in candidate.skills]

    # Build full name
    full_name = _compute_full_name(candidate.last_name, candidate.first_name, candidate.middle_name)
    age = _compute_age(candidate.birth_date)

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
        currency=candidate.currency,
        last_position=candidate.last_position,
        last_company=candidate.last_company,
        last_period=candidate.last_period,
        source=candidate.source,
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
        skills=skills,
        extra=candidate.extra,
        created_at=candidate.created_at
    )


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

    # Create candidate
    full_name = _compute_full_name(candidate_data.last_name, candidate_data.first_name, candidate_data.middle_name)

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
        salary_expectation=candidate_data.salary_expectation,
        currency=candidate_data.currency
    )

    session.add(candidate)
    await session.flush()

    # If vacancy_id provided, create application
    if candidate_data.vacancy_id:
        from ..models import Application  # Avoid circular import

        application = Application(
            company_id=company_id,
            candidate_id=candidate.id,
            vacancy_id=candidate_data.vacancy_id,
            stage="added",
            created_at=datetime.now(timezone.utc)
        )
        session.add(application)

    # Audit
    await audit(
        session,
        action="create",
        entity_type="candidate",
        entity_id=candidate.id,
        after={
            "full_name": full_name,
            "source": candidate_data.source,
            "vacancy_id": str(candidate_data.vacancy_id) if candidate_data.vacancy_id else None
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
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
        "city": candidate.city
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
    if candidate_data.salary_expectation is not None:
        candidate.salary_expectation = candidate_data.salary_expectation
    if candidate_data.currency is not None:
        candidate.currency = candidate_data.currency
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
            "city": candidate.city
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
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
            Application.company_id == company_id
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

    # Check if stage is valid
    if stage not in STAGES:
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

    # TODO: Create Event record for activity feed

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
        currency=candidate.currency,
        city=candidate.city,
        stage=stage,
        stage_color=STAGES[stage].color,
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