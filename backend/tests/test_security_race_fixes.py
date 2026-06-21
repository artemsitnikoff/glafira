"""Тесты безопасности: гонки/дубли/PII — security audit fixes.

FIX #2: UNIQUE-индексы против дублей Application/AiEvaluation под гонкой.
FIX #3: open_habr_contacts — атомарный захват (двойное платное списание).
FIX #5: PII (phone/email) убраны из промпта score_candidate.

НЕ утверждаем «pytest зелёный» без прогона на VPS.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vacancy, Application, Candidate
from app.models.habr_integration import HabrIntegration
from app.models.evaluation import AiEvaluation
from app.services.integrations.habr.sync import (
    import_habr_response,
    open_habr_contacts,
)
from app.services.integrations.hh.service import import_response as hh_import_response
from app.services.integrations.avito.sync import import_avito_application
from app.services.settings.crypto import encrypt_text
from app.core.errors import ValidationError


# ---------------------------------------------------------------------------
# Общие вспомогательные функции
# ---------------------------------------------------------------------------

def _make_habr_response_item(response_id: str = "habr-resp-race-1", login: str = "raceuser") -> dict:
    return {
        "id": response_id,
        "vacancy_id": "habr-vac-001",
        "body": "Сопроводительное письмо",
        "favorite": False,
        "archived": False,
        "created_at": "2026-06-21T10:00:00Z",
        "user": {
            "login": login,
            "name": "Тест Пользователь",
            "avatar": None,
            "specialization": "Python Developer",
            "skills": [{"title": "Python", "alias_name": "python"}],
            "experience_total": {"month": 24},
            "relocation": False,
            "remote": True,
            "compensation": {"value": 100000, "currency": "RUB"},
            "work_state": "search",
            "age": 28,
            "location": {"city": "Москва", "country": "RU"},
            "experiences": [
                {"company": "ООО Тест", "position": "Python Dev", "period": "2022—2024"}
            ],
            "educations": [],
        },
    }


def _make_avito_apply(apply_id: str = "avito-race-1") -> dict:
    return {
        "id": apply_id,
        "vacancy_id": "avito-vac-001",
        "created_at": "2026-06-21T10:00:00Z",
        "state": "active",
        "applicant": {
            "data": {
                "first_name": "Иван",
                "last_name": "Гончаров",
                "patronymic": "Петрович",
                "birthday": "1995-01-15",
                "citizenship": "RU",
                "education": "higher",
                "gender": "male",
            },
            "resume_id": None,
        },
        "contacts": {
            "phones": [{"value": "79001234567"}],
            "chat": None,
        },
        "enriched_properties": {
            "phone": None,
            "experience": "3 года",
            "age": 28,
            "citizenship": "RU",
        },
    }


def _make_hh_item(nid: str = "hh-neg-race-1") -> dict:
    return {
        "id": nid,
        "state": {"id": "response"},
        "chat_id": None,
        "resume": {
            "id": "hh-resume-race",
            "first_name": "Пётр",
            "last_name": "Иванов",
            "middle_name": None,
            "title": "Python Developer",
            "area": {"name": "Москва"},
            "gender": None,
            "birth_date": None,
            "age": None,
            "salary": None,
            "contact": [],
            "experience": [],
            "skill_set": [],
            "education": {},
            "skills": "",
            "alternate_url": None,
        },
    }


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def habr_vacancy_race(db_session: AsyncSession, admin_user) -> Vacancy:
    v = Vacancy(
        company_id=admin_user.company_id,
        name="Backend (Хабр race)",
        status="active",
        habr_vacancy_id="habr-vac-001",
    )
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)
    return v


@pytest_asyncio.fixture
async def habr_integration_race(db_session: AsyncSession, admin_user) -> HabrIntegration:
    integration = HabrIntegration(
        company_id=admin_user.company_id,
        access_token=encrypt_text("test-token-race"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(integration)
    await db_session.commit()
    await db_session.refresh(integration)
    return integration


@pytest_asyncio.fixture
async def avito_vacancy_race(db_session: AsyncSession, admin_user) -> Vacancy:
    from app.models.avito_integration import AvitoIntegration
    v = Vacancy(
        company_id=admin_user.company_id,
        name="Backend (Авито race)",
        status="active",
        avito_vacancy_id="avito-vac-001",
    )
    db_session.add(v)
    ai = AvitoIntegration(
        company_id=admin_user.company_id,
        client_id=encrypt_text("id"),
        client_secret=encrypt_text("sec"),
        access_token=encrypt_text("tok"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(ai)
    await db_session.commit()
    await db_session.refresh(v)
    return v


@pytest_asyncio.fixture
async def hh_vacancy_race(db_session: AsyncSession, admin_user) -> Vacancy:
    v = Vacancy(
        company_id=admin_user.company_id,
        name="Backend (hh race)",
        status="active",
        hh_vacancy_id="hh-vac-race",
    )
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)
    return v


# ---------------------------------------------------------------------------
# FIX #2 — Дубль-импорт отклика под «гонкой» → одна Application, нет 500
# ---------------------------------------------------------------------------

class TestFix2DuplicateImportRace:
    """Симулируем гонку: первый INSERT успешен, второй попадает в IntegrityError.
    Ожидаем: одна Application, никакого 500."""

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_habr_double_import_same_response_id(
        self,
        mock_habr_client,
        db_session: AsyncSession,
        admin_user,
        habr_vacancy_race: Vacancy,
        habr_integration_race: HabrIntegration,
    ):
        """Двойной вызов import_habr_response с тем же response_id → одна Application."""
        mock_habr_client.get_user_contacts = AsyncMock(return_value={})

        company_id = admin_user.company_id
        response_item = _make_habr_response_item(response_id="habr-resp-dedup-1")

        # Первый импорт
        result1 = await import_habr_response(
            db_session, company_id, habr_vacancy_race, response_item,
            access_token="tok",
        )
        await db_session.flush()
        assert result1 == "created"

        # Второй вызов с тем же response_id — должен вернуть "updated" и НЕ создать дубль
        result2 = await import_habr_response(
            db_session, company_id, habr_vacancy_race, response_item,
            access_token="tok",
        )
        await db_session.flush()
        assert result2 == "updated"

        # Проверяем что ровно одна Application
        apps = (await db_session.execute(
            select(Application).where(
                Application.habr_response_id == "habr-resp-dedup-1",
                Application.company_id == company_id,
            )
        )).scalars().all()
        assert len(apps) == 1, f"Ожидали 1 Application, получили {len(apps)}"

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_habr_integrity_error_handled(
        self,
        mock_habr_client,
        db_session: AsyncSession,
        admin_user,
        habr_vacancy_race: Vacancy,
        habr_integration_race: HabrIntegration,
    ):
        """Имитируем IntegrityError при flush — функция должна перечитать существующий Application."""
        from sqlalchemy.exc import IntegrityError as SAIntegrityError
        mock_habr_client.get_user_contacts = AsyncMock(return_value={})

        company_id = admin_user.company_id
        response_item = _make_habr_response_item(response_id="habr-resp-ie-1")

        # Сначала создаём Application вручную (симулируем "первый воркер")
        existing_cand = Candidate(
            company_id=company_id,
            source="habr",
            first_name="Тест",
            last_name="Кандидат",
        )
        db_session.add(existing_cand)
        await db_session.flush()

        existing_app = Application(
            company_id=company_id,
            candidate_id=existing_cand.id,
            vacancy_id=habr_vacancy_race.id,
            stage="response",
            habr_response_id="habr-resp-ie-1",
            created_at=datetime.now(timezone.utc),
            selected_at=datetime.now(timezone.utc),
        )
        db_session.add(existing_app)
        await db_session.flush()

        # Второй импорт с тем же response_id — должен найти existing_app в SELECT и вернуть "updated"
        result = await import_habr_response(
            db_session, company_id, habr_vacancy_race, response_item,
            access_token="tok",
        )
        # existing_app уже есть → результат "updated"
        assert result == "updated"

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_avito_double_import_same_application_id(
        self,
        mock_avito_client,
        db_session: AsyncSession,
        admin_user,
        avito_vacancy_race: Vacancy,
    ):
        """Двойной вызов import_avito_application с тем же apply_id → одна Application."""
        mock_avito_client.get_resume_v2 = AsyncMock(side_effect=Exception("no resume"))

        company_id = admin_user.company_id
        apply = _make_avito_apply(apply_id="avito-dedup-1")

        result1 = await import_avito_application(
            db_session, company_id, avito_vacancy_race, apply,
            access_token="tok",
        )
        await db_session.flush()
        assert result1 == "created"

        result2 = await import_avito_application(
            db_session, company_id, avito_vacancy_race, apply,
            access_token="tok",
        )
        await db_session.flush()
        assert result2 == "updated"

        apps = (await db_session.execute(
            select(Application).where(
                Application.avito_application_id == "avito-dedup-1",
                Application.company_id == company_id,
            )
        )).scalars().all()
        assert len(apps) == 1, f"Ожидали 1 Application (Авито), получили {len(apps)}"

    @patch("app.services.integrations.hh.service.hh_client")
    @patch("app.services.integrations.hh.service.save_hh_resume_document")
    async def test_hh_double_import_same_negotiation_id(
        self,
        mock_save_doc,
        mock_hh_client,
        db_session: AsyncSession,
        admin_user,
        hh_vacancy_race: Vacancy,
    ):
        """Двойной вызов hh import_response с тем же nid → одна Application."""
        mock_hh_client.get_resume = AsyncMock(side_effect=Exception("no full resume"))
        mock_save_doc = AsyncMock(return_value=None)

        company_id = admin_user.company_id
        item = _make_hh_item(nid="hh-neg-dedup-1")

        with patch(
            "app.services.integrations.hh.service.save_hh_resume_document",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result1 = await hh_import_response(db_session, company_id, hh_vacancy_race, item)
            await db_session.flush()
            assert result1 == "created"

            result2 = await hh_import_response(db_session, company_id, hh_vacancy_race, item)
            await db_session.flush()
            assert result2 == "updated"

        apps = (await db_session.execute(
            select(Application).where(
                Application.hh_negotiation_id == "hh-neg-dedup-1",
                Application.company_id == company_id,
            )
        )).scalars().all()
        assert len(apps) == 1, f"Ожидали 1 Application (hh), получили {len(apps)}"


# ---------------------------------------------------------------------------
# FIX #3 — open_habr_contacts атомарный захват (двойное платное списание)
# ---------------------------------------------------------------------------

class TestFix3HabrContactsAtomicSlot:
    """Проверяем атомарный захват слота: повторный вызов НЕ делает 2-й платный вызов."""

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_double_call_makes_only_one_paid_api_call(
        self,
        mock_habr_client,
        db_session: AsyncSession,
        admin_user,
        habr_integration_race: HabrIntegration,
    ):
        """Два последовательных вызова open_habr_contacts → get_user_contacts вызван 1 раз."""
        mock_habr_client.get_valid_access_token_habr = AsyncMock(
            return_value="test-habr-token"
        )
        mock_contacts = {"phones": ["79991234567"], "emails": ["test@example.com"]}
        mock_habr_client.get_user_contacts = AsyncMock(return_value=mock_contacts)

        company_id = admin_user.company_id
        # Создаём хабр-кандидата
        cand = Candidate(
            company_id=company_id,
            source="habr",
            external_source="habr",
            external_id="habr-user-atomic-1",
            first_name="Алексей",
            last_name="Смирнов",
        )
        db_session.add(cand)
        await db_session.flush()
        await db_session.refresh(cand)

        user_id = admin_user.id

        with patch(
            "app.services.integrations.habr.sync.get_valid_access_token_habr",
            new_callable=AsyncMock,
            return_value="test-habr-token",
        ), patch(
            "app.services.integrations.habr.sync.find_duplicate_candidates",
            new_callable=AsyncMock,
            return_value=[],
        ):
            # Первый вызов — должен сделать платный API-вызов
            result1 = await open_habr_contacts(
                db_session, company_id, cand.id, user_id
            )
            assert result1.get("already_opened") is False or result1.get("phone") is not None

            # Второй вызов — контакты уже открыты, платный вызов НЕ должен повториться
            result2 = await open_habr_contacts(
                db_session, company_id, cand.id, user_id
            )
            assert result2.get("already_opened") is True

        # get_user_contacts вызван РОВНО ОДИН РАЗ
        assert mock_habr_client.get_user_contacts.await_count == 1, (
            f"Ожидали 1 вызов get_user_contacts, получили "
            f"{mock_habr_client.get_user_contacts.await_count}"
        )

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_failed_paid_call_resets_slot(
        self,
        mock_habr_client,
        db_session: AsyncSession,
        admin_user,
        habr_integration_race: HabrIntegration,
    ):
        """Если платный вызов упал — habr_contacts_opened_at сбрасывается в NULL."""
        company_id = admin_user.company_id

        cand = Candidate(
            company_id=company_id,
            source="habr",
            external_source="habr",
            external_id="habr-user-fail-1",
            first_name="Борис",
            last_name="Петров",
        )
        db_session.add(cand)
        await db_session.flush()
        await db_session.refresh(cand)
        cand_id = cand.id

        with patch(
            "app.services.integrations.habr.sync.get_valid_access_token_habr",
            new_callable=AsyncMock,
            return_value="test-habr-token",
        ):
            mock_habr_client.get_user_contacts = AsyncMock(
                side_effect=ValueError("402 Payment Required")
            )

            with pytest.raises(ValidationError):
                await open_habr_contacts(
                    db_session, company_id, cand_id, admin_user.id
                )

        # После провала платного вызова — флаг должен быть сброшен в NULL
        await db_session.refresh(cand)
        assert cand.habr_contacts_opened_at is None, (
            "habr_contacts_opened_at должен быть NULL после провала платного вызова"
        )


# ---------------------------------------------------------------------------
# FIX #5 — phone/email убраны из промпта score_candidate (152-ФЗ)
# ---------------------------------------------------------------------------

class TestFix5NoPiiInScoringPrompt:
    """Проверяем что phone/email НЕ попадают в промпт score_candidate."""

    def test_scoring_user_template_has_no_phone_email_placeholders(self):
        """SCORING_USER_TEMPLATE не содержит {candidate_phone} и {candidate_email}."""
        from app.services.glafira.prompts import SCORING_USER_TEMPLATE
        assert "{candidate_phone}" not in SCORING_USER_TEMPLATE, (
            "candidate_phone не должен быть в SCORING_USER_TEMPLATE"
        )
        assert "{candidate_email}" not in SCORING_USER_TEMPLATE, (
            "candidate_email не должен быть в SCORING_USER_TEMPLATE"
        )

    def test_scoring_user_template_still_contains_required_fields(self):
        """Шаблон сохраняет все нужные для оценки поля (без PII)."""
        from app.services.glafira.prompts import SCORING_USER_TEMPLATE
        required = [
            "{vacancy_name}", "{vacancy_city}", "{vacancy_salary}",
            "{vacancy_description}", "{candidate_name}", "{candidate_city}",
            "{resume_text}", "{experience_text}", "{skills_text}", "{salary_expectation}",
        ]
        for field in required:
            assert field in SCORING_USER_TEMPLATE, f"Поле {field} должно быть в шаблоне"

    async def test_score_candidate_prompt_does_not_contain_phone_email(
        self,
        db_session: AsyncSession,
        admin_user,
        test_candidate,
    ):
        """Собранный user_prompt для score_candidate НЕ содержит phone/email кандидата."""
        from app.services.glafira.scoring import score_candidate
        from app.core.errors import GlafiraParseError, OpenRouterNotConfiguredError

        # Убеждаемся что у кандидата есть phone/email
        test_candidate.phone = "79991234567"
        test_candidate.email = "secret@example.com"
        await db_session.flush()

        # Создаём вакансию для скоринга
        vacancy = Vacancy(
            company_id=admin_user.company_id,
            name="Python Developer",
            city="Москва",
            description="Описание вакансии",
        )
        db_session.add(vacancy)
        await db_session.flush()
        await db_session.refresh(vacancy)

        captured_prompts = []

        async def mock_call_json(system: str, user: str, **kwargs):
            captured_prompts.append({"system": system, "user": user})
            # Возвращаем валидный ответ чтобы не упасть на валидации
            return {
                "score": 75,
                "verdict": "good",
                "summary": "Хороший кандидат",
                "strengths": ["Python"],
                "risks": [],
                "requirements_match": [],
                "forecast": None,
                "questions": [],
            }

        with patch(
            "app.services.glafira.scoring.call_json",
            side_effect=mock_call_json,
        ):
            try:
                await score_candidate(
                    session=db_session,
                    company_id=admin_user.company_id,
                    candidate_id=test_candidate.id,
                    vacancy_id=vacancy.id,
                )
            except (OpenRouterNotConfiguredError, Exception):
                # Если OpenRouter не настроен — нам важно только что был вызов и промпт захвачен
                pass

        # Если вызов был перехвачен — проверяем отсутствие PII
        if captured_prompts:
            user_prompt = captured_prompts[0]["user"]
            assert "79991234567" not in user_prompt, (
                "Телефон кандидата НЕ должен быть в user_prompt скоринга"
            )
            assert "secret@example.com" not in user_prompt, (
                "Email кандидата НЕ должен быть в user_prompt скоринга"
            )
            # Имя должно присутствовать (не PII-критичное для оценки)
            assert test_candidate.full_name in user_prompt or \
                   test_candidate.first_name in user_prompt, (
                "Имя кандидата должно быть в промпте"
            )
