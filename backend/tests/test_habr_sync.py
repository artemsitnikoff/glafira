"""Тесты синхронизации откликов Хабр Карьера.

Все вызовы habr_client мокаются по import-site (sync.py).
Проверяется реальная инфраструктура: дедуп, Application, normalize_phone, company-изоляция, audit.
НЕ утверждаем «pytest зелёный» без прогона на VPS.

Структура мок-отклика строго по документации Хабр Карьера:
  { id, vacancy_id, body, favorite, archived, created_at, user }
  user: { login, name, avatar, specialization, skills[{title}],
          experience_total{month}, compensation{value,currency}, work_state, age,
          location{city,country}, experiences[{company,position,period}],
          educations[{university,faculty,start_date,end_date}] }
  ⚠️ phone/email в user ОТСУТСТВУЮТ (только через платный /contacts)
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Vacancy, Application, Candidate
from app.models.habr_integration import HabrIntegration
from app.services.integrations.habr import sync as habr_sync
from app.services.integrations.habr.sync import (
    import_habr_response,
    poll_habr_responses_now,
    link_habr_vacancy,
    unlink_habr_vacancy,
    get_valid_access_token_habr,
    open_habr_contacts,
    _habr_response_user_to_normalized,
)
from app.services.settings.crypto import encrypt_text
from app.core.errors import ValidationError


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def habr_vacancy(db_session: AsyncSession, admin_user) -> Vacancy:
    """Вакансия с привязанным habr_vacancy_id."""
    v = Vacancy(
        company_id=admin_user.company_id,
        name="Backend Developer (Хабр)",
        status="active",
        habr_vacancy_id="habr-vac-001",
    )
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)
    return v


@pytest_asyncio.fixture
async def habr_integration(db_session: AsyncSession, admin_user) -> HabrIntegration:
    """HabrIntegration с действующим токеном."""
    integration = HabrIntegration(
        company_id=admin_user.company_id,
        access_token=encrypt_text("test-habr-access-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(integration)
    await db_session.commit()
    await db_session.refresh(integration)
    return integration


def _make_habr_user(
    login: str = "alexsmirn",
    name: str = "Смирнов Алексей",
    specialization: str = "Python Developer",
    city: str = "Москва",
    skills: list | None = None,
    experiences: list | None = None,
    educations: list | None = None,
    compensation_value: int | None = 150000,
    compensation_currency: str = "RUB",
    experience_total_month: int | None = 36,
    work_state: str = "search",
    age: int | None = 30,
) -> dict:
    """Конструктор мок-user из отклика Хабра (реальная структура по документации)."""
    return {
        "login": login,
        "name": name,
        "avatar": f"https://career.habr.com/avatars/{login}.jpg",
        "specialization": specialization,
        "skills": skills or [
            {"title": "Python", "alias_name": "python"},
            {"title": "FastAPI", "alias_name": "fastapi"},
            {"title": "PostgreSQL", "alias_name": "postgresql"},
        ],
        "experience_total": {"month": experience_total_month},
        "relocation": False,
        "remote": True,
        "compensation": {
            "value": compensation_value,
            "currency": compensation_currency,
        },
        "work_state": work_state,
        "age": age,
        "location": {"city": city, "country": "RU"},
        "experiences": experiences or [
            {
                "company": "ООО Тест",
                "position": "Python Developer",
                "period": "Январь 2020 — Декабрь 2023",
            }
        ],
        "educations": educations or [
            {
                "university": "МГУ",
                "faculty": "Прикладная математика",
                "start_date": "2015-09-01",
                "end_date": "2019-06-30",
            }
        ],
    }


def _make_response_item(
    response_id: str = "habr-resp-1",
    login: str = "alexsmirn",
    **user_kwargs,
) -> dict:
    """Конструктор мок-отклика Хабра (реальная структура по документации)."""
    return {
        "id": response_id,
        "vacancy_id": "habr-vac-001",
        "body": "Сопроводительное письмо",
        "favorite": False,
        "archived": False,
        "created_at": "2026-06-20T10:00:00Z",
        "user": _make_habr_user(login=login, **user_kwargs),
    }


# ---------------------------------------------------------------------------
# Тест маппера: _habr_response_user_to_normalized
# ---------------------------------------------------------------------------

class TestHabrResponseUserMapper:
    """Тест маппера response.user Хабра → нормализованный dict."""

    def test_basic_fields(self):
        user = _make_habr_user(
            name="Иванов Иван Сергеевич",
            specialization="Backend Developer",
            city="Санкт-Петербург",
        )
        result = _habr_response_user_to_normalized(user)
        # ФИО из name (первый токен = фамилия)
        assert result["last_name"] == "Иванов"
        assert result["first_name"] == "Иван"
        assert result["middle_name"] == "Сергеевич"
        assert result["city"] == "Санкт-Петербург"
        assert result["title"] == "Backend Developer"
        # Контакты ОТСУТСТВУЮТ в отклике
        assert result["phone"] is None
        assert result["email"] is None

    def test_no_contacts_in_response(self):
        """phone/email в отклике НЕТ — всегда None."""
        user = _make_habr_user()
        result = _habr_response_user_to_normalized(user)
        assert result["phone"] is None
        assert result["email"] is None

    def test_compensation_mapping(self):
        user = _make_habr_user(compensation_value=200000, compensation_currency="RUB")
        result = _habr_response_user_to_normalized(user)
        assert result["salary_from"] == 200000
        assert result["currency"] == "RUB"

    def test_skills_from_title(self):
        """Навыки извлекаются из skills[{title}]."""
        user = _make_habr_user(skills=[
            {"title": "Go", "alias_name": "golang"},
            {"title": "gRPC", "alias_name": "grpc"},
        ])
        result = _habr_response_user_to_normalized(user)
        assert "Go" in result["skill_set"]
        assert "gRPC" in result["skill_set"]

    def test_experiences_with_period(self):
        """Опыт с period-строкой (не дата)."""
        user = _make_habr_user(experiences=[
            {
                "company": "ООО Рога и Копыта",
                "position": "Senior Dev",
                "period": "Январь 2021 — Декабрь 2023",
            }
        ])
        result = _habr_response_user_to_normalized(user)
        assert len(result["experience"]) == 1
        exp = result["experience"][0]
        assert exp["position"] == "Senior Dev"
        assert exp["company"] == "ООО Рога и Копыта"
        # period сохраняется как description, start/end = None
        assert exp["description"] == "Январь 2021 — Декабрь 2023"
        assert exp["start"] is None
        assert exp["end"] is None

    def test_educations_mapping(self):
        """Образование из educations[{university, faculty, start_date, end_date}]."""
        user = _make_habr_user(educations=[
            {
                "university": "НГУ",
                "faculty": "Информационные технологии",
                "start_date": "2016-09-01",
                "end_date": "2020-06-30",
            }
        ])
        result = _habr_response_user_to_normalized(user)
        primary = result["education"]["primary"]
        assert len(primary) == 1
        assert primary[0]["name"] == "НГУ"
        assert primary[0]["organization"] == "Информационные технологии"
        assert primary[0]["year"] == "2020"  # из end_date[:4]

    def test_extra_data(self):
        """experience_total, work_state, age → в extra."""
        user = _make_habr_user(experience_total_month=48, work_state="ready", age=28)
        result = _habr_response_user_to_normalized(user)
        assert result["extra"]["experience_total_month"] == 48
        assert result["extra"]["work_state"] == "ready"
        assert result["extra"]["age"] == 28

    def test_empty_user_no_crash(self):
        """Пустой user → без исключений, все поля None/пусто."""
        result = _habr_response_user_to_normalized({})
        assert result["phone"] is None
        assert result["email"] is None
        assert result["first_name"] == ""
        assert result["last_name"] == ""
        assert result["skill_set"] == []


# ---------------------------------------------------------------------------
# Тест import_habr_response
# ---------------------------------------------------------------------------

class TestImportHabrResponse:
    """Тесты функции import_habr_response."""

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_creates_candidate_without_contacts(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Новый отклик → Candidate БЕЗ phone/email (контактов в отклике нет)."""
        item = _make_response_item(response_id="habr-resp-1", login="alexsmirn")

        result = await import_habr_response(
            db_session,
            admin_user.company_id,
            habr_vacancy,
            item,
            access_token="test-token",
        )
        await db_session.commit()

        assert result == "created"

        # Application существует
        app = (await db_session.execute(
            select(Application).where(
                Application.company_id == admin_user.company_id,
                Application.habr_response_id == "habr-resp-1",
            )
        )).scalar_one_or_none()
        assert app is not None
        assert app.stage == "response"
        assert app.vacancy_id == habr_vacancy.id

        # Кандидат: source='habr', external_id=login, БЕЗ телефона
        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand is not None
        assert cand.source == "habr"
        assert cand.company_id == admin_user.company_id
        assert cand.external_source == "habr"
        assert cand.external_id == "alexsmirn"
        # Контакты ОТСУТСТВУЮТ в отклике
        assert cand.phone is None
        assert cand.email is None
        # ФИО
        assert cand.last_name == "Смирнов"
        assert cand.first_name == "Алексей"

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_candidate_name_from_user_name(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """ФИО берётся из response.user.name (split по пробелам)."""
        item = _make_response_item(
            response_id="habr-resp-name",
            login="ivpetrov",
            name="Петров Иван Сергеевич",
        )

        await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()

        app = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-name")
        )).scalar_one_or_none()
        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand.last_name == "Петров"
        assert cand.first_name == "Иван"
        assert cand.middle_name == "Сергеевич"

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_dedup_by_login(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Дедуп по (external_source='habr', external_id=login): повтор login = тот же кандидат."""
        # Первый импорт
        item1 = _make_response_item(response_id="habr-resp-login-1", login="dupuser")
        await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item1, access_token="tok"
        )
        await db_session.commit()

        app1 = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-login-1")
        )).scalar_one_or_none()
        assert app1 is not None
        cand_id_1 = app1.candidate_id

        # Второй отклик от того же login (другая response id, та же вакансия)
        item2 = _make_response_item(response_id="habr-resp-login-2", login="dupuser")
        # Нужна вторая вакансия для уникального Application
        vac2 = Vacancy(
            company_id=admin_user.company_id,
            name="Вакансия 2",
            status="active",
            habr_vacancy_id="habr-vac-002",
        )
        db_session.add(vac2)
        await db_session.flush()

        await import_habr_response(
            db_session, admin_user.company_id, vac2, item2, access_token="tok"
        )
        await db_session.commit()

        app2 = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-login-2")
        )).scalar_one_or_none()
        assert app2 is not None
        # Application привязан к ТОМУ ЖЕ кандидату (дедуп по login)
        assert app2.candidate_id == cand_id_1

        # Только один кандидат с этим login
        cands = (await db_session.execute(
            select(Candidate).where(
                Candidate.company_id == admin_user.company_id,
                Candidate.external_source == "habr",
                Candidate.external_id == "dupuser",
            )
        )).scalars().all()
        assert len(cands) == 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_candidate_sections_created(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Секции резюме (опыт/навыки/образование) создаются из user.experiences/skills/educations."""
        item = _make_response_item(
            response_id="habr-resp-sections",
            login="sectionuser",
            experiences=[{
                "company": "X", "position": "Dev",
                "period": "Январь 2020 — Декабрь 2022",
            }],
            skills=[{"title": "Python"}, {"title": "FastAPI"}],
            educations=[{
                "university": "МГУ", "faculty": "ИТ",
                "start_date": "2015-09-01", "end_date": "2019-06-30",
            }],
        )

        await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()

        app = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-sections")
        )).scalar_one_or_none()
        assert app is not None

        from app.models import CandidateSkill, CandidateExperience
        skills = (await db_session.execute(
            select(CandidateSkill).where(CandidateSkill.candidate_id == app.candidate_id)
        )).scalars().all()
        assert len(skills) >= 1

        exps = (await db_session.execute(
            select(CandidateExperience).where(CandidateExperience.candidate_id == app.candidate_id)
        )).scalars().all()
        assert len(exps) >= 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_duplicate_response_not_duplicated(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Повторный import с тем же habr_response_id → без дубля Application (updated)."""
        item = _make_response_item(response_id="habr-resp-dedup-dup", login="dedupuser")

        r1 = await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()
        assert r1 == "created"

        r2 = await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()
        assert r2 == "updated"

        apps = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-dedup-dup")
        )).scalars().all()
        assert len(apps) == 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_company_isolation(
        self, mock_client, db_session: AsyncSession, admin_user, other_company, habr_vacancy
    ):
        """Отклик компании A не создаёт Application у компании B."""
        item = _make_response_item(response_id="habr-resp-isolation", login="isoluser")

        await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()

        # У компании B никаких Application нет
        apps_b = (await db_session.execute(
            select(Application).where(
                Application.company_id == other_company.id,
                Application.habr_response_id == "habr-resp-isolation",
            )
        )).scalars().all()
        assert len(apps_b) == 0

        # У компании A — есть
        apps_a = (await db_session.execute(
            select(Application).where(
                Application.company_id == admin_user.company_id,
                Application.habr_response_id == "habr-resp-isolation",
            )
        )).scalars().all()
        assert len(apps_a) == 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_raises_on_missing_id(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """response_item без поля id → ValueError (честно, не фейк-успех)."""
        item = {"user": _make_habr_user()}  # нет id

        with pytest.raises(ValueError, match="id"):
            await import_habr_response(
                db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
            )


# ---------------------------------------------------------------------------
# Тест poll_habr_responses_now
# ---------------------------------------------------------------------------

class TestPollHabrResponsesNow:
    """Тесты функции poll_habr_responses_now."""

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_imports_new_responses(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_vacancy
    ):
        """Базовый poll: новый отклик → Candidate(source='habr', phone=None) + Application."""
        mock_client.get_vacancy_responses = AsyncMock(return_value={
            "responses": [_make_response_item(response_id="habr-poll-1", login="polluser1")],
            "pagination": {"total": 1, "page": 1, "per": 50},
        })

        result = await poll_habr_responses_now(db_session, admin_user.company_id)
        await db_session.commit()

        assert result["imported"] == 1
        assert result["skipped"] == 0

        app = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-poll-1")
        )).scalar_one_or_none()
        assert app is not None

        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand.source == "habr"
        assert cand.company_id == admin_user.company_id
        # phone/email в отклике нет
        assert cand.phone is None
        assert cand.email is None
        assert cand.external_id == "polluser1"

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_uses_responses_key_not_items(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_vacancy
    ):
        """Ответ Хабра использует ключ 'responses', а не 'items'."""
        # Проверяем что структура {responses:[...], pagination:{...}} правильно разбирается
        mock_client.get_vacancy_responses = AsyncMock(return_value={
            "responses": [_make_response_item(response_id="habr-poll-responses-key", login="respkey")],
            "pagination": {"total": 1, "page": 1, "per": 50},
        })

        result = await poll_habr_responses_now(db_session, admin_user.company_id)
        await db_session.commit()

        assert result["imported"] == 1
        assert result["errors"] == []

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_skips_existing_responses(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_vacancy
    ):
        """Повторный poll с тем же response_id → skipped."""
        item = _make_response_item(response_id="habr-poll-skip", login="skipuser")

        mock_client.get_vacancy_responses = AsyncMock(return_value={
            "responses": [item],
            "pagination": {"total": 1, "page": 1, "per": 50},
        })

        r1 = await poll_habr_responses_now(db_session, admin_user.company_id)
        await db_session.commit()
        assert r1["imported"] == 1

        r2 = await poll_habr_responses_now(db_session, admin_user.company_id)
        await db_session.commit()
        assert r2["skipped"] == 1
        assert r2["imported"] == 0

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_no_vacancies_returns_empty(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration
    ):
        """Нет вакансий с habr_vacancy_id → vacancies=0, imported=0."""
        mock_client.get_vacancy_responses = AsyncMock(return_value={
            "responses": [], "pagination": {"total": 0, "page": 1, "per": 50}
        })

        result = await poll_habr_responses_now(db_session, admin_user.company_id)
        assert result["vacancies"] == 0
        assert result["imported"] == 0

    async def test_no_integration_raises_validation_error(
        self, db_session: AsyncSession, admin_user
    ):
        """Нет HabrIntegration → ValidationError честно, не 500/фейк."""
        with pytest.raises(ValidationError, match="не подключён"):
            await poll_habr_responses_now(db_session, admin_user.company_id)

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_expired_token_raises(
        self, mock_client, db_session: AsyncSession, admin_user
    ):
        """Истёкший токен → ValidationError."""
        integration = HabrIntegration(
            company_id=admin_user.company_id,
            access_token=encrypt_text("expired-token"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db_session.add(integration)
        await db_session.flush()

        with pytest.raises(ValidationError, match="[Тт]окен.*[Ии]стёк|истёк.*[Тт]окен"):
            await poll_habr_responses_now(db_session, admin_user.company_id)

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_api_error_returns_error_in_stats(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_vacancy
    ):
        """Ошибка Хабр API → ошибка в stats['errors'], не 500."""
        mock_client.get_vacancy_responses = AsyncMock(
            side_effect=ValueError("HTTP 403")
        )

        result = await poll_habr_responses_now(db_session, admin_user.company_id)
        assert len(result["errors"]) >= 1
        assert result["imported"] == 0


# ---------------------------------------------------------------------------
# Тест open_habr_contacts
# ---------------------------------------------------------------------------

class TestOpenHabrContacts:
    """Тесты функции open_habr_contacts (ПЛАТНЫЙ эндпоинт)."""

    @pytest_asyncio.fixture
    async def habr_candidate(self, db_session: AsyncSession, admin_user) -> Candidate:
        """Хабр-кандидат без контактов (как после import_habr_response)."""
        cand = Candidate(
            company_id=admin_user.company_id,
            first_name="Алексей",
            last_name="Смирнов",
            source="habr",
            external_source="habr",
            external_id="alexsmirn",
            phone=None,
            email=None,
        )
        db_session.add(cand)
        await db_session.flush()
        return cand

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_opens_contacts_and_sets_phone_email(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_candidate
    ):
        """Первое открытие: get_user_contacts вызван, phone normalize_phone, opened_at проставлен."""
        mock_client.get_user_contacts = AsyncMock(return_value={
            "phones": ["+7 999 123-45-67"],
            "emails": ["alex@example.com"],
        })

        result = await open_habr_contacts(
            db_session,
            company_id=admin_user.company_id,
            candidate_id=habr_candidate.id,
            user_id=admin_user.id,
        )
        await db_session.commit()

        assert result["merged"] is False
        assert result["already_opened"] is False
        assert result["candidate_id"] == str(habr_candidate.id)

        # Проверить кандидата в БД
        await db_session.refresh(habr_candidate)
        # Телефон нормализован (цифры без '+')
        assert habr_candidate.phone == "79991234567"
        assert habr_candidate.email == "alex@example.com"
        # habr_contacts_opened_at проставлен
        assert habr_candidate.habr_contacts_opened_at is not None

        # get_user_contacts вызван с login
        mock_client.get_user_contacts.assert_awaited_once_with("test-habr-access-token", "alexsmirn")

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_idempotent_no_second_call(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_candidate
    ):
        """ПОВТОРНЫЙ open-contacts → get_user_contacts НЕ вызван снова (не жжём лимит)."""
        mock_client.get_user_contacts = AsyncMock(return_value={
            "phones": ["+79991234567"],
            "emails": ["alex@example.com"],
        })

        # Первый вызов
        await open_habr_contacts(
            db_session,
            company_id=admin_user.company_id,
            candidate_id=habr_candidate.id,
            user_id=admin_user.id,
        )
        await db_session.commit()
        await db_session.refresh(habr_candidate)
        assert habr_candidate.habr_contacts_opened_at is not None

        # Второй вызов
        result2 = await open_habr_contacts(
            db_session,
            company_id=admin_user.company_id,
            candidate_id=habr_candidate.id,
            user_id=admin_user.id,
        )

        assert result2["already_opened"] is True
        # get_user_contacts вызван ТОЛЬКО один раз
        assert mock_client.get_user_contacts.await_count == 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_limit_error_raises_validation_error_not_mark_opened(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_candidate
    ):
        """Лимит/ошибка → ValidationError честно, opened_at НЕ проставлен."""
        mock_client.get_user_contacts = AsyncMock(
            side_effect=ValueError("HTTP 402 — лимит открытий исчерпан")
        )

        with pytest.raises(ValidationError, match="[Лл]имит"):
            await open_habr_contacts(
                db_session,
                company_id=admin_user.company_id,
                candidate_id=habr_candidate.id,
                user_id=admin_user.id,
            )

        # opened_at НЕ проставлен
        await db_session.refresh(habr_candidate)
        assert habr_candidate.habr_contacts_opened_at is None
        assert habr_candidate.phone is None

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_403_error_raises_validation_error(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_candidate
    ):
        """HTTP 403 (нет доступа) → ValidationError (не 500)."""
        mock_client.get_user_contacts = AsyncMock(
            side_effect=ValueError("HTTP 403 — нет доступа к базе резюме")
        )

        with pytest.raises(ValidationError, match="[Лл]имит"):
            await open_habr_contacts(
                db_session,
                company_id=admin_user.company_id,
                candidate_id=habr_candidate.id,
                user_id=admin_user.id,
            )

        await db_session.refresh(habr_candidate)
        assert habr_candidate.habr_contacts_opened_at is None

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_merge_with_existing_candidate(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration,
        habr_candidate, habr_vacancy
    ):
        """Дедуп-слияние: совпал с существующим → merged=True, хабр-кандидат soft-deleted."""
        # Существующий кандидат (другой источник) с тем же телефоном
        survivor = Candidate(
            company_id=admin_user.company_id,
            first_name="Существующий",
            last_name="Кандидат",
            phone="79991234567",
            email=None,
            source="direct",
        )
        db_session.add(survivor)
        await db_session.flush()

        # Заявка хабр-кандидата
        app = Application(
            company_id=admin_user.company_id,
            candidate_id=habr_candidate.id,
            vacancy_id=habr_vacancy.id,
            stage="response",
            habr_response_id="habr-resp-merge",
        )
        db_session.add(app)
        await db_session.flush()

        mock_client.get_user_contacts = AsyncMock(return_value={
            "phones": ["+79991234567"],
            "emails": ["alex@example.com"],
        })

        result = await open_habr_contacts(
            db_session,
            company_id=admin_user.company_id,
            candidate_id=habr_candidate.id,
            user_id=admin_user.id,
        )
        await db_session.commit()

        assert result["merged"] is True
        assert result["candidate_id"] == str(survivor.id)

        # Хабр-кандидат soft-deleted
        await db_session.refresh(habr_candidate)
        assert habr_candidate.deleted_at is not None

        # Заявка перенесена на survivor
        await db_session.refresh(app)
        assert app.candidate_id == survivor.id

    async def test_non_habr_candidate_raises(
        self, db_session: AsyncSession, admin_user, habr_integration
    ):
        """Кандидат не из Хабра → ValidationError."""
        manual_cand = Candidate(
            company_id=admin_user.company_id,
            first_name="Ручной",
            last_name="Кандидат",
            source="manual",
            external_source=None,
            external_id=None,
        )
        db_session.add(manual_cand)
        await db_session.flush()

        with pytest.raises(ValidationError, match="[Хх]абра"):
            await open_habr_contacts(
                db_session,
                company_id=admin_user.company_id,
                candidate_id=manual_cand.id,
                user_id=admin_user.id,
            )

    async def test_company_isolation_candidate_not_found(
        self, db_session: AsyncSession, admin_user, other_company, habr_integration
    ):
        """Кандидат другой компании → NotFoundError (изоляция company_id)."""
        from app.core.errors import NotFoundError

        cand_other = Candidate(
            company_id=other_company.id,
            first_name="Чужой",
            last_name="Кандидат",
            source="habr",
            external_source="habr",
            external_id="otherlogin",
        )
        db_session.add(cand_other)
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await open_habr_contacts(
                db_session,
                company_id=admin_user.company_id,  # не owner
                candidate_id=cand_other.id,
                user_id=admin_user.id,
            )


# ---------------------------------------------------------------------------
# Тест link_habr_vacancy / unlink_habr_vacancy
# ---------------------------------------------------------------------------

class TestLinkHabrVacancy:
    """Тесты привязки/отвязки вакансии к Хабру."""

    async def test_link_sets_habr_vacancy_id(
        self, db_session: AsyncSession, admin_user
    ):
        """link_habr_vacancy ставит habr_vacancy_id на вакансию."""
        vacancy = Vacancy(
            company_id=admin_user.company_id,
            name="Test Link Vac",
            status="active",
        )
        db_session.add(vacancy)
        await db_session.flush()

        await link_habr_vacancy(
            db_session,
            vacancy_id=vacancy.id,
            habr_vacancy_id="habr-new-123",
            company_id=admin_user.company_id,
            user_id=admin_user.id,
        )
        await db_session.commit()

        refreshed = await db_session.get(Vacancy, vacancy.id)
        assert refreshed.habr_vacancy_id == "habr-new-123"

    async def test_link_wrong_company_raises(
        self, db_session: AsyncSession, admin_user, other_company
    ):
        """link_habr_vacancy на вакансию чужой компании → NotFoundError."""
        from app.core.errors import NotFoundError

        vacancy = Vacancy(
            company_id=other_company.id,
            name="Чужая вакансия",
            status="active",
        )
        db_session.add(vacancy)
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await link_habr_vacancy(
                db_session,
                vacancy_id=vacancy.id,
                habr_vacancy_id="habr-123",
                company_id=admin_user.company_id,
                user_id=admin_user.id,
            )

    async def test_unlink_clears_habr_vacancy_id(
        self, db_session: AsyncSession, admin_user
    ):
        """unlink_habr_vacancy обнуляет habr_vacancy_id."""
        vacancy = Vacancy(
            company_id=admin_user.company_id,
            name="Test Unlink Vac",
            status="active",
            habr_vacancy_id="habr-to-unlink",
        )
        db_session.add(vacancy)
        await db_session.flush()

        await unlink_habr_vacancy(
            db_session,
            vacancy_id=vacancy.id,
            company_id=admin_user.company_id,
            user_id=admin_user.id,
        )
        await db_session.commit()

        refreshed = await db_session.get(Vacancy, vacancy.id)
        assert refreshed.habr_vacancy_id is None


# ---------------------------------------------------------------------------
# Тест get_valid_access_token_habr
# ---------------------------------------------------------------------------

class TestGetValidAccessTokenHabr:
    """Тесты получения валидного токена Хабра."""

    async def test_no_integration_raises(self, db_session: AsyncSession, admin_user):
        """Нет записи HabrIntegration → ValidationError."""
        with pytest.raises(ValidationError):
            await get_valid_access_token_habr(db_session, admin_user.company_id)

    async def test_valid_token_returned(
        self, db_session: AsyncSession, admin_user
    ):
        """Действующий токен возвращается корректно."""
        integration = HabrIntegration(
            company_id=admin_user.company_id,
            access_token=encrypt_text("valid-token-xyz"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        db_session.add(integration)
        await db_session.flush()

        token = await get_valid_access_token_habr(db_session, admin_user.company_id)
        assert token == "valid-token-xyz"

    async def test_expired_token_raises(self, db_session: AsyncSession, admin_user):
        """Истёкший токен → ValidationError (не 500)."""
        integration = HabrIntegration(
            company_id=admin_user.company_id,
            access_token=encrypt_text("old-token"),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db_session.add(integration)
        await db_session.flush()

        with pytest.raises(ValidationError, match="[Тт]окен"):
            await get_valid_access_token_habr(db_session, admin_user.company_id)

    async def test_no_expires_at_token_returned(
        self, db_session: AsyncSession, admin_user
    ):
        """Нет expires_at → токен возвращается (срок неизвестен, не блокируем)."""
        integration = HabrIntegration(
            company_id=admin_user.company_id,
            access_token=encrypt_text("no-expires-token"),
            expires_at=None,
        )
        db_session.add(integration)
        await db_session.flush()

        token = await get_valid_access_token_habr(db_session, admin_user.company_id)
        assert token == "no-expires-token"
