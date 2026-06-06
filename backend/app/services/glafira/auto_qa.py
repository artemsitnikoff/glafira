"""П.2 автоматизации воронки — уточняющие вопросы кандидату + автоперевод на ответах.

⚠️ ДЕЙСТВУЕТ С РЕАЛЬНЫМИ ЛЮДЬМИ. Предохранители:
- Вопросы задаются ОДИН РАЗ (флаг Application.auto_qa_asked_at) — анти-спам/анти-зацикливание.
- Только канал hh (реальная отправка). Нет канала/токена → НЕ действуем (не fake, не ставим
  asked_at → ретрай позже).
- Только режимы Глафиры A/B (в C автоматики нет).
- Анализ ответов — строгий LLM-JSON; при сбое/невнятности НЕ двигаем (оставляем рекрутёру),
  никакого фейка. Перевод только ВПЕРЁД (Отклик→Отобран) — обратимо.
- Все действия → audit_log с actor_type='ai'.

Две половины:
  ask_auto_qa_questions   — задать вопросы (хук в cron score_pending, ПОСЛЕ скоринга: у заявки
                            уже есть AiEvaluation.questions).
  analyze_and_advance     — проанализировать ответ и перевести (хук в poll_hh_messages,
                            event-driven при НОВОМ входящем сообщении).
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Application, Vacancy, Candidate, AiEvaluation, Message
from ...schemas.application import MoveRequest
from ...services.audit import audit
from ...services.application import move_application
from ...services.integrations.hh import client as hh_client
from ...services.integrations.hh.service import get_valid_access_token
from .client import call_json

logger = logging.getLogger(__name__)

_ANALYZE_SYSTEM = (
    "Ты — ассистент рекрутёра. Тебе дают короткий диалог: Глафира задала кандидату уточняющие "
    "вопросы по вакансии, кандидат ответил (или ответил частично). Реши, стоит ли продвинуть "
    "кандидата на следующий этап «Отобран». proceed=true ТОЛЬКО если ответы содержательны и "
    "подтверждают пригодность/заинтересованность кандидата. При уклончивых, пустых, нерелевантных "
    "ответах, явной незаинтересованности или отказе — proceed=false (оставить рекрутёру). "
    "Отвечай СТРОГО валидным JSON без текста вокруг: {\"proceed\": true|false, \"reason\": \"кратко почему\"}."
)


def _first_name(full_name: str | None) -> str:
    parts = (full_name or "").split()
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else "коллега"


def _compose_questions_message(candidate: Candidate, vacancy: Vacancy, questions: list[str]) -> str:
    lines = [
        f"Здравствуйте, {_first_name(candidate.full_name)}! Меня зовут Глафира, я ассистент по "
        f"подбору. Спасибо за отклик на вакансию «{vacancy.name}». Чтобы лучше понять ваш опыт, "
        f"уточните, пожалуйста, пару моментов:",
        "",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    lines.append("Заранее благодарю за ответы!")
    return "\n".join(lines)


async def ask_auto_qa_questions(session: AsyncSession, company_id: UUID, *, limit: int = 10) -> dict:
    """Задаёт уточняющие вопросы hh-кандидатам на этапе «Отклик» (один раз). Идемпотентно
    по флагу auto_qa_asked_at. Возвращает статистику."""
    stats = {"asked": 0, "skipped_no_questions": 0, "skipped_no_channel": 0, "failed": 0}

    try:
        access_token = await get_valid_access_token(session, company_id)
    except Exception:
        # hh не подключён — П.2 работает только для hh-кандидатов, тихо выходим
        return stats

    rows = (await session.execute(
        select(Application, Vacancy, Candidate)
        .join(Vacancy, Application.vacancy_id == Vacancy.id)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(
            Application.company_id == company_id,
            Application.stage == "response",
            Application.auto_qa_asked_at.is_(None),
            Application.hh_negotiation_id.isnot(None),
            Vacancy.auto_qa.is_(True),
            Vacancy.glafira_mode.in_(("A", "B")),
            Vacancy.deleted_at.is_(None),
            Candidate.deleted_at.is_(None),
        )
        .limit(limit)
    )).all()

    for app, vacancy, candidate in rows:
        # Вопросы — из последней AiEvaluation заявки (скоринг их уже сгенерил)
        ev = (await session.execute(
            select(AiEvaluation)
            .where(AiEvaluation.application_id == app.id)
            .order_by(desc(AiEvaluation.created_at))
            .limit(1)
        )).scalar_one_or_none()
        raw_q = ev.questions if (ev and isinstance(ev.questions, list)) else []
        questions = [str(q).strip() for q in raw_q if str(q).strip()][:5]
        if not questions:
            stats["skipped_no_questions"] += 1  # нечего спрашивать — НЕ шлём пустое/генерик
            continue

        # Резолвим chat_id (лениво)
        chat_id = app.hh_chat_id
        if not chat_id:
            try:
                nego = await hh_client.get_negotiation(access_token, app.hh_negotiation_id)
                chat_id = nego.get("chat_id")
                if chat_id:
                    app.hh_chat_id = chat_id
                    await session.flush()
            except Exception as e:
                logger.warning("[auto_qa] не удалось получить chat_id app=%s: %s", app.id, e)
        if not chat_id:
            stats["skipped_no_channel"] += 1  # нет канала → НЕ ставим asked_at (ретрай позже)
            continue

        body = _compose_questions_message(candidate, vacancy, questions)
        try:
            resp = await hh_client.send_chat_message(access_token, chat_id, body)
        except Exception as e:
            stats["failed"] += 1
            logger.warning("[auto_qa] отправка вопросов не удалась app=%s: %s", app.id, e)
            continue  # НЕ ставим asked_at → ретрай позже

        now = datetime.now(timezone.utc)
        session.add(Message(
            company_id=company_id, candidate_id=candidate.id, application_id=app.id,
            channel="hh", direction="out", sender_type="ai", sender_user_id=None,
            body=body, sent_at=now, created_at=now,
            external_id=str(resp.get("id", "")),
        ))
        app.auto_qa_asked_at = now  # анти-зацикливание: задаём ОДИН раз
        await audit(
            session, action="auto_qa_asked", entity_type="application", entity_id=app.id,
            after={"candidate_id": str(candidate.id), "vacancy_id": str(app.vacancy_id),
                   "questions": questions},
            actor_user_id=None, actor_type="ai", company_id=company_id,
        )
        await session.commit()  # покандидатно: сбой одного не откатывает остальных
        stats["asked"] += 1

    return stats


async def analyze_and_advance(session: AsyncSession, application: Application, company_id: UUID) -> bool:
    """Анализирует диалог (вопросы Глафиры + ответы кандидата) и при подтверждении переводит
    Отклик→Отобран. Вызывать при НОВОМ входящем сообщении. НЕ двигает при сбое/невнятности.
    Возвращает True, если перевёл."""
    # Предохранители: только «Отклик», только если вопросы реально задавались, режим A/B
    if application.stage != "response" or application.auto_qa_asked_at is None:
        return False
    vacancy = await session.get(Vacancy, application.vacancy_id)
    if not vacancy or not vacancy.auto_qa or vacancy.glafira_mode not in ("A", "B"):
        return False

    msgs = (await session.execute(
        select(Message)
        .where(Message.application_id == application.id)
        .order_by(Message.created_at)
    )).scalars().all()
    if not any(m.direction == "in" for m in msgs):
        return False  # кандидат ещё не ответил

    dialog = "\n".join(
        f"{'Глафира' if m.direction == 'out' else 'Кандидат'}: {m.body}" for m in msgs
    )
    user_prompt = f"Вакансия: {vacancy.name}\n\nДиалог:\n{dialog}"

    try:
        result = await call_json(system=_ANALYZE_SYSTEM, user=user_prompt, max_tokens=512)
        proceed = bool(result.get("proceed"))
        reason = str(result.get("reason") or "")[:500]
    except Exception as e:
        # Сбой LLM/парсинга → НЕ двигаем (не fake), оставляем рекрутёру
        logger.warning("[auto_qa] анализ ответов не удался app=%s: %s", application.id, e)
        return False

    if not proceed:
        logger.info("[auto_qa] ответы не подтвердили перевод app=%s: %s", application.id, reason)
        return False

    try:
        await move_application(
            session, application.id, MoveRequest(to_stage="selected"), company_id,
            actor_user_id=None, actor_type="ai",
        )
    except Exception as e:
        logger.warning("[auto_qa] перевод не удался app=%s: %s", application.id, e)
        return False

    await audit(
        session, action="auto_qa_advanced", entity_type="application", entity_id=application.id,
        after={"candidate_id": str(application.candidate_id), "vacancy_id": str(application.vacancy_id),
               "reason": reason},
        actor_user_id=None, actor_type="ai", company_id=company_id,
    )
    await session.commit()
    logger.info("[auto_qa] кандидат переведён Отклик→Отобран app=%s: %s", application.id, reason)
    return True
