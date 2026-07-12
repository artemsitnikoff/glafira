"""Автоматизация записи на интервью (паттерн auto_qa).

Логика:
- Для заявок на этапе vacancy.auto_interview_stage (где vacancy.auto_interview=True)
  без активной interview_link создаём ссылку и шлём кандидату.
- Идемпотентно: если активная ссылка уже есть — не пересоздаём.
- Если участник вакансии без b24_user_id — НЕ шлём, пишем Event с ошибкой.
- Все действия → Event(type='interview', actor_type='system') + audit_log.

⚠️ ДЕЙСТВУЕТ С РЕАЛЬНЫМИ ЛЮДЬМИ. Предохранители:
- Только при vacancy.auto_interview=True (opt-in, дефолт off).
- Идемпотентность через check активной ссылки.
- Честная ошибка при незамапленных участниках (не рассылаем с пустыми данными).
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Application, Vacancy, Candidate, User, Event, Integration, InterviewLink, VacancyTeam
from ...services.audit import audit
from ...services.integrations.smtp.service import send_email
from ...config import settings

logger = logging.getLogger(__name__)

_DEFAULT_HORIZON_DAYS = 14


def _get_slot_settings(integration: Integration) -> dict:
    """Достаёт настройки слотов из integrations.config (не Fernet, обычные ключи)."""
    cfg = integration.config or {}
    return {
        "work_days": cfg.get("work_days", [1, 2, 3, 4, 5]),
        "work_start": cfg.get("work_start", "10:00"),
        "work_end": cfg.get("work_end", "18:00"),
        "duration_min": int(cfg.get("duration_min", 60)),
        "step_min": int(cfg.get("step_min", 30)),
        "horizon_days": int(cfg.get("horizon_days", _DEFAULT_HORIZON_DAYS)),
        "lead_hours": int(cfg.get("lead_hours", 24)),
        "tz": cfg.get("tz", "Europe/Moscow"),
        "interview_video_link": cfg.get("interview_video_link", ""),
    }


async def send_interview_links(
    session: AsyncSession, company_id: UUID, *, limit: int = 10
) -> dict:
    """Отправляет ссылки записи на интервью кандидатам на целевом этапе.

    Паттерн: auto_qa. Идемпотентно по наличию активной interview_link.
    Возвращает статистику {'sent': N, 'skipped_unmapped': N, 'skipped_active': N, 'failed': N}.
    """
    stats = {
        "sent": 0,
        "skipped_unmapped": 0,
        "skipped_active": 0,
        "failed": 0,
    }

    # Получаем Б24-интеграцию компании
    b24_row = (await session.execute(
        select(Integration).where(
            Integration.provider == "bitrix24",
            Integration.company_id == company_id,
        )
    )).scalar_one_or_none()

    if not b24_row or not (b24_row.config or {}).get("webhook_url"):
        logger.debug("[interview_schedule] Б24 не настроен для компании %s", company_id)
        return stats

    slot_settings = _get_slot_settings(b24_row)
    horizon_days = slot_settings["horizon_days"]

    # Ищем заявки на целевом этапе автоинтервью
    rows = (await session.execute(
        select(Application, Vacancy, Candidate)
        .join(Vacancy, Application.vacancy_id == Vacancy.id)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(
            Application.company_id == company_id,
            Vacancy.auto_interview.is_(True),
            Vacancy.auto_interview_stage.isnot(None),
            Application.stage == Vacancy.auto_interview_stage,
            Vacancy.deleted_at.is_(None),
            Candidate.deleted_at.is_(None),
        )
        .limit(limit)
    )).all()

    for app, vacancy, candidate in rows:
        # Проверяем активную ссылку (идемпотентность)
        existing_link = (await session.execute(
            select(InterviewLink).where(
                InterviewLink.application_id == app.id,
                InterviewLink.status == "active",
            )
        )).scalar_one_or_none()

        if existing_link:
            stats["skipped_active"] += 1
            continue

        # Загружаем команду вакансии с b24_user_id
        vacancy_with_team = (await session.execute(
            select(Vacancy)
            .where(Vacancy.id == vacancy.id)
            .options(
                selectinload(Vacancy.team).selectinload(VacancyTeam.user),
            )
        )).scalar_one_or_none()

        if not vacancy_with_team:
            stats["failed"] += 1
            continue

        # Собираем всех участников команды
        team_members: list[User] = [
            vt.user for vt in (vacancy_with_team.team or []) if vt.user
        ]

        # Добавляем ответственного если не в команде
        if vacancy_with_team.responsible_user_id:
            responsible_ids = {vt.user_id for vt in (vacancy_with_team.team or [])}
            if vacancy_with_team.responsible_user_id not in responsible_ids:
                resp_user = (await session.execute(
                    select(User).where(User.id == vacancy_with_team.responsible_user_id)
                )).scalar_one_or_none()
                if resp_user:
                    team_members.append(resp_user)

        # Проверяем маппинг b24_user_id у всех участников
        unmapped = [u for u in team_members if not u.b24_user_id]
        if unmapped:
            unmapped_names = ", ".join(u.full_name for u in unmapped)
            logger.warning(
                "[interview_schedule] Участники без b24_user_id для вакансии %s: %s",
                vacancy.id, unmapped_names,
            )
            # Идемпотентность: событие «не привязаны» пишем ОДИН РАЗ, иначе крон (раз в
            # 5 мин) спамит ленту. Если interview-событие для этой пары кандидат+вакансия
            # уже писалось — молчим (при повторных прогонах ничего не добавляем).
            already_notified = (await session.execute(
                select(Event.id).where(
                    Event.candidate_id == candidate.id,
                    Event.vacancy_id == vacancy.id,
                    Event.type == "interview",
                ).limit(1)
            )).scalar_one_or_none()
            if already_notified is not None:
                stats["skipped_unmapped"] += 1
                continue
            session.add(Event(
                company_id=company_id,
                type="interview",
                actor_type="ai",
                actor_user_id=None,
                text=(
                    f"Автоматизация: ссылка на интервью НЕ отправлена — не привязаны к "
                    f"Битрикс24 участники: {unmapped_names}. "
                    f"Кандидат: {candidate.full_name}, вакансия: {vacancy.name}."
                ),
                entities=[],
                candidate_id=candidate.id,
                vacancy_id=vacancy.id,
            ))
            await audit(
                session,
                action="interview_link_unmapped_participants",
                entity_type="application",
                entity_id=app.id,
                after={"unmapped": unmapped_names, "vacancy": vacancy.name},
                actor_user_id=None,
                actor_type="system",
                company_id=company_id,
            )
            await session.commit()
            stats["skipped_unmapped"] += 1
            continue

        # Создаём ссылку
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=horizon_days)
        link = InterviewLink(
            company_id=company_id,
            application_id=app.id,
            token=token,
            status="active",
            expires_at=expires_at,
        )
        session.add(link)
        await session.flush()  # получаем link.id

        # Формируем ссылку (FRONTEND_BASE_URL для публичной страницы)
        schedule_url = f"{settings.FRONTEND_BASE_URL}/schedule/{token}"

        # Шлём email кандидату (если есть email и настроен SMTP)
        try:
            if candidate.email:
                body_text = (
                    f"Здравствуйте, {candidate.full_name or 'уважаемый кандидат'}!\n\n"
                    f"Приглашаем вас на интервью по вакансии «{vacancy.name}».\n\n"
                    f"Для выбора удобного времени перейдите по ссылке:\n{schedule_url}\n\n"
                    f"Ссылка действительна {horizon_days} дней."
                )
                if slot_settings["interview_video_link"]:
                    body_text += (
                        f"\n\nСсылка на видеовстречу: {slot_settings['interview_video_link']}"
                    )

                await send_email(
                    session,
                    company_id,
                    to=candidate.email,
                    subject=f"Запись на интервью: {vacancy.name}",
                    body_text=body_text,
                )
        except Exception as e:
            logger.warning(
                "[interview_schedule] Не удалось отправить email кандидату %s: %s",
                candidate.id, e,
            )
            # Ссылка создана, но email не ушёл — логируем, не откатываем

        # Event + audit
        session.add(Event(
            company_id=company_id,
            type="interview",
            actor_type="ai",
            actor_user_id=None,
            text=(
                f"Автоматизация: Глафира отправила кандидату {candidate.full_name} "
                f"ссылку для записи на интервью (вакансия: {vacancy.name})."
            ),
            entities=[],
            candidate_id=candidate.id,
            vacancy_id=vacancy.id,
        ))
        await audit(
            session,
            action="interview_link_sent",
            entity_type="application",
            entity_id=app.id,
            after={
                "candidate_id": str(candidate.id),
                "vacancy_id": str(vacancy.id),
                "expires_at": expires_at.isoformat(),
            },
            actor_user_id=None,
            actor_type="system",
            company_id=company_id,
        )
        await session.commit()
        stats["sent"] += 1

    return stats
