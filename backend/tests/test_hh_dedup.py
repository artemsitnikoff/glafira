"""Тесты дедупликации кандидата при импорте отклика hh (import_response).

Фикс главной причины «дублей кандидатов»: раньше каждый новый hh-отклик, не найденный
по hh_negotiation_id, создавал НОВОГО Candidate. Теперь — 3-уровневый дедуп (resume_id →
phone/email → новый), и «одна строка на вакансию» (второй отклик того же человека на ту же
вакансию не плодит вторую заявку и не двигает этап).

import_response вызываем БЕЗ access_token — тогда полное резюме не догружается (данные берём
прямо из item['resume']), а save_hh_resume_document/сеть не дёргаются. Так же устроены
существующие TestHhService в test_hh_polling.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import select, func

from app.services.integrations.hh import service as hh_service
from app.models import Vacancy, Application, Candidate, CandidateExperience


def _cell(formatted: str) -> dict:
    return {"type": {"id": "cell"}, "value": {"formatted": formatted}}


async def _count_candidates(db_session, company_id) -> int:
    return (await db_session.execute(
        select(func.count()).select_from(Candidate).where(Candidate.company_id == company_id)
    )).scalar_one()


class TestImportResponseDedup:
    """3-уровневый дедуп кандидата + «одна строка на вакансию»."""

    async def test_reuse_by_phone_other_vacancy_creates_app_no_new_candidate(
        self, db_session, test_company, admin_user
    ):
        """(1) Тот же человек (тот же телефон), новый nid, ДРУГАЯ вакансия →
        кандидат переиспользован (число Candidate не выросло), создана новая Application."""
        cand = Candidate(
            company_id=test_company.id, last_name="Иванов", first_name="Иван",
            source="manual", phone="+79001112233",
        )
        v2 = Vacancy(company_id=test_company.id, name="Вакансия 2", status="active")
        db_session.add_all([cand, v2])
        await db_session.flush()

        before = await _count_candidates(db_session, test_company.id)

        item = {
            "id": "nid_diffvac",
            "resume": {
                "first_name": "Иван", "last_name": "Иванов",
                "contact": [_cell("+7 900 111 22 33")],
            },
        }
        result = await hh_service.import_response(db_session, test_company.id, v2, item)
        assert result == "created"

        after = await _count_candidates(db_session, test_company.id)
        assert after == before  # новый кандидат НЕ создан — переиспользован по телефону

        app = (await db_session.execute(
            select(Application).where(Application.hh_negotiation_id == "nid_diffvac")
        )).scalar_one()
        assert app.vacancy_id == v2.id
        assert app.candidate_id == cand.id

    async def test_reuse_same_vacancy_new_nid_no_second_app_stage_untouched(
        self, db_session, test_company, admin_user
    ):
        """(2) Тот же человек, ТА ЖЕ вакансия, новый nid → новой Application НЕТ,
        этап существующей заявки НЕ изменился, nid записан в extra['hh_seen_nids']."""
        cand = Candidate(
            company_id=test_company.id, last_name="Петров", first_name="Пётр",
            source="manual", phone="+79002223344",
        )
        v1 = Vacancy(company_id=test_company.id, name="Вакансия 1", status="active")
        db_session.add_all([cand, v1])
        await db_session.flush()

        app1 = Application(
            company_id=test_company.id, candidate_id=cand.id, vacancy_id=v1.id,
            stage="interview", hh_negotiation_id="nid_first",
        )
        db_session.add(app1)
        await db_session.flush()

        item = {
            "id": "nid_second",
            "resume": {
                "first_name": "Пётр", "last_name": "Петров",
                "contact": [_cell("+7 900 222 33 44")],
            },
        }
        result = await hh_service.import_response(db_session, test_company.id, v1, item)
        assert result == "updated"

        apps = (await db_session.execute(
            select(Application).where(
                Application.candidate_id == cand.id,
                Application.vacancy_id == v1.id,
            )
        )).scalars().all()
        assert len(apps) == 1  # вторая заявка НЕ создана
        assert apps[0].id == app1.id
        assert apps[0].stage == "interview"           # этап не тронут
        assert apps[0].hh_negotiation_id == "nid_first"  # negotiation не перезаписан

        await db_session.refresh(cand)
        assert "nid_second" in (cand.extra or {}).get("hh_seen_nids", [])

    async def test_reuse_by_resume_id(self, db_session, test_company, admin_user):
        """(3) Дедуп по resume_id (external_id) → переиспользование, новый кандидат не создаётся."""
        cand = Candidate(
            company_id=test_company.id, last_name="Сидоров", first_name="Сидор",
            source="hh", external_source="hh", external_id="resume_777",
        )
        v1 = Vacancy(company_id=test_company.id, name="Вакансия 1", status="active")
        db_session.add_all([cand, v1])
        await db_session.flush()

        before = await _count_candidates(db_session, test_company.id)

        item = {
            "id": "nid_r3",
            "resume": {"id": "resume_777", "first_name": "Сидор", "last_name": "Сидоров"},
        }
        result = await hh_service.import_response(db_session, test_company.id, v1, item)
        assert result == "created"

        after = await _count_candidates(db_session, test_company.id)
        assert after == before  # переиспользован по resume_id

        app = (await db_session.execute(
            select(Application).where(Application.hh_negotiation_id == "nid_r3")
        )).scalar_one()
        assert app.candidate_id == cand.id

    async def test_reuse_non_hh_preserves_source_and_experience(
        self, db_session, test_company, admin_user
    ):
        """(4) Дедуп по телефону кандидата НЕ-hh (talantix, с опытом) → переиспользован,
        source остался 'talantix', строки CandidateExperience НЕ удалены (секции не трогаем)."""
        cand = Candidate(
            company_id=test_company.id, last_name="Талантов", first_name="Тал",
            source="talantix", external_source="talantix", external_id="tx_1",
            phone="+79003334455",
        )
        db_session.add(cand)
        await db_session.flush()

        exp = CandidateExperience(
            company_id=test_company.id, candidate_id=cand.id,
            position="Ведущий инженер", company="Талантикс ООО",
            period="2018 — 2021", order_index=0,
        )
        v1 = Vacancy(company_id=test_company.id, name="Вакансия 1", status="active")
        db_session.add_all([exp, v1])
        await db_session.flush()

        item = {
            "id": "nid_tx",
            "resume": {
                "first_name": "Тал", "last_name": "Талантов",
                "contact": [_cell("+7 900 333 44 55")],
                # у отклика hh СВОЙ опыт — он НЕ должен затереть talantix-опыт
                "experience": [{"position": "hh должность", "company": "HH Corp", "start": "2022-01-01"}],
            },
        }
        result = await hh_service.import_response(db_session, test_company.id, v1, item)
        assert result == "created"

        await db_session.refresh(cand)
        assert cand.source == "talantix"           # источник НЕ перезаписан на hh
        assert cand.external_source == "talantix"

        exps = (await db_session.execute(
            select(CandidateExperience).where(CandidateExperience.candidate_id == cand.id)
        )).scalars().all()
        assert len(exps) == 1                      # hh-опыт не добавлен, talantix-опыт цел
        assert exps[0].company == "Талантикс ООО"

    async def test_new_person_creates_candidate_and_app(
        self, db_session, test_company, admin_user
    ):
        """(5) Новый человек → создаётся candidate+app (поведение не изменилось)."""
        v1 = Vacancy(company_id=test_company.id, name="Вакансия 1", status="active")
        db_session.add(v1)
        await db_session.flush()

        before = await _count_candidates(db_session, test_company.id)

        item = {
            "id": "nid_new5",
            "resume": {
                "id": "resume_new5", "first_name": "Новый", "last_name": "Человек",
                "contact": [_cell("+7 900 999 88 77")],
            },
        }
        result = await hh_service.import_response(db_session, test_company.id, v1, item)
        assert result == "created"

        after = await _count_candidates(db_session, test_company.id)
        assert after == before + 1                 # новый кандидат создан

        app = (await db_session.execute(
            select(Application).where(Application.hh_negotiation_id == "nid_new5")
        )).scalar_one()
        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand.source == "hh"
        assert cand.external_id == "resume_new5"
        assert cand.first_name == "Новый"

    async def test_repoll_same_nid_recreates_sections(
        self, db_session, test_company, admin_user
    ):
        """(6) Re-poll того же nid → кандидат обновлён, секции пересозданы (delete+add),
        поведение не изменилось."""
        cand = Candidate(
            company_id=test_company.id, last_name="Реполлов", first_name="Ре",
            source="hh", external_source="hh", external_id="resume_rp",
        )
        v1 = Vacancy(company_id=test_company.id, name="Вакансия 1", status="active")
        db_session.add_all([cand, v1])
        await db_session.flush()

        old = CandidateExperience(
            company_id=test_company.id, candidate_id=cand.id,
            position="Старая должность", company="OldCo", order_index=0,
        )
        app1 = Application(
            company_id=test_company.id, candidate_id=cand.id, vacancy_id=v1.id,
            stage="response", hh_negotiation_id="nid_rp",
        )
        db_session.add_all([old, app1])
        await db_session.flush()

        item = {
            "id": "nid_rp",  # тот же nid → re-poll
            "resume": {
                "first_name": "Ре", "last_name": "Реполлов",
                "experience": [
                    {"position": "Новая должность", "company": "NewCo",
                     "start": "2020-01-01", "end": "2022-01-01"},
                ],
            },
        }
        result = await hh_service.import_response(db_session, test_company.id, v1, item)
        assert result == "updated"

        exps = (await db_session.execute(
            select(CandidateExperience).where(CandidateExperience.candidate_id == cand.id)
        )).scalars().all()
        assert len(exps) == 1                      # старый опыт удалён
        assert exps[0].company == "NewCo"          # новый из свежего резюме создан

    async def test_poll_skips_seen_nids(self, db_session, test_company, admin_user):
        """(7) poll_responses_now пропускает nid из candidate.extra['hh_seen_nids'] —
        import_response для них НЕ вызывается (резюме не фетчится)."""
        v1 = Vacancy(
            company_id=test_company.id, name="Вакансия 1", status="active",
            hh_vacancy_id="hh_vac_1",
        )
        cand = Candidate(
            company_id=test_company.id, last_name="Сеен", first_name="Нид",
            source="hh", extra={"hh_seen_nids": ["nid_seen"]},
        )
        db_session.add_all([v1, cand])
        await db_session.flush()

        fake_integration = MagicMock()
        fake_integration.hh_employer_id = "emp_1"

        collections = [{
            "id": "response",
            "url": "https://api.hh.ru/negotiations/response?vacancy_id=hh_vac_1",
            "count": 1,
        }]
        page = {
            "found": 1,
            "items": [{"id": "nid_seen", "chat_id": None, "resume": {"id": "r1"}}],
            "pages": 1,
        }

        with patch(
            "app.services.integrations.hh.service.get_integration",
            new_callable=AsyncMock, return_value=fake_integration,
        ), patch(
            "app.services.integrations.hh.service.get_valid_access_token",
            new_callable=AsyncMock, return_value="tok",
        ), patch(
            "app.services.integrations.hh.client.get_negotiation_collections",
            new_callable=AsyncMock, return_value=collections,
        ), patch(
            "app.services.integrations.hh.client.get_collection_page",
            new_callable=AsyncMock, return_value=page,
        ), patch(
            "app.services.integrations.hh.service.import_response",
            new_callable=AsyncMock,
        ) as mock_import:
            stats = await hh_service.poll_responses_now(db_session, test_company.id)

        mock_import.assert_not_awaited()           # запомненный nid пропущен без импорта
        assert stats["skipped"] >= 1
