"""Тесты импорта кандидатов + истории комментариев из Talantix (talantix.ru).

Офлайн: GraphQL мокается РЕАЛЬНОЙ структурой (подтверждена по доке api.talantix.ru/docs).
Живой API не пинится (заказчиком на VPS). Патч-таргеты — на модулях использования.
"""

import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select, func

from app.core.errors import ValidationError
from app.services.integrations.talantix import mapper as tmap
from app.services.integrations.talantix import service as tsvc
from app.services.integrations.talantix.client import TalantixClient, TalantixError
from app.services.candidate_import import (
    _classify_talantix_rows,
    _process_talantix_person,
    _import_talantix_comments,
)
from app.models import Candidate, Comment, Consent, CandidateExperience, CandidateSkill


class _FakeResult:
    def scalar_one_or_none(self):
        return MagicMock(id=uuid4())


class _FakeSession:
    """Минимальная фейк-сессия для save_config (execute→integration; audit замокан)."""
    async def execute(self, *a, **k):
        return _FakeResult()


# --- Реалистичные ноды GraphQL (структура подтверждена по доке) -------------

def _person_node(pid=555):
    return {
        "__typename": "PersonItem",
        "id": pid,
        "firstName": "Иван",
        "lastName": "Петров",
        "middleName": "Сергеевич",
        "gender": "male",
        "birthDay": 642729600000,
        "updatedAt": 1700000000000,
        "area": {"id": 1, "name": "Москва"},
        "source": {"id": 2, "name": "Отклик, hh.ru"},
        "contacts": {"items": [
            {"type": "cell", "value": "+7 999 123-45-67"},
            {"type": "email", "value": "ivan@example.com"},
            {"type": "telegram", "value": "@ivan"},
        ]},
        "resumes": {"items": [
            {"__typename": "StructuredResume", "id": 9, "title": "Python-разработчик",
             "skills": "Опыт 5 лет. Python, Django. <b>PostgreSQL</b>",
             "keySkills": ["Python", "Django", "PostgreSQL"],
             "salary": {"amount": 150000, "currency": "RUR"},
             "education": {"level": {"name": "Высшее"}},
             "experiences": {"items": [
                 {"position": "Backend-разработчик", "description": "Разработка API",
                  "company": {"name": "ООО Ромашка"}, "area": {"name": "Москва"},
                  "period": {"start": 1577836800000, "end": 1656633600000, "months": 30}},
             ]}},
        ]},
        "personalDataAgreement": {
            "personalDataAgreementStatus": "agree",
            "updatedAt": 1699000000000,
            "expiredAt": None,
        },
        "responses": {"count": 3},
    }


_COMMENT_ADDED = {
    "__typename": "CommentAdded",
    "id": "ca-1",
    "eventTime": 1699100000000,
    "html": "<p>Хороший кандидат</p>",
    "initiator": {"__typename": "CompanyManager", "firstName": "Мария",
                  "lastName": "Иванова", "middleName": None},
    "vacancy": {"id": 10, "title": "Backend"},
}

_HH_COMMENT_ADDED = {
    "__typename": "HhCommentAdded",
    "id": "hh-1",
    "eventTime": 1699200000000,
    "html": "Отклик с hh",
    "managerName": "Пётр Сидоров",
    "initiator": None,
}


# --- Маппер персоны ---------------------------------------------------------

class TestTalantixPersonMapper:
    def test_map_person_full(self):
        m = tmap.map_person(_person_node())
        assert m["talantix_person_id"] == "555"
        assert m["first_name"] == "Иван"
        assert m["last_name"] == "Петров"
        assert m["middle_name"] == "Сергеевич"
        # телефон в формате хранения (цифры без '+')
        assert m["phone"] == "79991234567"
        assert m["email"] == "ivan@example.com"
        assert m["city"] == "Москва"
        assert m["gender"] == "male"
        # резюме собирается из структуры (title + о себе + опыт), HTML снят
        assert "Python" in m["resume_text"]
        assert "<b>" not in m["resume_text"]
        assert "Опыт работы" in m["resume_text"]
        assert m["last_position"] == "Python-разработчик"
        # структурные секции (опыт/навыки) — из experiences/keySkills, НЕ из пустого skills
        assert [s["skill"] for s in m["skills"]] == ["Python", "Django", "PostgreSQL"]
        assert len(m["experience"]) == 1
        exp = m["experience"][0]
        assert exp["position"] == "Backend-разработчик"
        assert exp["company"] == "ООО Ромашка"
        assert exp["period"] == "2020-01 — 2022-07"  # формат hh (start/end мс → YYYY-MM)
        # зарплата ИЗ резюме Talantix (amount+currency), раньше терялась
        assert m["salary_expectation"] == 150000
        assert m["messengers"] == [{"type": "tg", "value": "@ivan"}]
        assert m["responses_count"] == 3
        assert m["birth_date"] is not None

    def test_map_person_minimal(self):
        node = {"__typename": "PersonItem", "id": 1, "firstName": "Анна"}
        m = tmap.map_person(node)
        assert m["first_name"] == "Анна"
        assert m["last_name"] == ""
        assert m["phone"] is None
        assert m["email"] is None
        assert m["resume_text"] is None
        assert m["talantix_person_id"] == "1"

    def test_map_person_custom_resume(self):
        # Произвольное резюме (CustomResume): name+text, структурного опыта НЕТ,
        # но текст и должность не теряем (раньше выходило пусто).
        node = {
            "__typename": "PersonItem", "id": 77, "firstName": "Дарья", "lastName": "Горева",
            "contacts": {"items": [{"type": "cell", "value": "+79001234567"}]},
            "resumes": {"items": [
                {"__typename": "CustomResume", "name": "Врач-косметолог",
                 "text": "Опыт работы косметологом 3 года. <b>Инъекции</b>, чистки."},
            ]},
        }
        m = tmap.map_person(node)
        assert m["last_position"] == "Врач-косметолог"
        assert m["experience"] == []
        assert m["skills"] == []
        assert "Врач-косметолог" in m["resume_text"]
        assert "Инъекции" in m["resume_text"]
        assert "<b>" not in m["resume_text"]  # HTML снят


# --- Маппер комментариев истории -------------------------------------------

class TestTalantixCommentMapper:
    def test_comment_added_author_from_initiator_and_vacancy_prefix(self):
        c = tmap.map_comment_event(_COMMENT_ADDED)
        assert c["external_id"] == "ca-1"
        # автор из initiator (CompanyManager) — Фамилия Имя
        assert c["author_name"] == "Иванова Мария"
        # контекст вакансии зафиксирован в теле истории
        assert c["body"].startswith("[Вакансия: Backend]")
        assert "Хороший кандидат" in c["body"]
        # дата = eventTime ОРИГИНАЛА
        expected = datetime.fromtimestamp(1699100000000 / 1000, tz=timezone.utc)
        assert c["created_at"] == expected

    def test_hh_comment_added_author_from_manager_name(self):
        c = tmap.map_comment_event(_HH_COMMENT_ADDED)
        assert c["external_id"] == "hh-1"
        assert c["author_name"] == "Пётр Сидоров"
        assert c["body"] == "Отклик с hh"
        expected = datetime.fromtimestamp(1699200000000 / 1000, tz=timezone.utc)
        assert c["created_at"] == expected

    def test_system_initiator_author(self):
        node = {**_COMMENT_ADDED, "id": "ca-2", "vacancy": None,
                "initiator": {"__typename": "SystemInitiator"}}
        c = tmap.map_comment_event(node)
        assert c["author_name"] == "Talantix (система)"

    def test_non_comment_event_ignored(self):
        assert tmap.map_comment_event({"__typename": "StatusChanged"}) is None

    def test_empty_html_ignored(self):
        node = {**_COMMENT_ADDED, "id": "ca-3", "html": ""}
        assert tmap.map_comment_event(node) is None

    def test_pd_agreement_signed(self):
        assert tmap.pd_agreement_is_signed({"personalDataAgreementStatus": "agree"}) is True
        assert tmap.pd_agreement_is_signed({"personalDataAgreementStatus": "sent"}) is False
        assert tmap.pd_agreement_is_signed({"personalDataAgreementStatus": "disagree"}) is False
        assert tmap.pd_agreement_is_signed(None) is False
        signed_at = tmap.pd_agreement_signed_at({"updatedAt": 1699000000000})
        assert signed_at == datetime.fromtimestamp(1699000000000 / 1000, tz=timezone.utc)


# --- Клиент: пагинация истории, ошибки, PersonError -------------------------

class TestTalantixClient:
    @pytest.mark.asyncio
    async def test_fetch_all_history_paginates_all_pages(self):
        """Курсор истории: hasNextPage=true→false → берём ОБЕ страницы."""
        client = TalantixClient(uuid4())
        page1 = {"person": {"__typename": "PersonItem", "history": {
            "items": [_COMMENT_ADDED],
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
        }}}
        page2 = {"person": {"__typename": "PersonItem", "history": {
            "items": [_HH_COMMENT_ADDED],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}
        client._gql = AsyncMock(side_effect=[page1, page2])

        events = await client.fetch_all_history(555)
        await client.close()

        assert len(events) == 2
        types = {e["__typename"] for e in events}
        assert types == {"CommentAdded", "HhCommentAdded"}
        assert client._gql.await_count == 2  # обе страницы запрошены

    @pytest.mark.asyncio
    async def test_get_person_full_person_error_returns_none(self):
        """PersonError в union → None (кандидат пропускается, импорт не падает)."""
        client = TalantixClient(uuid4())
        client._gql = AsyncMock(return_value={
            "person": {"__typename": "PersonError", "message": "нет доступа"}
        })
        result = await client.get_person_full(1)
        await client.close()
        assert result is None

    @pytest.mark.asyncio
    async def test_gql_data_errors_raises(self):
        """HTTP 200 + непустой data.errors = ОШИБКА (raise), НЕ проглатывается как успех."""
        client = TalantixClient(uuid4())
        client._ensure_token = AsyncMock(return_value="tok")
        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"errors": [{"message": "boom"}]}
        client._client.post = AsyncMock(return_value=resp)

        with pytest.raises(TalantixError):
            await client._gql("query { x }")
        await client.close()


# --- Классификация превью ---------------------------------------------------

class TestTalantixClassification:
    def test_classify_new(self):
        rows = _classify_talantix_rows(
            [{"first_name": "Иван", "last_name": "Петров",
              "phone": "79991234567", "email": "a@b.c"}],
            [],
        )
        assert rows[0]["status"] == "new"
        assert rows[0]["source"] == "talantix"

    def test_classify_duplicate_and_error(self):
        existing = [Candidate(id=uuid4(), first_name="Иван", last_name="Петров",
                              phone="79991234567", email="x@y.z")]
        rows = _classify_talantix_rows(
            [
                {"first_name": "Иван", "last_name": "Петров", "phone": "+79991234567", "email": ""},
                {"first_name": "", "last_name": "", "phone": "", "email": ""},
            ],
            existing,
        )
        assert rows[0]["status"] == "duplicate"
        assert rows[1]["status"] == "error"


# --- Интеграция: обработка персоны против реальной сессии --------------------

class TestTalantixProcessPerson:
    @pytest.mark.asyncio
    async def test_creates_candidate_with_comments_and_consent(self, db_session, admin_user):
        company_id = admin_user.company_id
        mapped = tmap.map_person(_person_node())
        events = [_COMMENT_ADDED, _HH_COMMENT_ADDED]
        pd = _person_node()["personalDataAgreement"]
        stats: dict = {}

        await _process_talantix_person(db_session, company_id, mapped, events, pd, "skip", stats)
        await db_session.flush()

        assert stats.get("created") == 1
        assert stats.get("comments") == 2

        cand = (await db_session.execute(
            select(Candidate).where(
                Candidate.company_id == company_id,
                Candidate.talantix_person_id == "555",
            )
        )).scalar_one()
        assert cand.source == "talantix"
        assert cand.external_source == "talantix"
        assert cand.phone == "79991234567"
        assert cand.extra.get("talantix_responses_count") == 3

        comments = (await db_session.execute(
            select(Comment).where(Comment.candidate_id == cand.id, Comment.source == "talantix")
        )).scalars().all()
        assert len(comments) == 2
        by_ext = {c.external_id: c for c in comments}
        # автор и дата ОРИГИНАЛА, не импортёр
        assert by_ext["ca-1"].author_name_ext == "Иванова Мария"
        assert by_ext["ca-1"].author_user_id is None
        assert by_ext["ca-1"].created_at == datetime.fromtimestamp(1699100000000 / 1000, tz=timezone.utc)
        assert by_ext["hh-1"].author_name_ext == "Пётр Сидоров"

        # согласие 'agree' → Consent(signed)
        consent = (await db_session.execute(
            select(Consent).where(Consent.candidate_id == cand.id)
        )).scalar_one()
        assert consent.status == "signed"
        assert consent.signed_at is not None

    @pytest.mark.asyncio
    async def test_creates_structured_resume_and_salary(self, db_session, admin_user):
        """Опыт/навыки/зарплата из резюме Talantix → структурные записи (таб «Резюме»)."""
        company_id = admin_user.company_id
        mapped = tmap.map_person(_person_node())
        stats: dict = {}
        await _process_talantix_person(db_session, company_id, mapped, [], None, "skip", stats)
        await db_session.flush()

        cand = (await db_session.execute(
            select(Candidate).where(Candidate.talantix_person_id == "555")
        )).scalar_one()
        assert cand.salary_expectation == 150000
        assert cand.salary_from == 150000 and cand.salary_to == 150000

        exps = (await db_session.execute(
            select(CandidateExperience).where(CandidateExperience.candidate_id == cand.id)
        )).scalars().all()
        assert len(exps) == 1
        assert exps[0].position == "Backend-разработчик"
        assert exps[0].company == "ООО Ромашка"
        assert exps[0].period == "2020-01 — 2022-07"

        skills = (await db_session.execute(
            select(CandidateSkill).where(CandidateSkill.candidate_id == cand.id)
        )).scalars().all()
        assert {s.skill for s in skills} == {"Python", "Django", "PostgreSQL"}

    @pytest.mark.asyncio
    async def test_dedup_existing_candidate_enriched_not_duplicated(self, db_session, admin_user):
        company_id = admin_user.company_id
        existing = Candidate(
            company_id=company_id, last_name="Петров", first_name="Иван",
            phone="79991234567", email="ivan@example.com", source="manual",
        )
        db_session.add(existing)
        await db_session.flush()

        mapped = tmap.map_person(_person_node())
        stats: dict = {}
        await _process_talantix_person(db_session, company_id, mapped, [_COMMENT_ADDED], None, "update", stats)
        await db_session.flush()

        # НЕ дубль — тот же кандидат обогащён
        assert stats.get("updated") == 1
        assert stats.get("created", 0) == 0
        total = (await db_session.execute(
            select(func.count()).select_from(Candidate).where(Candidate.company_id == company_id)
        )).scalar_one()
        assert total == 1
        # talantix_person_id бэкфилл + комментарий привязан к существующему
        await db_session.refresh(existing)
        assert existing.talantix_person_id == "555"
        assert stats.get("comments") == 1
        # структурное резюме дозалилось на существующего (был без опыта) — режим «Обновить»
        exps = (await db_session.execute(
            select(CandidateExperience).where(CandidateExperience.candidate_id == existing.id)
        )).scalars().all()
        assert len(exps) == 1
        assert exps[0].period == "2020-01 — 2022-07"

    @pytest.mark.asyncio
    async def test_idempotent_reimport(self, db_session, admin_user):
        company_id = admin_user.company_id
        mapped = tmap.map_person(_person_node())
        events = [_COMMENT_ADDED, _HH_COMMENT_ADDED]

        stats1: dict = {}
        await _process_talantix_person(db_session, company_id, mapped, events, None, "skip", stats1)
        await db_session.flush()

        stats2: dict = {}
        await _process_talantix_person(db_session, company_id, mapped, events, None, "skip", stats2)
        await db_session.flush()

        # второй прогон не плодит кандидата и не дублирует комментарии
        cand_count = (await db_session.execute(
            select(func.count()).select_from(Candidate).where(Candidate.company_id == company_id)
        )).scalar_one()
        assert cand_count == 1
        comment_count = (await db_session.execute(
            select(func.count()).select_from(Comment).where(
                Comment.company_id == company_id, Comment.source == "talantix"
            )
        )).scalar_one()
        assert comment_count == 2
        assert stats2.get("comments") == 0  # ничего нового не импортировано
        assert stats2.get("skipped") == 1

    @pytest.mark.asyncio
    async def test_import_comments_dedup(self, db_session, admin_user):
        company_id = admin_user.company_id
        cand = Candidate(company_id=company_id, last_name="Т", first_name="К", source="manual")
        db_session.add(cand)
        await db_session.flush()

        n1 = await _import_talantix_comments(db_session, company_id, cand.id, [_COMMENT_ADDED, _COMMENT_ADDED])
        await db_session.flush()
        # тот же external_id внутри одного вызова → только один
        assert n1 == 1
        n2 = await _import_talantix_comments(db_session, company_id, cand.id, [_COMMENT_ADDED])
        assert n2 == 0

    @pytest.mark.asyncio
    async def test_company_isolation(self, db_session, admin_user, second_company):
        """Кандидат/комментарии одной компании не видны/не матчатся у другой."""
        company_a = admin_user.company_id
        company_b = second_company.id

        # В компании B уже есть кандидат с тем же телефоном
        b_cand = Candidate(
            company_id=company_b, last_name="Другой", first_name="Борис",
            phone="79991234567", source="manual",
        )
        db_session.add(b_cand)
        await db_session.flush()

        mapped = tmap.map_person(_person_node())
        stats: dict = {}
        await _process_talantix_person(db_session, company_a, mapped, [_COMMENT_ADDED], None, "skip", stats)
        await db_session.flush()

        # В A создан НОВЫЙ кандидат (не смэтчен с B)
        assert stats.get("created") == 1
        a_count = (await db_session.execute(
            select(func.count()).select_from(Candidate).where(Candidate.company_id == company_a)
        )).scalar_one()
        assert a_count == 1
        # У B комментарии Talantix НЕ появились
        b_comments = (await db_session.execute(
            select(func.count()).select_from(Comment).where(
                Comment.company_id == company_b, Comment.source == "talantix"
            )
        )).scalar_one()
        assert b_comments == 0


# --- Connect: разбор JSON-блока токенов + access-first валидация ------------

class TestTalantixConnectParse:
    def test_parse_json_both_tokens_and_expires(self):
        raw = json.dumps({
            "name": "My token",
            "access_token": "acc-123",
            "expires_in": 86400,
            "refresh_token": "ref-456",
            "refresh_token_expires_in": 10368000,
            "token_type": "bearer",
            "created_at": 1700000000000,
        })
        access, refresh, expires_at = tsvc._parse_connect_input(raw)
        assert access == "acc-123"
        assert refresh == "ref-456"
        expected = datetime.fromtimestamp(1700000000000 / 1000, tz=timezone.utc) + timedelta(seconds=86400)
        assert expires_at == expected

    def test_parse_json_without_created_at_uses_now(self):
        raw = json.dumps({"access_token": "a", "refresh_token": "r", "expires_in": 100})
        access, refresh, expires_at = tsvc._parse_connect_input(raw)
        assert access == "a" and refresh == "r"
        assert expires_at is not None  # база = now (не падаем без created_at)

    def test_parse_url_to_token_page_raises_400(self):
        with pytest.raises(ValidationError) as e:
            tsvc._parse_connect_input("https://api.talantix.ru/docs/pages/token/?hash=abc123")
        assert "браузере" in str(e.value).lower() or "ссылка" in str(e.value).lower()

    def test_parse_json_without_refresh_raises(self):
        with pytest.raises(ValidationError):
            tsvc._parse_connect_input(json.dumps({"access_token": "acc"}))

    def test_parse_plain_string_is_refresh(self):
        access, refresh, expires_at = tsvc._parse_connect_input("just-a-raw-refresh-token")
        assert access is None
        assert refresh == "just-a-raw-refresh-token"
        assert expires_at is None

    def test_parse_empty_raises(self):
        with pytest.raises(ValidationError):
            tsvc._parse_connect_input("   ")


class TestTalantixConnectSaveConfig:
    @pytest.mark.asyncio
    async def test_access_valid_stores_both_without_refresh(self):
        """Пастнутый access рабочий → сохраняем пару как есть, refresh НЕ ротируем."""
        raw = json.dumps({
            "access_token": "acc", "refresh_token": "ref",
            "expires_in": 86400, "created_at": 1700000000000,
        })
        with patch("app.services.integrations.talantix.service.probe_access_token",
                   new=AsyncMock(return_value=True)) as mprobe, \
             patch("app.services.integrations.talantix.token.save_tokens",
                   new=AsyncMock()) as msave, \
             patch("app.services.integrations.talantix.token.connect_and_store",
                   new=AsyncMock()) as mconnect, \
             patch("app.services.integrations.talantix.service.audit",
                   new=AsyncMock()):
            await tsvc.save_config(_FakeSession(), uuid4(), token_input=raw, user_id=uuid4())

        mprobe.assert_awaited_once()
        msave.assert_awaited_once()
        kwargs = msave.await_args.kwargs
        assert kwargs["access_token"] == "acc"
        assert kwargs["refresh_token"] == "ref"
        assert kwargs["expires_at"] is not None
        mconnect.assert_not_awaited()  # refresh не тратим

    @pytest.mark.asyncio
    async def test_access_invalid_falls_back_to_refresh(self):
        """Access не сработал → фолбэк на обмен refresh (+ GraphQL-проверка)."""
        raw = json.dumps({"access_token": "stale", "refresh_token": "ref", "expires_in": 86400})
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.check_connection = AsyncMock(return_value=True)
        with patch("app.services.integrations.talantix.service.probe_access_token",
                   new=AsyncMock(return_value=False)), \
             patch("app.services.integrations.talantix.token.connect_and_store",
                   new=AsyncMock()) as mconnect, \
             patch("app.services.integrations.talantix.token.save_tokens",
                   new=AsyncMock()) as msave, \
             patch("app.services.integrations.talantix.service.TalantixClient",
                   return_value=mock_client), \
             patch("app.services.integrations.talantix.service.audit",
                   new=AsyncMock()):
            await tsvc.save_config(_FakeSession(), uuid4(), token_input=raw, user_id=uuid4())

        mconnect.assert_awaited_once()
        assert mconnect.await_args.kwargs["refresh_token"] == "ref"
        mock_client.check_connection.assert_awaited_once()
        msave.assert_not_awaited()  # свежую пару сохранил connect_and_store

    @pytest.mark.asyncio
    async def test_plain_refresh_string_uses_refresh_path(self):
        """Голая refresh-строка → access=None → сразу фолбэк на refresh (как раньше)."""
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.check_connection = AsyncMock(return_value=True)
        with patch("app.services.integrations.talantix.service.probe_access_token",
                   new=AsyncMock(return_value=False)) as mprobe, \
             patch("app.services.integrations.talantix.token.connect_and_store",
                   new=AsyncMock()) as mconnect, \
             patch("app.services.integrations.talantix.service.TalantixClient",
                   return_value=mock_client), \
             patch("app.services.integrations.talantix.service.audit",
                   new=AsyncMock()):
            await tsvc.save_config(_FakeSession(), uuid4(), token_input="plain-refresh", user_id=uuid4())

        mprobe.assert_not_awaited()  # access отсутствует — probe не зовём
        mconnect.assert_awaited_once()
        assert mconnect.await_args.kwargs["refresh_token"] == "plain-refresh"
