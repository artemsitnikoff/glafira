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

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Application, Vacancy, Candidate, AiEvaluation, Message, Event
from ...schemas.application import MoveRequest, RejectRequest
from ...services.audit import audit
from ...services.application import move_application, reject_application
from ...services.settings.reject_reasons import list_reject_reasons
from ...services.integrations.hh import client as hh_client
from ...services.integrations.hh.service import get_valid_access_token
from .client import call_json
from ..settings.glafira import get_company_openrouter_key

logger = logging.getLogger(__name__)

_ANALYZE_SYSTEM = (
    "Ты — ассистент рекрутёра. Тебе дают короткий диалог: Глафира задала кандидату уточняющие "
    "вопросы по вакансии, кандидат ответил (или ответил частично). Реши, стоит ли продвинуть "
    "кандидата на следующий этап «Отобран». proceed=true ТОЛЬКО если ответы содержательны и "
    "подтверждают пригодность/заинтересованность кандидата. При уклончивых, пустых, нерелевантных "
    "ответах, явной незаинтересованности или отказе — proceed=false (оставить рекрутёру). "
    "Отвечай СТРОГО валидным JSON без текста вокруг: {\"proceed\": true|false, \"reason\": \"кратко почему\"}."
)

# П.3 — анализ незаинтересованности. Высокий порог уверенности: ложный автоотказ = отшили
# хорошего кандидата (необратимо). При сомнении — НЕ отказываем.
_REJECT_SYSTEM = (
    "Ты анализируешь переписку рекрутёра/Глафиры с кандидатом по вакансии. Определи, ПОТЕРЯЛ ли "
    "кандидат интерес: явно отказался, принял другой оффер, передумал, сообщил что не ищет работу "
    "или не рассматривает эту позицию. Тебе дан список доступных причин отказа со стороны кандидата. "
    "Верни СТРОГО валидный JSON без текста вокруг: {\"disinterested\": true|false, \"confidence\": число 0..1, "
    "\"reason\": \"точная строка из списка причин ИЛИ пустая строка\", \"quote\": \"фраза кандидата, "
    "показывающая незаинтересованность\"}. disinterested=true ТОЛЬКО при ЯВНЫХ, недвусмысленных признаках; "
    "при нейтральном/деловом диалоге, обсуждении деталей, молчании или любых сомнениях — false и низкий confidence. "
    "reason выбирай ТОЛЬКО из предложенного списка (точную строку); если ни одна не подходит — пустая строка."
)
_REJECT_CONFIDENCE_THRESHOLD = 0.85


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
            # Источник П.2 — настраиваемый (vacancy.auto_qa_stage), NULL→'response'.
            Application.stage == func.coalesce(Vacancy.auto_qa_stage, "response"),
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
        # Развилка вопросов П.2: 'fixed' = статический текст вакансии (рекрутёр задал сам/
        # из шаблона), всегда один и тот же; иначе 'weak' = вопросы по слабым сторонам,
        # сгенерированные при скоринге (AiEvaluation.questions). Пусто → НЕ шлём.
        if (vacancy.auto_qa_mode or "weak") == "fixed":
            # auto_qa_fixed_text может быть HTML из rich-редактора → в hh-чат шлём чистый
            # текст (теги убираем, переносы/списки сохраняем). Плоский текст пройдёт как есть.
            from .scoring import _strip_html
            body = _strip_html(vacancy.auto_qa_fixed_text)
            if not body:
                stats["skipped_no_questions"] += 1  # нет статического текста — НЕ шлём пустое
                continue
        else:
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
            body = _compose_questions_message(candidate, vacancy, questions)

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
        # Автоматизация → лента «Все действия» (вид автоматизации + что произошло).
        session.add(Event(
            company_id=company_id,
            type="qual",
            actor_type="ai",
            actor_user_id=None,
            text=(
                f"Автоматизация: Глафира задала кандидату {candidate.full_name} "
                f"уточняющие вопросы ("
                + ("по слабым местам резюме" if (vacancy.auto_qa_mode or "weak") == "weak" else "заготовленные")
                + ")."
            ),
            entities=[],
            candidate_id=candidate.id,
            vacancy_id=app.vacancy_id,
        ))
        app.auto_qa_asked_at = now  # анти-зацикливание: задаём ОДИН раз
        await audit(
            session, action="auto_qa_asked", entity_type="application", entity_id=app.id,
            # Фиксируем РЕАЛЬНО отправленный текст + режим (§2.2). `body` определён в обеих
            # ветках (weak/fixed); прежняя `questions` была доступна только в weak →
            # UnboundLocalError в fixed-режиме (после отправки, до commit → повторный спам).
            after={"candidate_id": str(candidate.id), "vacancy_id": str(app.vacancy_id),
                   "mode": (vacancy.auto_qa_mode or "weak"), "body": body},
            actor_user_id=None, actor_type="ai", company_id=company_id,
        )
        await session.commit()  # покандидатно: сбой одного не откатывает остальных
        stats["asked"] += 1

    return stats


async def analyze_and_advance(session: AsyncSession, application: Application, company_id: UUID) -> bool:
    """Анализирует диалог (вопросы Глафиры + ответы кандидата) и при подтверждении переводит
    Отклик→Отобран. Вызывать при НОВОМ входящем сообщении. НЕ двигает при сбое/невнятности.
    Возвращает True, если перевёл."""
    # Предохранители: вопросы реально задавались, вакансия активна, режим A/B, и карточка
    # на НАСТРАИВАЕМОМ исходном этапе (vacancy.auto_qa_stage, NULL→'response').
    if application.auto_qa_asked_at is None:
        return False
    vacancy = await session.get(Vacancy, application.vacancy_id)
    if not vacancy or not vacancy.auto_qa or vacancy.glafira_mode not in ("A", "B"):
        return False
    source_stage = vacancy.auto_qa_stage or "response"
    if application.stage != source_stage:
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
        # Резолвим API-ключ компании для LLM
        api_key = await get_company_openrouter_key(session, company_id)
        result = await call_json(system=_ANALYZE_SYSTEM, user=user_prompt, api_key=api_key, max_tokens=512)
        proceed = bool(result.get("proceed"))
        reason = str(result.get("reason") or "")[:500]
    except Exception as e:
        # Сбой LLM/парсинга → НЕ двигаем (не fake), оставляем рекрутёру
        logger.warning("[auto_qa] анализ ответов не удался app=%s: %s", application.id, e)
        return False

    if not proceed:
        logger.info("[auto_qa] ответы не подтвердили перевод app=%s: %s", application.id, reason)
        return False

    # Целевой этап П.2 — настраиваемый (vacancy.auto_qa_target_stage), та же валидация
    # что у автоскоринга: не защищённый / не терминальный / реальный этап вакансии.
    from .scoring import resolve_auto_target_stage
    target = await resolve_auto_target_stage(session, vacancy.id, vacancy.auto_qa_target_stage)
    if not target:
        logger.warning(
            "[auto_qa] нет валидного целевого этапа app=%s (auto_qa_target_stage=%r) — НЕ двигаем",
            application.id, vacancy.auto_qa_target_stage,
        )
        return False

    try:
        await move_application(
            session, application.id, MoveRequest(to_stage=target), company_id,
            actor_user_id=None, actor_type="ai",
        )
    except Exception as e:
        logger.warning("[auto_qa] перевод не удался app=%s: %s", application.id, e)
        return False

    await audit(
        session, action="auto_qa_advanced", entity_type="application", entity_id=application.id,
        after={"candidate_id": str(application.candidate_id), "vacancy_id": str(application.vacancy_id),
               "from_stage": source_stage, "to_stage": target, "reason": reason},
        actor_user_id=None, actor_type="ai", company_id=company_id,
    )
    await session.commit()
    logger.info("[auto_qa] кандидат переведён %s→%s app=%s: %s", source_stage, target, application.id, reason)
    return True


async def analyze_and_reject(session: AsyncSession, application: Application, company_id: UUID) -> bool:
    """П.3 — автоотказ при незаинтересованности. Вызывать при НОВОМ входящем сообщении.

    ⚠️ КРИТИЧНО (ложный отказ необратим — отшили хорошего кандидата + письмо):
    - Режим B (Автомат): при ЯВНОЙ незаинтересованности и высокой уверенности LLM → отказ
      (actor_type='ai', причина из справочника вакансии, решение LLM с цитатой в audit).
      Дальше существующий sync шлёт вежливый текст отказа в hh (П.4).
    - Режим A (Полуавтомат): НЕ отказываем — ставим флаг auto_reject_suggested_at + аудит-подсказку
      рекрутёру («Глафира предполагает незаинтересованность»).
    - Режим C: ничего.
    Возвращает True, если что-то сделал (отказал или подсказал) — чтобы П.2 не пытался двигать.
    """
    if application.stage in ("rejected", "hired"):
        return False
    vacancy = await session.get(Vacancy, application.vacancy_id)
    if not vacancy or not vacancy.auto_reject or vacancy.glafira_mode not in ("A", "B"):
        return False

    msgs = (await session.execute(
        select(Message)
        .where(Message.application_id == application.id)
        .order_by(Message.created_at)
    )).scalars().all()
    if not any(m.direction == "in" for m in msgs):
        return False

    dialog = "\n".join(
        f"{'Глафира/рекрутёр' if m.direction == 'out' else 'Кандидат'}: {m.body}" for m in msgs
    )
    reasons = await list_reject_reasons(session, company_id, side="candidate", vacancy_id=application.vacancy_id)
    reason_labels = [r.label for r in reasons]
    reasons_text = "; ".join(reason_labels) if reason_labels else "(список не настроен)"
    user_prompt = f"Доступные причины отказа (от кандидата): {reasons_text}\n\nПереписка:\n{dialog}"

    try:
        # Резолвим API-ключ компании для LLM
        api_key = await get_company_openrouter_key(session, company_id)
        result = await call_json(system=_REJECT_SYSTEM, user=user_prompt, api_key=api_key, max_tokens=512)
        disinterested = bool(result.get("disinterested"))
        confidence = float(result.get("confidence") or 0)
        reason = str(result.get("reason") or "").strip()[:120]
        quote = str(result.get("quote") or "").strip()[:300]
    except Exception as e:
        logger.warning("[auto_reject] анализ не удался app=%s: %s", application.id, e)
        return False

    # Предохранитель уверенности: при сомнении НЕ отказываем (оставляем рекрутёру)
    if not disinterested or confidence < _REJECT_CONFIDENCE_THRESHOLD:
        return False

    # Причина — ТОЛЬКО из справочника; если LLM не выбрал валидную → дефолт
    if reason not in reason_labels:
        reason = reason_labels[0] if reason_labels else "Кандидат не заинтересован в вакансии"

    now = datetime.now(timezone.utc)
    if vacancy.glafira_mode == "B":
        # ПОЛНЫЙ автоотказ (только режим Автомат)
        try:
            await reject_application(
                session, application.id, RejectRequest(reason=reason, side="candidate"),
                company_id, actor_user_id=None, actor_type="ai",
            )
        except Exception as e:
            logger.warning("[auto_reject] отказ не удался app=%s: %s", application.id, e)
            return False
        await audit(
            session, action="auto_reject", entity_type="application", entity_id=application.id,
            after={"candidate_id": str(application.candidate_id), "vacancy_id": str(application.vacancy_id),
                   "reason": reason, "confidence": confidence, "quote": quote},
            actor_user_id=None, actor_type="ai", company_id=company_id,
        )
        await session.commit()
        logger.info("[auto_reject] кандидат отклонён app=%s conf=%.2f причина=%s цитата=«%s»",
                    application.id, confidence, reason, quote)
        return True

    # Режим A — только подсказка рекрутёру, НЕ двигаем
    application.auto_reject_suggested_at = now
    await audit(
        session, action="auto_reject_suggested", entity_type="application", entity_id=application.id,
        after={"candidate_id": str(application.candidate_id), "vacancy_id": str(application.vacancy_id),
               "reason": reason, "confidence": confidence, "quote": quote},
        actor_user_id=None, actor_type="ai", company_id=company_id,
    )
    await session.commit()
    logger.info("[auto_reject] подсказка незаинтересованности (режим A, не двигаем) app=%s: %s",
                application.id, reason)
    return True
