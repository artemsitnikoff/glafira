"""Сервис НАЗНАЧЕНИЯ тестов кандидатам + автоматизации воронки (модуль «Тесты», фаза 2Б).

Здесь:
  • ручное назначение теста рекрутёром (assign / remind / cancel) — привязка к Application;
  • брендированная/канальная доставка ссылки прохождения (email через шаблон Глафиры,
    telegram/hh — через существующий send_message);
  • авто-отправка ссылки на тест при переходе на целевой этап вакансии (send_test_links,
    паттерн send_interview_links);
  • авто-отказ по результату теста (maybe_auto_reject, opt-in по порогу test.auto_reject_below).

⚠️ ДЕЙСТВУЕТ С РЕАЛЬНЫМИ ЛЮДЬМИ. Предохранители: авто-отправка и авто-отказ работают
ТОЛЬКО при явном opt-in вакансии/теста (дефолт OFF). Идемпотентность — по активному
назначению (status in sent/started). Все изменяющие действия → audit_log; лента → Event(type='test').
"""
from __future__ import annotations

import html as _html
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..models import Application, Candidate, Event, Test, TestAssignment, Vacancy
from ..schemas.message import MessageCreate
from ..services.audit import audit
from ..services.company_display import resolve_company_display_name
from ..services.integrations.smtp.service import send_email
from ..services.integrations.smtp.templates import render_simple_email
from ..services.message import send_message

logger = logging.getLogger(__name__)

# TTL для авто-назначения теста (send_test_links): у авто-пути нет параметра ttl_days,
# берём тот же дефолт, что и у ручного назначения (TestAssignRequest.ttl_days=7).
_DEFAULT_TTL_DAYS = 7

_ACTIVE_STATUSES = ("sent", "started")
# Статусы, при которых АВТО-рассылка (send_test_links) НЕ должна повторно слать тест:
# уже приглашён (sent/started), уже прошёл (completed — иначе спам + ретейк перебьёт балл
# в воронке), рекрутёр отменил (cancelled — уважаем ручное решение). 'expired' НЕ включён:
# ссылка истекла, кандидат тест не прошёл → авто-переотправка свежей ссылки уместна.
_AUTOSEND_HANDLED_STATUSES = ("sent", "started", "completed", "cancelled")


def _has_telegram(candidate: Candidate) -> bool:
    """У кандидата есть, куда написать в Telegram: телефон или tg-username."""
    if candidate.phone:
        return True
    if (candidate.extra or {}).get("tg_username"):
        return True
    for m in (candidate.messengers or []):
        if isinstance(m, dict) and (m.get("type") or "").lower() == "telegram":
            return True
        if isinstance(m, str) and m.lower() == "telegram":
            return True
    return False


def _pick_channel(candidate: Optional[Candidate], explicit: Optional[str]) -> str:
    """Канал доставки: явный выбор рекрутёра либо авто-подбор по контактам кандидата."""
    if explicit in ("email", "telegram", "hh"):
        return explicit
    if candidate is None:
        return "email"
    if candidate.email:
        return "email"
    if _has_telegram(candidate):
        return "telegram"
    return "hh"


async def deliver_test_link(
    session: AsyncSession,
    *,
    company_id: UUID,
    candidate: Optional[Candidate],
    vacancy: Optional[Vacancy],
    url: str,
    channel: str,
    message: Optional[str],
    actor_user_id: Optional[UUID],
    application_id: Optional[UUID],
    days: Optional[int] = None,
) -> None:
    """Доставить ссылку прохождения теста кандидату. ВСЁ best-effort — сбой доставки
    НЕ должен ронять назначение (только logger.warning), как в send_interview_links.

    email  → брендированное письмо (шаблон Глафиры) через render_simple_email + send_email;
    telegram/hh → через существующий send_message (нужен actor_user_id = User; при None,
        т.е. авто-путь, эти каналы недоступны — лог и выход).
    """
    try:
        if candidate is None:
            logger.warning("[tests] доставка ссылки на тест: кандидат отсутствует")
            return

        vacancy_name = vacancy.name if vacancy is not None else ""

        if channel == "email":
            if not candidate.email:
                logger.warning(
                    "[tests] ссылка на тест не отправлена email — у кандидата %s нет email",
                    candidate.id,
                )
                return
            company_name = await resolve_company_display_name(session, company_id, vacancy)
            _co_text = f"в компанию «{company_name}» " if company_name else ""

            body_text = (
                f"Здравствуйте, {candidate.full_name or 'уважаемый кандидат'}!\n\n"
                f"Приглашаем вас пройти тестирование {_co_text}"
                f"на вакансию «{vacancy_name}».\n\n"
                f"Для прохождения перейдите по ссылке:\n{url}\n"
            )
            if days:
                body_text += f"\nСсылка действительна {days} дней."
            if message:
                body_text += f"\n\n{message}"

            _vac = _html.escape(vacancy_name)
            _company = _html.escape(company_name or "")
            _url = _html.escape(url)
            _co_html = (
                f'в компанию <strong style="color:#0F1620;font-weight:600;">«{_company}»</strong> '
                if _company else ''
            )
            _inner = (
                f'<p style="margin:0 0 14px;">Приглашаем вас пройти тестирование {_co_html}'
                f'на вакансию <strong style="color:#0F1620;font-weight:600;">«{_vac}»</strong>.</p>'
                f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:22px 0 6px;"><tr>'
                f'<td style="border-radius:8px;background:#2A8AF0;"><a href="{_url}" target="_blank" '
                f'style="display:inline-block;font-family:\'Inter\',Arial,sans-serif;font-size:15px;'
                f'font-weight:600;color:#FFFFFF;padding:13px 26px;border-radius:8px;">Пройти тестирование</a></td>'
                f'</tr></table>'
            )
            if days:
                _inner += (
                    f'<p style="margin:14px 0 0;font-size:13px;color:#5B6573;">'
                    f'Ссылка действительна {days} дней.</p>'
                )
            if message:
                _inner += (
                    f'<p style="margin:12px 0 0;font-size:14px;color:#1A1F29;">'
                    f'{_html.escape(message)}</p>'
                )

            body_html = render_simple_email(
                f"Здравствуйте, {candidate.full_name or 'уважаемый кандидат'}!",
                _inner,
                preheader=(
                    f"Приглашение пройти тестирование {_co_text}на вакансию {vacancy_name}"
                ),
                company_name=company_name,
            )
            await send_email(
                session,
                company_id,
                to=candidate.email,
                subject=(
                    f"Тестирование: {vacancy_name} — {company_name}"
                    if company_name else f"Тестирование: {vacancy_name}"
                ),
                body_text=body_text,
                body_html=body_html,
            )
            return

        # telegram / hh — только при наличии пользователя-отправителя (send_message).
        if actor_user_id is None:
            logger.warning(
                "[tests] авто-доставка ссылки на тест по каналу %s недоступна без пользователя-отправителя",
                channel,
            )
            return
        text_body = (
            f"Здравствуйте! Приглашаем пройти тестирование на вакансию «{vacancy_name}». "
            f"Ссылка: {url}"
        )
        if message:
            text_body += f"\n\n{message}"
        await send_message(
            session,
            candidate.id,
            MessageCreate(channel=channel, body=text_body, application_id=application_id),
            company_id,
            actor_user_id,
        )
    except Exception as e:
        logger.warning("[tests] не удалось доставить ссылку на тест (%s): %s", channel, e)


async def assign_test(
    session: AsyncSession,
    *,
    application_id: UUID,
    company_id: UUID,
    test_id: UUID,
    ttl_days: int,
    channel: Optional[str],
    message: Optional[str],
    created_by: Optional[UUID],
) -> TestAssignment:
    """Назначить тест кандидату (привязка к Application). Идемпотентно по активному
    назначению того же теста на той же заявке — повторный вызов НЕ плодит токены."""
    app = (
        await session.execute(
            select(Application).where(
                Application.id == application_id,
                Application.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    if app is None:
        raise NotFoundError("Заявка")

    test = (
        await session.execute(
            select(Test).where(Test.id == test_id, Test.company_id == company_id)
        )
    ).scalar_one_or_none()
    if test is None:
        raise NotFoundError("Тест")

    # Идемпотентность: активное назначение того же теста уже есть → возвращаем ЕГО.
    existing = (
        await session.execute(
            select(TestAssignment)
            .where(
                TestAssignment.application_id == application_id,
                TestAssignment.test_id == test_id,
                TestAssignment.company_id == company_id,
                TestAssignment.status.in_(_ACTIVE_STATUSES),
            )
            .order_by(TestAssignment.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    candidate = (
        await session.execute(
            select(Candidate).where(
                Candidate.id == app.candidate_id,
                Candidate.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    vacancy = (
        await session.execute(
            select(Vacancy).where(
                Vacancy.id == app.vacancy_id,
                Vacancy.company_id == company_id,
            )
        )
    ).scalar_one_or_none()

    resolved_channel = _pick_channel(candidate, channel)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

    assignment = TestAssignment(
        company_id=company_id,
        application_id=application_id,
        candidate_id=app.candidate_id,  # ⚠️ candidate из заявки — не доверяем клиенту
        test_id=test_id,
        token=token,
        expires_at=expires_at,
        status="sent",
        channel=resolved_channel,
        created_by=created_by,
    )
    session.add(assignment)
    await session.flush()  # получаем assignment.id / created_at

    url = f"{settings.FRONTEND_BASE_URL}/test/{token}"
    await deliver_test_link(
        session,
        company_id=company_id,
        candidate=candidate,
        vacancy=vacancy,
        url=url,
        channel=resolved_channel,
        message=message,
        actor_user_id=created_by,
        application_id=application_id,
        days=ttl_days,
    )

    cand_name = candidate.full_name if candidate else ""
    vac_name = vacancy.name if vacancy else ""
    session.add(Event(
        company_id=company_id,
        type="test",
        actor_type="human",
        actor_user_id=created_by,
        text=f"Кандидату {cand_name} отправлена ссылка на тест «{test.name}» (вакансия: {vac_name}).",
        entities=[],
        candidate_id=app.candidate_id,
        vacancy_id=app.vacancy_id,
    ))
    await audit(
        session,
        action="test_assigned",
        entity_type="application",
        entity_id=application_id,
        after={
            "test_id": str(test_id),
            "candidate_id": str(app.candidate_id),
            "channel": resolved_channel,
            "expires_at": expires_at.isoformat(),
        },
        actor_user_id=created_by,
        actor_type="human",
        company_id=company_id,
    )
    return assignment


async def remind_test(
    session: AsyncSession,
    *,
    application_id: UUID,
    assignment_id: UUID,
    company_id: UUID,
    actor_user_id: Optional[UUID],
) -> TestAssignment:
    """Переотправить ссылку (тот же токен) по активному назначению. Best-effort доставка."""
    assignment = (
        await session.execute(
            select(TestAssignment).where(
                TestAssignment.id == assignment_id,
                TestAssignment.application_id == application_id,
                TestAssignment.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise NotFoundError("Назначение теста")
    if assignment.status not in _ACTIVE_STATUSES:
        raise ValidationError("Переотправить можно только активное назначение")

    candidate = (
        await session.execute(
            select(Candidate).where(
                Candidate.id == assignment.candidate_id,
                Candidate.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    app = (
        await session.execute(
            select(Application).where(
                Application.id == application_id,
                Application.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    vacancy = None
    if app is not None:
        vacancy = (
            await session.execute(
                select(Vacancy).where(
                    Vacancy.id == app.vacancy_id,
                    Vacancy.company_id == company_id,
                )
            )
        ).scalar_one_or_none()

    channel = assignment.channel or _pick_channel(candidate, None)
    url = f"{settings.FRONTEND_BASE_URL}/test/{assignment.token}" if assignment.token else ""
    if url:
        await deliver_test_link(
            session,
            company_id=company_id,
            candidate=candidate,
            vacancy=vacancy,
            url=url,
            channel=channel,
            message=None,
            actor_user_id=actor_user_id,
            application_id=application_id,
        )

    await audit(
        session,
        action="test_reminded",
        entity_type="application",
        entity_id=application_id,
        after={"assignment_id": str(assignment_id), "channel": channel},
        actor_user_id=actor_user_id,
        actor_type="human",
        company_id=company_id,
    )
    return assignment


async def cancel_test(
    session: AsyncSession,
    *,
    application_id: UUID,
    assignment_id: UUID,
    company_id: UUID,
    actor_user_id: Optional[UUID],
) -> TestAssignment:
    """Отменить назначение теста. Пройденный (completed) отменить нельзя (409)."""
    assignment = (
        await session.execute(
            select(TestAssignment).where(
                TestAssignment.id == assignment_id,
                TestAssignment.application_id == application_id,
                TestAssignment.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise NotFoundError("Назначение теста")
    if assignment.status == "completed":
        raise ConflictError("Нельзя отменить пройденный тест")

    prev_status = assignment.status
    assignment.status = "cancelled"
    await audit(
        session,
        action="test_cancelled",
        entity_type="application",
        entity_id=application_id,
        before={"status": prev_status},
        after={"assignment_id": str(assignment_id), "status": "cancelled"},
        actor_user_id=actor_user_id,
        actor_type="human",
        company_id=company_id,
    )
    return assignment


async def maybe_auto_reject(
    session: AsyncSession,
    *,
    test,
    raw_score: int,
    application_id: UUID,
    company_id: UUID,
) -> None:
    """Авто-отказ по результату теста. Дефолт OFF: без порога test.auto_reject_below —
    ничего не делает. Балл >= порога — тоже пропуск. Иначе отклоняем заявку как AI.

    reject_application уже пишет StageHistory + Event(type='move') + audit (actor='ai').
    Если заявка уже отклонена — reject_application кинет ValidationError; здесь НЕ ловим
    (ловит вызывающий finalize_attempt через savepoint)."""
    if test.auto_reject_below is None:
        return
    if raw_score >= test.auto_reject_below:
        return
    # Локальный импорт — избегаем циклической зависимости на уровне модуля.
    from ..services.application import reject_application
    from ..schemas.application import RejectRequest

    await reject_application(
        session,
        application_id,
        RejectRequest(
            reason=(
                f"Автоотказ по тесту «{test.name}»: результат {raw_score} "
                f"ниже порога {test.auto_reject_below}"
            ),
            side="company",
        ),
        company_id,
        actor_user_id=None,
        actor_type="ai",
    )


async def send_test_links(
    session: AsyncSession, company_id: UUID, *, limit: int = 10
) -> dict:
    """Авто-отправка ссылок на тест кандидатам на целевом этапе (паттерн send_interview_links).

    Идемпотентно по активному назначению того же теста. Авто-путь = email-only (актора-
    пользователя нет → send_message недоступен). Коммит покандидатно. Возвращает
    статистику {'sent': N, 'skipped_active': N, 'failed': N}."""
    stats = {"sent": 0, "skipped_active": 0, "failed": 0}

    rows = (await session.execute(
        select(Application, Vacancy, Candidate)
        .join(Vacancy, Application.vacancy_id == Vacancy.id)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(
            Application.company_id == company_id,
            Vacancy.auto_test.is_(True),
            Vacancy.auto_test_id.isnot(None),
            Vacancy.auto_test_stage.isnot(None),
            Application.stage == Vacancy.auto_test_stage,
            Vacancy.deleted_at.is_(None),
            Candidate.deleted_at.is_(None),
        )
        .limit(limit)
    )).all()

    for app, vacancy, candidate in rows:
        try:
            # Идемпотентность авто-рассылки: не слать, если по этой заявке+тесту уже есть
            # обработанное назначение (приглашён/прошёл/отменён). Только 'expired' → можно
            # переотправить (кандидат так и не прошёл, ссылка истекла).
            existing = (await session.execute(
                select(TestAssignment.id).where(
                    TestAssignment.application_id == app.id,
                    TestAssignment.test_id == vacancy.auto_test_id,
                    TestAssignment.company_id == company_id,
                    TestAssignment.status.in_(_AUTOSEND_HANDLED_STATUSES),
                ).limit(1)
            )).scalar_one_or_none()
            if existing is not None:
                stats["skipped_active"] += 1
                continue

            test = (await session.execute(
                select(Test).where(
                    Test.id == vacancy.auto_test_id,
                    Test.company_id == company_id,
                )
            )).scalar_one_or_none()
            if test is None:
                stats["failed"] += 1
                continue

            token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(days=_DEFAULT_TTL_DAYS)
            assignment = TestAssignment(
                company_id=company_id,
                application_id=app.id,
                candidate_id=app.candidate_id,
                test_id=vacancy.auto_test_id,
                token=token,
                expires_at=expires_at,
                status="sent",
                channel="email",
                created_by=None,
            )
            session.add(assignment)
            await session.flush()

            url = f"{settings.FRONTEND_BASE_URL}/test/{token}"
            await deliver_test_link(
                session,
                company_id=company_id,
                candidate=candidate,
                vacancy=vacancy,
                url=url,
                channel="email",  # авто = email-only
                message=None,
                actor_user_id=None,
                application_id=app.id,
                days=_DEFAULT_TTL_DAYS,
            )

            session.add(Event(
                company_id=company_id,
                type="test",
                actor_type="ai",
                actor_user_id=None,
                text=(
                    f"Автоматизация: Глафира отправила кандидату {candidate.full_name} "
                    f"ссылку на тест «{test.name}» (вакансия: {vacancy.name})."
                ),
                entities=[],
                candidate_id=app.candidate_id,
                vacancy_id=app.vacancy_id,
            ))
            await audit(
                session,
                action="test_assigned",
                entity_type="application",
                entity_id=app.id,
                after={
                    "test_id": str(vacancy.auto_test_id),
                    "candidate_id": str(app.candidate_id),
                    "channel": "email",
                    "expires_at": expires_at.isoformat(),
                    "auto": True,
                },
                actor_user_id=None,
                actor_type="system",
                company_id=company_id,
            )
            await session.commit()
            stats["sent"] += 1
        except Exception as e:
            await session.rollback()
            logger.error(
                "[tests] авто-отправка теста не удалась для заявки %s: %s", app.id, e
            )
            stats["failed"] += 1

    return stats
