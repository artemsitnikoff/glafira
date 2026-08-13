"""Тесты переоценки AI-скорингом (две связанные фичи):

1. TestForceReevaluateSingle — одиночная переоценка через POST /glafira/score с
   force=True ТЕПЕРЬ реально перезаписывает балл (раньше упиралась в partial-unique
   (candidate_id, application_id) и молча возвращала СТАРУЮ оценку).

2. TestVacancyReevaluate — массовая переоценка вакансии POST /vacancies/{id}/reevaluate:
   снимает оценки со ВСЕХ нетерминальных заявок (удаляет AiEvaluation, обнуляет
   ai_score/ai_score_attempts) → фоновый крон score_pending переоценит по актуальному
   промту. Терминальные («Отказ»/«Нанят») не трогает; candidate.ai_score (пул-кэш) не
   обнуляет; RBAC admin/recruiter; только active/paused вакансия; company-scoped.

Все LLM-вызовы мокаются (offline). Дискриминирующие проверки: значения меняются от
реального состояния БД, а не от константы.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models import (
    AiEvaluation,
    Application,
    AuditLog,
    Candidate,
    Event,
    User,
    Vacancy,
)

pytestmark = pytest.mark.asyncio


async def _create_vacancy(
    client: AsyncClient, headers: dict, *, name: str, client_id: str
) -> dict:
    resp = await client.post(
        "/api/v1/vacancies",
        headers=headers,
        json={"name": name, "city": "Москва", "description": "Описание", "client_id": client_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _make_app_with_eval(
    db: AsyncSession, *, company_id, vacancy_id, stage: str, score: int
) -> tuple[Candidate, Application, AiEvaluation]:
    """Кандидат + заявка (ai_score/attempts заданы) + существующая AiEvaluation."""
    candidate = Candidate(
        company_id=company_id,
        last_name="Кандидатов",
        first_name="Тест",
        source="manual",
        ai_score=score,
    )
    db.add(candidate)
    await db.flush()

    application = Application(
        company_id=company_id,
        candidate_id=candidate.id,
        vacancy_id=vacancy_id,
        stage=stage,
        ai_score=score,
        ai_score_attempts=2,
    )
    db.add(application)
    await db.flush()

    evaluation = AiEvaluation(
        company_id=company_id,
        candidate_id=candidate.id,
        application_id=application.id,
        score=score,
        verdict="good",
        summary="прежняя оценка",
    )
    db.add(evaluation)
    await db.flush()
    return candidate, application, evaluation


# ===========================================================================
# ЗАДАЧА 1 — force реально перезаписывает оценку
# ===========================================================================


class TestForceReevaluateSingle:

    async def test_force_reevaluate_overwrites_score(
        self, async_client, auth_headers, test_candidate, db_session, default_client
    ):
        """force=True удаляет старую оценку и создаёт новую: балл перезаписан,
        candidate/application.ai_score обновлены, Event+audit записаны, дублей нет."""
        vac = await _create_vacancy(
            async_client, auth_headers, name="Python Developer", client_id=default_client
        )
        vacancy_id = vac["id"]

        application = Application(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy_id,
            stage="response",
        )
        db_session.add(application)
        await db_session.commit()
        app_id = application.id

        first = {
            "score": 78,
            "verdict": "good",
            "summary": "Первичная оценка",
            "strengths": ["Python"],
            "risks": [],
            "requirements_match": [],
            "forecast": "2 недели",
            "questions": [],
        }
        with patch(
            "app.services.glafira.scoring.call_json", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = first
            r1 = await async_client.post(
                "/api/v1/glafira/score",
                headers=auth_headers,
                json={"candidate_id": str(test_candidate.id), "vacancy_id": vacancy_id},
            )
            assert r1.status_code == 201, r1.text
            assert r1.json()["score"] == 78

        # Без force повторный вызов возвращает СТАРУЮ оценку (200) и НЕ трогает LLM.
        with patch(
            "app.services.glafira.scoring.call_json", new_callable=AsyncMock
        ) as mock_noforce:
            mock_noforce.return_value = {**first, "score": 1}
            r_noforce = await async_client.post(
                "/api/v1/glafira/score",
                headers=auth_headers,
                json={"candidate_id": str(test_candidate.id), "vacancy_id": vacancy_id},
            )
            assert r_noforce.status_code == 200, r_noforce.text
            assert r_noforce.json()["score"] == 78  # прежняя, не 1
            mock_noforce.assert_not_awaited()  # платного вызова LLM не было

        second = {
            "score": 42,
            "verdict": "bad",
            "summary": "Переоценка ниже",
            "strengths": [],
            "risks": ["мало опыта"],
            "requirements_match": [
                {"criterion": "Python", "weight": 50, "points": 10, "comment": "слабо"}
            ],
            "forecast": "под вопросом",
            "questions": ["Опыт с async?"],
        }
        with patch(
            "app.services.glafira.scoring.call_json", new_callable=AsyncMock
        ) as mock_force:
            mock_force.return_value = second
            r2 = await async_client.post(
                "/api/v1/glafira/score",
                headers=auth_headers,
                json={
                    "candidate_id": str(test_candidate.id),
                    "vacancy_id": vacancy_id,
                    "force": True,
                },
            )
            assert r2.status_code == 201, r2.text  # НОВАЯ оценка создана
            assert r2.json()["score"] == 42
            mock_force.assert_awaited()  # LLM реально вызвана

        # Ровно ОДНА оценка (старая удалена, новая на её месте), балл 42.
        eval_rows = (
            await db_session.execute(
                select(AiEvaluation).where(
                    AiEvaluation.candidate_id == test_candidate.id
                )
            )
        ).scalars().all()
        assert len(eval_rows) == 1
        assert eval_rows[0].score == 42

        # candidate.ai_score + application.ai_score перезаписаны (fresh column-select).
        cand_score = (
            await db_session.execute(
                select(Candidate.ai_score).where(Candidate.id == test_candidate.id)
            )
        ).scalar_one()
        assert cand_score == 42
        app_score = (
            await db_session.execute(
                select(Application.ai_score).where(Application.id == app_id)
            )
        ).scalar_one()
        assert app_score == 42

        # Event + audit записаны для ОБЕИХ оценок (первичной и переоценки).
        score_events = (
            await db_session.execute(
                select(Event).where(
                    Event.type == "score", Event.candidate_id == test_candidate.id
                )
            )
        ).scalars().all()
        assert len(score_events) == 2

        audits = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "glafira_score",
                    AuditLog.company_id == test_candidate.company_id,
                )
            )
        ).scalars().all()
        assert len(audits) == 2


# ===========================================================================
# ЗАДАЧА 2 — массовая переоценка вакансии
# ===========================================================================


class TestVacancyReevaluate:

    async def test_reevaluate_clears_nonterminal_keeps_terminal(
        self, async_client, auth_headers, admin_user, db_session, default_client
    ):
        """Нетерминальные заявки: оценка удалена + ai_score=NULL + attempts=0.
        Терминальные (rejected/hired) — НЕ тронуты. candidate.ai_score НЕ обнулён.
        Возвращает queued=N; audit записан."""
        company_id = admin_user.company_id
        vac = await _create_vacancy(
            async_client, auth_headers, name="Аналитик", client_id=default_client
        )
        vac_id = vac["id"]

        cand_i, app_i, ev_i = await _make_app_with_eval(
            db_session, company_id=company_id, vacancy_id=vac_id, stage="interview", score=80
        )
        cand_r, app_r, ev_r = await _make_app_with_eval(
            db_session, company_id=company_id, vacancy_id=vac_id, stage="response", score=55
        )
        cand_rej, app_rej, ev_rej = await _make_app_with_eval(
            db_session, company_id=company_id, vacancy_id=vac_id, stage="rejected", score=30
        )
        cand_h, app_h, ev_h = await _make_app_with_eval(
            db_session, company_id=company_id, vacancy_id=vac_id, stage="hired", score=90
        )
        await db_session.commit()

        # Захватываем id ДО мутации — после DELETE обращение к ev.id вызвало бы reload.
        ev_i_id, ev_r_id, ev_rej_id, ev_h_id = ev_i.id, ev_r.id, ev_rej.id, ev_h.id
        app_i_id, app_r_id, app_rej_id, app_h_id = app_i.id, app_r.id, app_rej.id, app_h.id
        cand_i_id, cand_r_id = cand_i.id, cand_r.id

        resp = await async_client.post(
            f"/api/v1/vacancies/{vac_id}/reevaluate", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["queued"] == 2  # interview + response

        remaining_eval_ids = set(
            (
                await db_session.execute(
                    select(AiEvaluation.id).where(
                        AiEvaluation.id.in_([ev_i_id, ev_r_id, ev_rej_id, ev_h_id])
                    )
                )
            ).scalars().all()
        )
        assert ev_i_id not in remaining_eval_ids, "оценка interview удалена"
        assert ev_r_id not in remaining_eval_ids, "оценка response удалена"
        assert ev_rej_id in remaining_eval_ids, "оценка rejected сохранена"
        assert ev_h_id in remaining_eval_ids, "оценка hired сохранена"

        # Нетерминальные заявки обнулены.
        for app_id in (app_i_id, app_r_id):
            row = (
                await db_session.execute(
                    select(Application.ai_score, Application.ai_score_attempts).where(
                        Application.id == app_id
                    )
                )
            ).one()
            assert row.ai_score is None
            assert row.ai_score_attempts == 0

        # Терминальные заявки — как были.
        rej_row = (
            await db_session.execute(
                select(Application.ai_score, Application.ai_score_attempts).where(
                    Application.id == app_rej_id
                )
            )
        ).one()
        assert rej_row.ai_score == 30
        assert rej_row.ai_score_attempts == 2
        h_score = (
            await db_session.execute(
                select(Application.ai_score).where(Application.id == app_h_id)
            )
        ).scalar_one()
        assert h_score == 90

        # candidate.ai_score (пул-кэш) НЕ тронут даже у нетерминальных.
        for cand_id, expected in ((cand_i_id, 80), (cand_r_id, 55)):
            c_score = (
                await db_session.execute(
                    select(Candidate.ai_score).where(Candidate.id == cand_id)
                )
            ).scalar_one()
            assert c_score == expected

        # Audit записан.
        audits = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "vacancy_reevaluate",
                    AuditLog.company_id == company_id,
                )
            )
        ).scalars().all()
        assert len(audits) == 1
        assert audits[0].changes["after"]["queued"] == 2
        assert str(audits[0].entity_id) == vac_id

    async def test_reevaluate_manager_forbidden(
        self, async_client, auth_headers, manager_headers, default_client
    ):
        """Менеджер не может переоценивать (зеркало /glafira/score) → 403."""
        vac = await _create_vacancy(
            async_client, auth_headers, name="Закрыта для менеджера", client_id=default_client
        )
        resp = await async_client.post(
            f"/api/v1/vacancies/{vac['id']}/reevaluate", headers=manager_headers
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_reevaluate_hiring_manager_forbidden(
        self, async_client, auth_headers, admin_user, db_session, default_client
    ):
        """hiring_manager отбит deny-by-default на роутере вакансий → 403."""
        vac = await _create_vacancy(
            async_client, auth_headers, name="Закрыта для НМ", client_id=default_client
        )
        hm = User(
            company_id=admin_user.company_id,
            email="hm.reeval@example.com",
            password_hash=get_password_hash("Glafira2026!"),
            full_name="Нанимающий Менеджер",
            role="hiring_manager",
            is_active=True,
        )
        db_session.add(hm)
        await db_session.commit()

        login = await async_client.post(
            "/api/v1/auth/login",
            json={"email": hm.email, "password": "Glafira2026!"},
        )
        assert login.status_code == 200, login.text
        hm_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = await async_client.post(
            f"/api/v1/vacancies/{vac['id']}/reevaluate", headers=hm_headers
        )
        assert resp.status_code == 403, resp.text

    async def test_reevaluate_archived_vacancy_400(
        self, async_client, auth_headers, db_session, default_client
    ):
        """Архивную вакансию переоценивать нельзя (крон её не скорит) → 400."""
        vac = await _create_vacancy(
            async_client, auth_headers, name="В архив", client_id=default_client
        )
        vac_obj = await db_session.get(Vacancy, uuid.UUID(vac["id"]))
        vac_obj.status = "archived"
        await db_session.commit()

        resp = await async_client.post(
            f"/api/v1/vacancies/{vac['id']}/reevaluate", headers=auth_headers
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_reevaluate_other_company_404(
        self, async_client, auth_headers, second_company, db_session
    ):
        """Вакансия чужой компании → 404 (company-scoped через get_vacancy)."""
        other_vac = Vacancy(
            company_id=second_company.id, name="Чужая вакансия", status="active"
        )
        db_session.add(other_vac)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/v1/vacancies/{other_vac.id}/reevaluate", headers=auth_headers
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_reevaluate_no_applications_returns_zero(
        self, async_client, auth_headers, default_client
    ):
        """Вакансия без заявок → queued=0, без падения."""
        vac = await _create_vacancy(
            async_client, auth_headers, name="Без заявок", client_id=default_client
        )
        resp = await async_client.post(
            f"/api/v1/vacancies/{vac['id']}/reevaluate", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["queued"] == 0
