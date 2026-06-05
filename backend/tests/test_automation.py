"""Тесты фичи автоматизации воронки (П.1 автоперевод по скорингу, П.4 текст отказа).

Фикстуры — реальные из conftest: db_session, admin_user (его company_id = тест-компания),
test_candidate. Мок LLM — через AsyncMock на call_json в namespace scoring.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, Vacancy, StageHistory, GlafiraSettings
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


async def _make_vacancy(db, company_id, **kw) -> Vacancy:
    vac = Vacancy(company_id=company_id, name="Авто-вакансия", **kw)
    db.add(vac)
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
