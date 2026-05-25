"""Скоринг кандидатов через Claude API"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .client import call_json
from .prompts import SCORING_SYSTEM_PROMPT, SCORING_USER_TEMPLATE
from ...core.errors import NotFoundError
from ...models import Candidate, Vacancy, Application, AiEvaluation, Event, CandidateExperience, CandidateSkill
from ...services.audit import audit


def _build_experience_text(experiences: list) -> str:
    """Build experience text from CandidateExperience objects"""
    if not experiences:
        return "Опыт работы не указан"

    lines = []
    for exp in experiences:
        line = f"• {exp.position or 'Должность не указана'}"
        if exp.company:
            line += f" в {exp.company}"
        if exp.period:
            line += f" ({exp.period})"
        if exp.description:
            line += f"\n  {exp.description[:200]}..."
        lines.append(line)

    return "\n".join(lines)


def _build_skills_text(skills: list) -> str:
    """Build skills text from CandidateSkill objects"""
    if not skills:
        return "Навыки не указаны"

    skill_names = [skill.name for skill in skills if skill.name]
    return ", ".join(skill_names) if skill_names else "Навыки не указаны"


async def score_candidate(
    session: AsyncSession,
    *,
    candidate_id: UUID,
    vacancy_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> AiEvaluation:
    """Score candidate for a specific vacancy"""

    # Get candidate with related data
    candidate_result = await session.execute(
        select(Candidate)
        .options(
            joinedload(Candidate.experience),
            joinedload(Candidate.skills)
        )
        .where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    candidate = candidate_result.unique().scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Кандидат")

    # Get vacancy
    vacancy_result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id,
            Vacancy.deleted_at.is_(None)
        )
    )
    vacancy = vacancy_result.scalar_one_or_none()
    if not vacancy:
        raise NotFoundError("Вакансия")

    # Check if application exists
    application_result = await session.execute(
        select(Application).where(
            Application.candidate_id == candidate_id,
            Application.vacancy_id == vacancy_id
        )
    )
    application = application_result.scalar_one_or_none()

    # Build prompt data
    experience_text = _build_experience_text(candidate.experience)
    skills_text = _build_skills_text(candidate.skills)

    # Format salary
    vacancy_salary = "не указана"
    if vacancy.salary_from and vacancy.salary_to:
        vacancy_salary = f"{vacancy.salary_from:,} - {vacancy.salary_to:,} {vacancy.currency}"
    elif vacancy.salary_from:
        vacancy_salary = f"от {vacancy.salary_from:,} {vacancy.currency}"
    elif vacancy.salary_to:
        vacancy_salary = f"до {vacancy.salary_to:,} {vacancy.currency}"

    candidate_salary = "не указана"
    if candidate.salary_expectation:
        candidate_salary = f"{candidate.salary_expectation:,} {candidate.currency}"

    # Create user prompt
    user_prompt = SCORING_USER_TEMPLATE.format(
        vacancy_name=vacancy.name,
        vacancy_city=vacancy.city or "не указан",
        vacancy_salary=vacancy_salary,
        vacancy_description=vacancy.description or "описание отсутствует",
        candidate_name=candidate.full_name,
        candidate_city=candidate.city or "не указан",
        candidate_phone=candidate.phone or "не указан",
        candidate_email=candidate.email or "не указан",
        resume_text=candidate.resume_text or "резюме не загружено",
        experience_text=experience_text,
        skills_text=skills_text,
        salary_expectation=candidate_salary
    )

    # Call Claude API
    response_data = await call_json(
        system=SCORING_SYSTEM_PROMPT,
        user=user_prompt,
        max_tokens=2048
    )

    # Validate required fields
    required_fields = ['score', 'verdict', 'summary', 'strengths', 'risks', 'requirements_match', 'forecast']
    for field in required_fields:
        if field not in response_data:
            response_data[field] = None

    # Ensure score is valid integer
    if not isinstance(response_data['score'], int) or not (0 <= response_data['score'] <= 100):
        response_data['score'] = 50  # Default score if invalid

    # Ensure verdict is valid
    if response_data['verdict'] not in ['good', 'partial', 'bad']:
        response_data['verdict'] = 'partial'

    # Create evaluation record
    now = datetime.now(timezone.utc)
    evaluation = AiEvaluation(
        company_id=company_id,
        candidate_id=candidate_id,
        application_id=application.id if application else None,
        score=response_data['score'],
        verdict=response_data['verdict'],
        summary=response_data['summary'] or "",
        strengths=response_data['strengths'] or [],
        risks=response_data['risks'] or [],
        requirements_match=response_data['requirements_match'] or {},
        forecast=response_data.get('forecast'),
        model=f"claude-sonnet-4-{now.strftime('%Y%m%d')}",
        created_at=now
    )

    session.add(evaluation)

    # Update candidate ai_score
    candidate.ai_score = response_data['score']

    # Update application ai_score if exists
    if application:
        application.ai_score = response_data['score']

    # Create event
    event = Event(
        company_id=company_id,
        type='score',
        actor_type='ai',
        actor_user_id=actor_user_id,
        text=f"Глафира оценила: {response_data['score']}, вердикт «{response_data['verdict']}»",
        entities=[
            {"type": "candidate", "id": str(candidate_id), "label": candidate.full_name},
            {"type": "vacancy", "id": str(vacancy_id), "label": vacancy.name},
            {"type": "evaluation", "id": str(evaluation.id), "label": f"Оценка {response_data['score']}"}
        ],
        candidate_id=candidate_id,
        vacancy_id=vacancy_id,
        created_at=now
    )
    session.add(event)

    # Audit log
    await audit(
        session,
        action='glafira_score',
        entity_type='ai_evaluation',
        entity_id=evaluation.id,
        after={
            'score': response_data['score'],
            'verdict': response_data['verdict'],
            'candidate_id': str(candidate_id),
            'vacancy_id': str(vacancy_id)
        },
        actor_user_id=actor_user_id,
        actor_type='ai',
        company_id=company_id,
    )

    await session.flush()
    return evaluation