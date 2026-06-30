"""Тесты фичи автоматизации воронки (П.1 автоперевод по скорингу, П.4 текст отказа).

Фикстуры — реальные из conftest: db_session, admin_user (его company_id = тест-компания),
test_candidate. Мок LLM — через AsyncMock на call_json в namespace scoring.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, Vacancy, StageHistory, GlafiraSettings, VacancyStage
from app.schemas.application import MoveRequest
from app.schemas.vacancy import VacancyCreate, VacancyUpdate
from app.services.application import move_application
from app.services.vacancy import create_vacancy, update_vacancy, get_vacancy
from app.services.glafira.scoring import score_candidate
from app.services.integrations.hh.service import resolve_rejection_text, POLITE_REJECTION_TEXT


def _mock_score(score: int, verdict: str = "good") -> dict:
    return {
        "score": score, "verdict": verdict, "summary": "тест",
        "strengths": ["опыт"], "risks": [], "requirements_match": [],
        "forecast": "прогноз", "questions": [],
    }


# Реальная воронка (как сеет create_vacancy в проде). Нужна, чтобы валидация
# целевого этапа авто-перевода (resolve_auto_target_stage) находила 'selected' и др.
# непротекторные/нетерминальные этапы — иначе перевод не происходит (None → не двигаем).
_FUNNEL_STAGES = [
    ("response", "Отклик", False),
    ("added", "Добавлен", False),
    ("selected", "Отобран", False),
    ("recruiter", "Контакт с рекрутером", False),
    ("interview", "Интервью", False),
    ("offer", "Оффер", False),
    ("hired", "Нанят", True),
    ("rejected", "Отказ", True),
]


async def _make_vacancy(db, company_id, **kw) -> Vacancy:
    vac = Vacancy(company_id=company_id, name="Авто-вакансия", **kw)
    db.add(vac)
    await db.flush()
    for i, (key, label, term) in enumerate(_FUNNEL_STAGES):
        db.add(VacancyStage(
            company_id=company_id, vacancy_id=vac.id,
            stage_key=key, label=label, order_index=i, is_terminal=term,
        ))
    await db.flush()
    return vac


async def _make_application(db, company_id, candidate_id, vacancy_id, stage="response") -> Application:
    app = Application(
        company_id=company_id, candidate_id=candidate_id, vacancy_id=vacancy_id,
        stage=stage, created_at=datetime.now(timezone.utc),
    )
    db.add(app)
    await db.flush()
    return app


# ===== П.1 — автоперевод по скорингу =====

async def test_auto_move_by_score_advances_response_to_selected(
    db_session: AsyncSession, admin_user, test_candidate,
):
    """auto_move=True, threshold=80, mode='A', заявка 'response', score=85 → 'selected' (actor_type='ai')."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_move=True, auto_move_threshold=80, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)

    with patch("app.services.glafira.scoring.call_json", new_callable=AsyncMock) as m:
        m.return_value = _mock_score(85)
        await score_candidate(db_session, candidate_id=test_candidate.id, vacancy_id=vac.id,
                              company_id=cid, source="TEST")

    await db_session.refresh(app)
    assert app.stage == "selected"
    assert app.ai_score == 85

    hist = (await db_session.execute(
        select(StageHistory).where(
            StageHistory.application_id == app.id,
            StageHistory.to_stage == "selected",
        )
    )).scalar_one_or_none()
    assert hist is not None
    assert hist.actor_type == "ai"
    assert hist.actor_user_id is None


async def test_auto_move_custom_target_stage(db_session: AsyncSession, admin_user, test_candidate):
    """auto_move_stage='interview' (настраиваемый целевой этап) → перевод на 'interview', не 'selected'."""
    cid = admin_user.company_id
    vac = await _make_vacancy(
        db_session, cid, auto_move=True, auto_move_threshold=80,
        glafira_mode="A", auto_move_stage="interview",
    )
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)

    with patch("app.services.glafira.scoring.call_json", new_callable=AsyncMock) as m:
        m.return_value = _mock_score(90)
        await score_candidate(db_session, candidate_id=test_candidate.id, vacancy_id=vac.id,
                              company_id=cid, source="TEST")

    await db_session.refresh(app)
    assert app.stage == "interview"


async def test_auto_move_low_score_stays(db_session: AsyncSession, admin_user, test_candidate):
    """score=70 < threshold=80 → остаётся на 'response'."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_move=True, auto_move_threshold=80, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)

    with patch("app.services.glafira.scoring.call_json", new_callable=AsyncMock) as m:
        m.return_value = _mock_score(70, "partial")
        await score_candidate(db_session, candidate_id=test_candidate.id, vacancy_id=vac.id,
                              company_id=cid, source="TEST")

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_auto_move_mode_c_never_moves(db_session: AsyncSession, admin_user, test_candidate):
    """РЕЖИМ C (под контролем): даже при score=95 и auto_move=True — НЕ двигает."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_move=True, auto_move_threshold=80, glafira_mode="C")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)

    with patch("app.services.glafira.scoring.call_json", new_callable=AsyncMock) as m:
        m.return_value = _mock_score(95)
        await score_candidate(db_session, candidate_id=test_candidate.id, vacancy_id=vac.id,
                              company_id=cid, source="TEST")

    await db_session.refresh(app)
    assert app.stage == "response"  # режим C запрещает автоматику


async def test_auto_move_disabled_stays(db_session: AsyncSession, admin_user, test_candidate):
    """auto_move=False, score=95 → не двигает."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_move=False, auto_move_threshold=80, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)

    with patch("app.services.glafira.scoring.call_json", new_callable=AsyncMock) as m:
        m.return_value = _mock_score(95)
        await score_candidate(db_session, candidate_id=test_candidate.id, vacancy_id=vac.id,
                              company_id=cid, source="TEST")

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_move_application_ai_actor_type(db_session: AsyncSession, admin_user, test_candidate):
    """move_application(actor_type='ai', actor_user_id=None) → StageHistory.actor_type=='ai'."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid)
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)

    await move_application(db_session, app.id, MoveRequest(to_stage="selected"), cid,
                          actor_user_id=None, actor_type="ai")

    hist = (await db_session.execute(
        select(StageHistory).where(StageHistory.application_id == app.id, StageHistory.to_stage == "selected")
    )).scalar_one_or_none()
    assert hist is not None
    assert hist.actor_type == "ai"
    assert hist.actor_user_id is None


# ===== П.4 — настраиваемый текст отказа =====

async def test_resolve_rejection_text_vacancy_override_wins(db_session: AsyncSession, admin_user):
    """Приоритет: текст вакансии > дефолт компании > встроенный fallback."""
    cid = admin_user.company_id
    db_session.add(GlafiraSettings(company_id=cid, default_rejection_text="Дефолт компании"))
    vac = await _make_vacancy(db_session, cid, rejection_text="Текст вакансии")
    await db_session.flush()

    assert await resolve_rejection_text(db_session, cid, vac.id) == "Текст вакансии"


async def test_resolve_rejection_text_falls_back_to_company_default(db_session: AsyncSession, admin_user):
    """Нет текста вакансии → дефолт компании."""
    cid = admin_user.company_id
    db_session.add(GlafiraSettings(company_id=cid, default_rejection_text="Дефолт компании"))
    vac = await _make_vacancy(db_session, cid, rejection_text=None)
    await db_session.flush()

    assert await resolve_rejection_text(db_session, cid, vac.id) == "Дефолт компании"


async def test_resolve_rejection_text_builtin_fallback(db_session: AsyncSession, admin_user):
    """Нет ни текста вакансии, ни дефолта → встроенный POLITE_REJECTION_TEXT."""
    cid = admin_user.company_id
    db_session.add(GlafiraSettings(company_id=cid, default_rejection_text=None))
    vac = await _make_vacancy(db_session, cid, rejection_text=None)
    await db_session.flush()

    assert await resolve_rejection_text(db_session, cid, vac.id) == POLITE_REJECTION_TEXT


# ===== Персист автополей через сервис =====

async def test_vacancy_automation_fields_persist_create_update(db_session: AsyncSession, admin_user):
    """create_vacancy сохраняет автополя; update_vacancy их меняет; не-переданные не трогает."""
    cid = admin_user.company_id
    vac = await create_vacancy(
        db_session,
        VacancyCreate(name="Авто", auto_move=True, auto_move_threshold=75, auto_qa=True,
                      auto_reject=False, rejection_text="Кастом"),
        cid, admin_user.id,
    )
    assert vac.auto_move is True
    assert vac.auto_move_threshold == 75
    assert vac.auto_qa is True
    assert vac.auto_reject is False
    assert vac.rejection_text == "Кастом"

    await update_vacancy(
        db_session, vac.id,
        VacancyUpdate(auto_move=False, auto_move_threshold=90, rejection_text="Новый"),
        cid, admin_user.id,
    )
    fresh = await get_vacancy(db_session, vac.id, cid)
    assert fresh.auto_move is False
    assert fresh.auto_move_threshold == 90
    assert fresh.auto_qa is True  # не передавали — не изменилось
    assert fresh.rejection_text == "Новый"


# ===== П.2 — уточняющие вопросы (ask) + автоперевод на ответах (analyze) =====

from app.models import AiEvaluation, Message
from app.services.glafira.auto_qa import ask_auto_qa_questions, analyze_and_advance


async def _make_eval(db, company_id, candidate_id, application_id, questions):
    ev = AiEvaluation(
        company_id=company_id, candidate_id=candidate_id, application_id=application_id,
        score=60, verdict="partial", summary="тест", questions=questions,
        model="test", created_at=datetime.now(timezone.utc),
    )
    db.add(ev)
    await db.flush()
    return ev


async def _add_in_message(db, company_id, candidate_id, application_id, body):
    now = datetime.now(timezone.utc)
    db.add(Message(
        company_id=company_id, candidate_id=candidate_id, application_id=application_id,
        channel="hh", direction="in", sender_type="candidate", sender_user_id=None,
        body=body, sent_at=now, created_at=now,
    ))
    await db.flush()


async def test_auto_qa_asks_once_via_hh(db_session: AsyncSession, admin_user, test_candidate):
    """auto_qa=True, mode A, заявка 'response' с hh + вопросы из оценки → задаёт ОДИН раз в hh."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_qa=True, auto_move=False, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    app.hh_negotiation_id = "neg1"
    app.hh_chat_id = "chat1"
    await _make_eval(db_session, cid, test_candidate.id, app.id, ["Какой ваш опыт?", "Готовы к удалёнке?"])
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.get_valid_access_token", new_callable=AsyncMock) as tok, \
         patch("app.services.glafira.auto_qa.hh_client.send_chat_message", new_callable=AsyncMock) as send:
        tok.return_value = "token"
        send.return_value = {"id": "m1"}
        await ask_auto_qa_questions(db_session, cid)
        await db_session.refresh(app)
        assert app.auto_qa_asked_at is not None
        assert send.await_count == 1  # отправлено один раз

        # Исходящее AI-сообщение записано
        out = (await db_session.execute(
            select(Message).where(Message.application_id == app.id, Message.direction == "out")
        )).scalar_one_or_none()
        assert out is not None and out.sender_type == "ai"

        # Повторный проход — уже задано, не дёргаем кандидата снова
        await ask_auto_qa_questions(db_session, cid)
        assert send.await_count == 1


async def test_auto_qa_mode_c_not_asked(db_session: AsyncSession, admin_user, test_candidate):
    """Режим C — вопросы не задаются."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_qa=True, auto_move=False, glafira_mode="C")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    app.hh_negotiation_id = "neg1"
    app.hh_chat_id = "chat1"
    await _make_eval(db_session, cid, test_candidate.id, app.id, ["Q?"])
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.get_valid_access_token", new_callable=AsyncMock) as tok, \
         patch("app.services.glafira.auto_qa.hh_client.send_chat_message", new_callable=AsyncMock) as send:
        tok.return_value = "token"
        await ask_auto_qa_questions(db_session, cid)
        await db_session.refresh(app)
        assert app.auto_qa_asked_at is None
        assert send.await_count == 0


async def test_auto_qa_no_questions_skipped(db_session: AsyncSession, admin_user, test_candidate):
    """Нет оценки/вопросов → не задаём (не шлём пустое), asked_at остаётся None."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_qa=True, auto_move=False, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    app.hh_negotiation_id = "neg1"
    app.hh_chat_id = "chat1"
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.get_valid_access_token", new_callable=AsyncMock) as tok, \
         patch("app.services.glafira.auto_qa.hh_client.send_chat_message", new_callable=AsyncMock) as send:
        tok.return_value = "token"
        await ask_auto_qa_questions(db_session, cid)
        await db_session.refresh(app)
        assert app.auto_qa_asked_at is None
        assert send.await_count == 0


async def test_auto_qa_analyze_proceeds_moves_to_selected(db_session: AsyncSession, admin_user, test_candidate):
    """Ответ есть, LLM proceed=true → перевод Отклик→Отобран (actor_type='ai')."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_qa=True, auto_move=False, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    app.auto_qa_asked_at = datetime.now(timezone.utc)
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "Опыт 5 лет, к удалёнке готов")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        cj.return_value = {"proceed": True, "reason": "содержательные ответы"}
        moved = await analyze_and_advance(db_session, app, cid)
        assert moved is True

    await db_session.refresh(app)
    assert app.stage == "selected"
    hist = (await db_session.execute(
        select(StageHistory).where(StageHistory.application_id == app.id, StageHistory.to_stage == "selected")
    )).scalar_one_or_none()
    assert hist is not None and hist.actor_type == "ai"


async def test_auto_qa_analyze_declines_no_move(db_session: AsyncSession, admin_user, test_candidate):
    """LLM proceed=false → НЕ двигаем (оставляем рекрутёру)."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_qa=True, auto_move=False, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    app.auto_qa_asked_at = datetime.now(timezone.utc)
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "не знаю")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        cj.return_value = {"proceed": False, "reason": "уклончиво"}
        moved = await analyze_and_advance(db_session, app, cid)
        assert moved is False

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_auto_qa_analyze_no_incoming_no_move(db_session: AsyncSession, admin_user, test_candidate):
    """Кандидат не ответил → анализ не запускается, не двигаем."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_qa=True, auto_move=False, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    app.auto_qa_asked_at = datetime.now(timezone.utc)
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        moved = await analyze_and_advance(db_session, app, cid)
        assert moved is False
        assert cj.await_count == 0  # LLM не дёргали

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_auto_qa_analyze_mode_c_no_move(db_session: AsyncSession, admin_user, test_candidate):
    """Режим C → анализ/перевод не выполняется даже при ответе."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_qa=True, auto_move=False, glafira_mode="C")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    app.auto_qa_asked_at = datetime.now(timezone.utc)
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "ответ")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        moved = await analyze_and_advance(db_session, app, cid)
        assert moved is False
        assert cj.await_count == 0

    await db_session.refresh(app)
    assert app.stage == "response"


# ===== П.3 — автоотказ при незаинтересованности =====

from app.models import RejectReason
from app.services.glafira.auto_qa import analyze_and_reject


async def _make_reject_reason(db, company_id, vacancy_id, label, side="candidate", order_index=0):
    rr = RejectReason(
        company_id=company_id, vacancy_id=vacancy_id, side=side,
        label=label, order_index=order_index, is_active=True, is_system=False,
    )
    db.add(rr)
    await db.flush()
    return rr


async def test_auto_reject_mode_b_rejects(db_session: AsyncSession, admin_user, test_candidate):
    """Режим B (Автомат), auto_reject=True, ответ есть, LLM disinterested=true conf=0.9 →
    заявка 'rejected' (side='candidate'), StageHistory actor_type='ai', причина из справочника."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=True, glafira_mode="B")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await _make_reject_reason(db_session, cid, vac.id, "Принял другой оффер")
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "Спасибо, уже принял другой оффер")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        cj.return_value = {"disinterested": True, "confidence": 0.9,
                           "reason": "Принял другой оффер", "quote": "уже принял другой оффер"}
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is True

    await db_session.refresh(app)
    assert app.stage == "rejected"
    assert app.reject_side == "candidate"
    assert app.reject_reason == "Принял другой оффер"
    hist = (await db_session.execute(
        select(StageHistory).where(StageHistory.application_id == app.id, StageHistory.to_stage == "rejected")
    )).scalar_one_or_none()
    assert hist is not None and hist.actor_type == "ai" and hist.actor_user_id is None


async def test_auto_reject_mode_a_suggests_not_moves(db_session: AsyncSession, admin_user, test_candidate):
    """Режим A (Полуавтомат) — НЕ отказываем, только подсказка (auto_reject_suggested_at), stage остаётся."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=True, glafira_mode="A")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await _make_reject_reason(db_session, cid, vac.id, "Не интересна вакансия")
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "Передумал, не интересно")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        cj.return_value = {"disinterested": True, "confidence": 0.95,
                           "reason": "Не интересна вакансия", "quote": "не интересно"}
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is True

    await db_session.refresh(app)
    assert app.stage == "response"  # НЕ двигаем в режиме A
    assert app.auto_reject_suggested_at is not None


async def test_auto_reject_mode_c_nothing(db_session: AsyncSession, admin_user, test_candidate):
    """Режим C — ничего, LLM даже не дёргаем."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=True, glafira_mode="C")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "не интересно")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is False
        assert cj.await_count == 0

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_auto_reject_disabled_nothing(db_session: AsyncSession, admin_user, test_candidate):
    """auto_reject=False — ничего, LLM не дёргаем."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=False, glafira_mode="B")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "не интересно")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is False
        assert cj.await_count == 0

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_auto_reject_low_confidence_nothing(db_session: AsyncSession, admin_user, test_candidate):
    """Низкая уверенность (<0.85) — НЕ отказываем (предохранитель), stage остаётся."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=True, glafira_mode="B")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await _make_reject_reason(db_session, cid, vac.id, "Не интересна вакансия")
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "хм, надо подумать")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        cj.return_value = {"disinterested": True, "confidence": 0.6,
                           "reason": "Не интересна вакансия", "quote": "надо подумать"}
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is False

    await db_session.refresh(app)
    assert app.stage == "response"
    assert app.auto_reject_suggested_at is None


async def test_auto_reject_not_disinterested_nothing(db_session: AsyncSession, admin_user, test_candidate):
    """LLM disinterested=false — ничего (деловой диалог)."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=True, glafira_mode="B")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "Да, интересно, когда собеседование?")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        cj.return_value = {"disinterested": False, "confidence": 0.9, "reason": "", "quote": ""}
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is False

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_auto_reject_no_incoming_nothing(db_session: AsyncSession, admin_user, test_candidate):
    """Нет входящего ответа кандидата — анализ не запускается."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=True, glafira_mode="B")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is False
        assert cj.await_count == 0

    await db_session.refresh(app)
    assert app.stage == "response"


async def test_auto_reject_invalid_reason_falls_back(db_session: AsyncSession, admin_user, test_candidate):
    """LLM вернул причину не из справочника → берём первую из справочника (не сырой текст LLM)."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject=True, glafira_mode="B")
    app = await _make_application(db_session, cid, test_candidate.id, vac.id)
    await _make_reject_reason(db_session, cid, vac.id, "Принял другой оффер", order_index=0)
    await _add_in_message(db_session, cid, test_candidate.id, app.id, "уже не ищу работу")
    await db_session.flush()

    with patch("app.services.glafira.auto_qa.call_json", new_callable=AsyncMock) as cj:
        cj.return_value = {"disinterested": True, "confidence": 0.92,
                           "reason": "Выдуманная причина", "quote": "не ищу работу"}
        acted = await analyze_and_reject(db_session, app, cid)
        assert acted is True

    await db_session.refresh(app)
    assert app.stage == "rejected"
    assert app.reject_reason == "Принял другой оффер"  # фолбэк на справочник


# ===== П.4-чекбокс — авто-сообщение при отказе (gate auto_reject_message) =====

from app.services.integrations.hh.service import sync_company_rejections


async def _make_rejected_hh_app(db, company_id, candidate_id, vacancy_id):
    app = await _make_application(db, company_id, candidate_id, vacancy_id, stage="rejected")
    app.hh_negotiation_id = "neg-rej-1"
    app.hh_chat_id = "chat-rej-1"
    app.reject_reason = "Не подходит опыт"
    app.reject_side = "company"
    await db.flush()
    return app


async def test_reject_message_gate_on_sends(db_session: AsyncSession, admin_user, test_candidate):
    """auto_reject_message=True → discard + вежливое сообщение РЕАЛЬНО отправляется в hh, Message сохранён."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject_message=True)
    app = await _make_rejected_hh_app(db_session, cid, test_candidate.id, vac.id)

    with patch("app.services.integrations.hh.service.get_valid_access_token", new_callable=AsyncMock) as tok, \
         patch("app.services.integrations.hh.service.hh_client.discard_negotiation", new_callable=AsyncMock) as disc, \
         patch("app.services.integrations.hh.service.hh_client.send_chat_message", new_callable=AsyncMock) as send:
        tok.return_value = "token"
        disc.return_value = True
        send.return_value = {"id": "m1"}
        stats = await sync_company_rejections(db_session, cid, limit=10)
        assert stats["discarded"] == 1
        send.assert_called_once()  # сообщение отправлено

    await db_session.refresh(app)
    assert app.hh_discard_synced_at is not None
    msg = (await db_session.execute(
        select(Message).where(Message.application_id == app.id, Message.direction == "out", Message.channel == "hh")
    )).scalar_one_or_none()
    assert msg is not None and msg.sender_type == "ai"


async def test_reject_message_gate_off_no_send(db_session: AsyncSession, admin_user, test_candidate):
    """auto_reject_message=False → discard на hh ВСЁ РАВНО идёт, но сообщение НЕ шлём и Message не создаём."""
    cid = admin_user.company_id
    vac = await _make_vacancy(db_session, cid, auto_reject_message=False)
    app = await _make_rejected_hh_app(db_session, cid, test_candidate.id, vac.id)

    with patch("app.services.integrations.hh.service.get_valid_access_token", new_callable=AsyncMock) as tok, \
         patch("app.services.integrations.hh.service.hh_client.discard_negotiation", new_callable=AsyncMock) as disc, \
         patch("app.services.integrations.hh.service.hh_client.send_chat_message", new_callable=AsyncMock) as send:
        tok.return_value = "token"
        disc.return_value = True
        send.return_value = {"id": "m1"}
        stats = await sync_company_rejections(db_session, cid, limit=10)
        assert stats["discarded"] == 1   # discard прошёл независимо от флага
        send.assert_not_called()         # но письмо НЕ отправлено

    await db_session.refresh(app)
    assert app.hh_discard_synced_at is not None
    msg = (await db_session.execute(
        select(Message).where(Message.application_id == app.id, Message.direction == "out", Message.channel == "hh")
    )).scalar_one_or_none()
    assert msg is None  # сообщение не создано
