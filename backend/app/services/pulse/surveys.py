"""Сервис для управления опросами пульса"""

import secrets
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...models import Employee, PulseSurvey, SurveyTemplate, Company
from ...schemas.pulse import BulkRunSurveyRequest, BulkRunSurveyResult, PublicAnswer
from ...core.errors import NotFoundError, ValidationError, ConflictError
from ...services.audit import audit


# --- Маппинг человекочитаемой шкалы шаблона на тип ввода публичной страницы ---

def scale_to_kind(scale: str | None) -> str:
    """Определяет тип контрола по строке шкалы из шаблона опроса.

    emoji5  — 5 смайликов настроения (😡 😞 😐 🙂 😄)
    scale5  — 1·2·3·4·5
    yesno   — Да / Нет
    nps11   — 0–10 (eNPS)
    text    — свободный текст
    """
    s = (scale or "").lower()
    if any(ch in (scale or "") for ch in ("😡", "😞", "😐", "🙂", "😄")):
        return "emoji5"
    if "да" in s and "нет" in s:
        return "yesno"
    if "enps" in s or "0–10" in (scale or "") or "0-10" in s:
        return "nps11"
    if "текст" in s or "📝" in (scale or ""):
        return "text"
    # «1 · 2 · 3 · 4 · 5» и подобные числовые → scale5
    return "scale5"


def _snapshot_questions(template: SurveyTemplate) -> list[dict]:
    """Снимает включённые вопросы шаблона в неизменяемый снапшот для опроса."""
    raw = template.questions
    # questions хранится как list[dict] (см. survey_templates DEFAULT_SURVEY_TEMPLATES)
    items = raw if isinstance(raw, list) else list(raw.values()) if isinstance(raw, dict) else []
    snapshot: list[dict] = []
    for q in items:
        if not isinstance(q, dict):
            continue
        if q.get("enabled") is False:
            continue
        snapshot.append({
            "id": q.get("id") or f"q{len(snapshot) + 1}",
            "text": q.get("text", ""),
            "scale": q.get("scale"),
            "kind": scale_to_kind(q.get("scale")),
            "optional": bool(q.get("optional", False)),
        })
    return snapshot


def _type_from_trigger_day(trigger_day: int | None) -> str:
    """Тип опроса (бейдж) из дня запуска шаблона. CHECK: weekly|monthly|special|enps."""
    if trigger_day is None:
        return "special"
    if trigger_day <= 7:
        return "weekly"
    if trigger_day <= 30:
        return "monthly"
    return "special"


def _compute_overall_score(questions: list[dict], answers_by_id: dict[str, str]) -> Decimal | None:
    """Средняя оценка по 5-балльным вопросам (emoji5 / scale5). Прочие шкалы
    (Да/Нет, 0–10, текст) в средний балл не входят — разные шкалы не усредняем.
    Возвращает None, если ни одного 5-балльного ответа нет.
    """
    vals: list[int] = []
    for q in questions:
        if q.get("kind") not in ("emoji5", "scale5"):
            continue
        raw = answers_by_id.get(q.get("id"))
        if raw is None:
            continue
        try:
            v = int(str(raw).strip())
        except (ValueError, TypeError):
            continue
        if 1 <= v <= 5:
            vals.append(v)
    if not vals:
        return None
    avg = Decimal(sum(vals)) / Decimal(len(vals))
    return avg.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


async def list_employee_surveys(
    session: AsyncSession,
    employee_id: UUID,
    company_id: UUID,
) -> list[PulseSurvey]:
    """Получает список опросов сотрудника"""

    employee_query = select(Employee).where(
        Employee.id == employee_id,
        Employee.company_id == company_id
    )
    employee_result = await session.execute(employee_query)
    employee = employee_result.scalar_one_or_none()

    if not employee:
        raise NotFoundError("Сотрудник")

    query = select(PulseSurvey).where(
        PulseSurvey.employee_id == employee_id,
        PulseSurvey.company_id == company_id
    ).order_by(PulseSurvey.sent_at.desc())

    result = await session.execute(query)
    return result.scalars().all()


async def launch_survey(
    session: AsyncSession,
    employee_id: UUID,
    template_id: UUID,
    company_id: UUID,
    actor_user_id: UUID,
) -> PulseSurvey:
    """Запускает опрос по выбранному шаблону: снапшотит вопросы, генерит публичную
    ссылку (public_token). Реальной отправки пока нет — HR копирует ссылку вручную.
    """

    employee_query = select(Employee).where(
        Employee.id == employee_id,
        Employee.company_id == company_id
    )
    employee = (await session.execute(employee_query)).scalar_one_or_none()
    if not employee:
        raise NotFoundError("Сотрудник")

    template_query = select(SurveyTemplate).where(
        SurveyTemplate.id == template_id,
        SurveyTemplate.company_id == company_id
    )
    template = (await session.execute(template_query)).scalar_one_or_none()
    if not template:
        raise NotFoundError("Шаблон опроса")

    snapshot = _snapshot_questions(template)
    if not snapshot:
        raise ValidationError("В шаблоне нет включённых вопросов")

    survey = PulseSurvey(
        company_id=company_id,
        employee_id=employee_id,
        type=_type_from_trigger_day(template.trigger_day),
        template_key=template.name,
        sent_at=datetime.now(timezone.utc),
        answers=[],
        questions=snapshot,
        public_token=secrets.token_urlsafe(32),
    )

    session.add(survey)
    await session.flush()

    await audit(
        session,
        action="survey_launched",
        entity_type="pulse_survey",
        entity_id=survey.id,
        after={
            "template_id": str(template_id),
            "template_name": template.name,
            "employee_id": str(employee_id),
            "questions_count": len(snapshot),
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    return survey


async def bulk_run_survey(
    session: AsyncSession,
    data: BulkRunSurveyRequest,
    company_id: UUID,
    actor_user_id: UUID,
) -> BulkRunSurveyResult:
    """Atomic bulk survey creation for multiple employees"""

    if not data.employee_ids:
        return BulkRunSurveyResult(launched_count=0)

    employees_query = select(Employee).where(
        Employee.id.in_(data.employee_ids),
        Employee.company_id == company_id
    )
    employees_result = await session.execute(employees_query)
    found_employees = employees_result.scalars().all()

    found_employee_ids = {emp.id for emp in found_employees}
    requested_employee_ids = set(data.employee_ids)

    if found_employee_ids != requested_employee_ids:
        missing_ids = requested_employee_ids - found_employee_ids
        raise NotFoundError(f"Сотрудники с ID {list(missing_ids)} не найдены")

    # Шаблон для bulk: template_key — это имя шаблона (см. фронт handleBulkRun)
    template = (await session.execute(
        select(SurveyTemplate).where(
            SurveyTemplate.name == data.template_key,
            SurveyTemplate.company_id == company_id,
        )
    )).scalar_one_or_none()
    snapshot = _snapshot_questions(template) if template else []
    survey_type = _type_from_trigger_day(template.trigger_day) if template else "weekly"

    send_at = data.send_at or datetime.now(timezone.utc)
    launched_count = 0

    for employee in found_employees:
        survey = PulseSurvey(
            company_id=company_id,
            employee_id=employee.id,
            type=survey_type,
            template_key=data.template_key,
            sent_at=send_at,
            answers=[],
            questions=snapshot,
            public_token=secrets.token_urlsafe(32),
        )
        session.add(survey)
        launched_count += 1

        await audit(
            session,
            action="survey_run",
            entity_type="pulse_survey",
            entity_id=survey.id,
            after={
                "template_key": data.template_key,
                "employee_id": str(employee.id),
                "bulk_operation": True,
            },
            actor_user_id=actor_user_id,
            company_id=company_id,
        )

    await session.flush()

    return BulkRunSurveyResult(launched_count=launched_count)


# ===== Публичная (без авторизации) сторона: проходит респондент по ссылке =====

async def get_public_survey(session: AsyncSession, token: str) -> tuple[PulseSurvey, Employee, Company]:
    """Находит опрос по секретному токену + сотрудника и компанию (для брендинга)."""
    if not token:
        raise NotFoundError("Опрос")

    survey = (await session.execute(
        select(PulseSurvey)
        .where(PulseSurvey.public_token == token)
        .options(selectinload(PulseSurvey.employee))
    )).scalar_one_or_none()
    if not survey:
        raise NotFoundError("Опрос")

    employee = survey.employee
    company = (await session.execute(
        select(Company).where(Company.id == survey.company_id)
    )).scalar_one_or_none()

    return survey, employee, company


async def submit_public_survey(
    session: AsyncSession,
    token: str,
    answers: list[PublicAnswer],
) -> PulseSurvey:
    """Сохраняет ответы респондента, ставит answered_at, считает overall_score.
    Идемпотентно по факту: повторная отправка отклоняется (опрос уже отвечен).
    """
    survey = (await session.execute(
        select(PulseSurvey).where(PulseSurvey.public_token == token)
    )).scalar_one_or_none()
    if not survey:
        raise NotFoundError("Опрос")

    if survey.answered_at is not None:
        raise ConflictError("Опрос уже пройден")

    questions: list[dict] = survey.questions or []
    valid_ids = {q.get("id") for q in questions}
    answers_by_id = {a.id: (a.answer or "").strip() for a in answers if a.id in valid_ids}

    # Обязательные (не optional) вопросы должны иметь непустой ответ
    for q in questions:
        if q.get("optional"):
            continue
        if not answers_by_id.get(q.get("id")):
            raise ValidationError(f"Не отвечен обязательный вопрос: {q.get('text', q.get('id'))}")

    # Сохраняем в читаемом виде: текст вопроса + ответ
    stored = [
        {
            "id": q.get("id"),
            "text": q.get("text", ""),
            "scale": q.get("scale"),
            "kind": q.get("kind"),
            "answer": answers_by_id.get(q.get("id"), ""),
        }
        for q in questions
    ]

    survey.answers = stored
    survey.answered_at = datetime.now(timezone.utc)
    survey.overall_score = _compute_overall_score(questions, answers_by_id)

    await session.flush()

    # Действие респондента — системное (нет авторизованного пользователя)
    await audit(
        session,
        action="survey_answered",
        entity_type="pulse_survey",
        entity_id=survey.id,
        after={
            "employee_id": str(survey.employee_id),
            "overall_score": float(survey.overall_score) if survey.overall_score is not None else None,
        },
        actor_user_id=None,
        actor_type="system",
        company_id=survey.company_id,
    )

    return survey
