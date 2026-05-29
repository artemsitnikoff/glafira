"""Генерация резюме через Claude API"""

import logging
from uuid import UUID
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from .client import call_json
from .prompts import RESUME_GEN_SYSTEM_PROMPT, RESUME_GEN_USER_TEMPLATE
from ...core.errors import GlafiraParseError
from ...models import Candidate, CandidateExperience, CandidateSkill, CandidateEducation

logger = logging.getLogger(__name__)


async def generate_resume(
    session: AsyncSession,
    candidate: Candidate,
    vacancy_domain: str,
    quality_hint: str = "middle"
) -> None:
    """
    Генерирует AI-резюме для кандидата и сохраняет в БД.

    Args:
        session: DB сессия
        candidate: объект кандидата
        vacancy_domain: домен вакансии (Frontend, B2B Sales, etc.)
        quality_hint: уровень качества (junior, middle, senior)
    """
    try:
        # Подготавливаем данные для промпта
        user_prompt = RESUME_GEN_USER_TEMPLATE.format(
            name=candidate.full_name,
            age=getattr(candidate, 'age', 'не указан'),
            position=getattr(candidate, 'position', vacancy_domain),
            domain=vacancy_domain,
            quality_level=quality_hint
        )

        logger.info(f"Генерируем резюме для {candidate.full_name} ({vacancy_domain}, {quality_hint})")

        # Вызов AI
        result = await call_json(
            system=RESUME_GEN_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=3500
        )

        # Валидация результата
        if not isinstance(result, dict):
            raise GlafiraParseError(details={"reason": "Invalid JSON response from AI"})

        required_fields = ["summary", "experience", "skills", "education", "languages"]
        for field in required_fields:
            if field not in result:
                raise GlafiraParseError(details={"reason": f"Missing field: {field}"})

        # Создаем resume_text из структуры
        resume_text_parts = [result["summary"]]

        if result.get("experience"):
            resume_text_parts.append("\n\nОПЫТ РАБОТЫ:")
            for exp in result["experience"]:
                exp_text = f"• {exp.get('position', 'Должность не указана')}"
                if exp.get('company'):
                    exp_text += f" в {exp['company']}"
                if exp.get('period'):
                    exp_text += f" ({exp['period']})"
                if exp.get('description'):
                    exp_text += f"\n  {exp['description']}"
                resume_text_parts.append(exp_text)

        if result.get("skills"):
            skills_text = ", ".join(result["skills"])
            resume_text_parts.append(f"\n\nНАВЫКИ: {skills_text}")

        if result.get("education"):
            resume_text_parts.append("\n\nОБРАЗОВАНИЕ:")
            for edu in result["education"]:
                edu_text = f"• {edu.get('institution', 'Учебное заведение не указано')}"
                if edu.get('specialty'):
                    edu_text += f", {edu['specialty']}"
                if edu.get('years'):
                    edu_text += f" ({edu['years']})"
                resume_text_parts.append(edu_text)

        if result.get("languages"):
            languages_text = ", ".join(result["languages"])
            resume_text_parts.append(f"\n\nЯЗЫКИ: {languages_text}")

        # Сохраняем resume_text
        candidate.resume_text = "\n".join(resume_text_parts)

        # Создаем CandidateExperience записи
        if result.get("experience"):
            # Удаляем старые записи опыта (если есть)
            await session.execute(
                delete(CandidateExperience).where(
                    CandidateExperience.candidate_id == candidate.id
                )
            )

            for idx, exp_data in enumerate(result["experience"]):
                experience = CandidateExperience(
                    candidate_id=candidate.id,
                    position=exp_data.get("position", ""),
                    company=exp_data.get("company"),
                    period=exp_data.get("period"),
                    description=exp_data.get("description"),
                    order_index=idx
                )
                session.add(experience)

        # Создаем CandidateSkill записи
        if result.get("skills"):
            # Удаляем старые записи навыков (если есть)
            await session.execute(
                delete(CandidateSkill).where(
                    CandidateSkill.candidate_id == candidate.id
                )
            )

            for idx, skill_name in enumerate(result["skills"]):
                skill = CandidateSkill(
                    candidate_id=candidate.id,
                    skill=skill_name,
                    order_index=idx
                )
                session.add(skill)

        # Создаем CandidateEducation записи
        if result.get("education"):
            # Удаляем старые записи образования (если есть)
            await session.execute(
                delete(CandidateEducation).where(
                    CandidateEducation.candidate_id == candidate.id
                )
            )

            for idx, edu_data in enumerate(result["education"]):
                education = CandidateEducation(
                    candidate_id=candidate.id,
                    institution=edu_data.get("institution"),
                    specialty=edu_data.get("specialty"),
                    years=edu_data.get("years"),
                    order_index=idx
                )
                session.add(education)

        # Сохраняем языки в candidate.extra
        if result.get("languages"):
            existing_extra = candidate.extra or {}
            existing_extra.update({
                "demo": "true",  # Помечаем как демо-данные
                "languages": result["languages"]
            })
            candidate.extra = existing_extra

        await session.flush()
        logger.info(f"Резюме для {candidate.full_name} успешно создано")

    except Exception as e:
        logger.error(f"Ошибка генерации резюме для {candidate.full_name}: {e}")
        # При ошибке оставляем кандидата с пустым резюме, не падаем
        candidate.resume_text = f"Кандидат {candidate.full_name}. Резюме будет дополнено."