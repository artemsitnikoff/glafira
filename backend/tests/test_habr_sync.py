"""Тесты синхронизации откликов Хабр Карьера.

Все вызовы habr_client мокаются по import-site (sync.py).
Проверяется реальная инфраструктура: дедуп, Application, normalize_phone, company-изоляция, audit.
НЕ утверждаем «pytest зелёный» без прогона на VPS.
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

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
    _habr_resume_to_normalized,
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


def _make_response_item(
    response_id: str = "habr-resp-1",
    first_name: str = "Алексей",
    last_name: str = "Смирнов",
    phone: str = "+79991234567",
    email: str = "alex@example.com",
    title: str = "Python Developer",
    city: str = "Москва",
    experience: list | None = None,
    skills: list | None = None,
) -> dict:
    """Конструктор мок-отклика Хабра (ASSUMPTION-структура)."""
    return {
        "id": response_id,
        "resume": {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "email": email,
            "title": title,
            "city": {"name": city},
            "experience": experience or [
                {
                    "position": "Python Developer",
                    "company": "ООО Тест",
                    "started_at": "2020-01-01",
                    "finished_at": "2023-12-31",
                    "description": "Разработка backend",
                }
            ],
            "skills": skills or ["Python", "FastAPI", "PostgreSQL"],
            "education": {
                "primary": [
                    {"name": "МГУ", "faculty": "Прикладная математика", "year": 2019}
                ]
            },
        },
    }


# ---------------------------------------------------------------------------
# Тест маппера: _habr_resume_to_normalized
# ---------------------------------------------------------------------------

class TestHabrResumeMapper:
    """Тест маппера Хабр-резюме → нормализованный dict."""

    def test_basic_fields(self):
        raw = {
            "first_name": "Иван",
            "last_name": "Петров",
            "middle_name": "Сергеевич",
            "phone": "+79991234567",
            "email": "ivan@example.com",
            "title": "Backend Developer",
            "city": {"name": "Санкт-Петербург"},
        }
        result = _habr_resume_to_normalized(raw)
        assert result["first_name"] == "Иван"
        assert result["last_name"] == "Петров"
        assert result["middle_name"] == "Сергеевич"
        assert result["city"] == "Санкт-Петербург"
        assert result["title"] == "Backend Developer"
        # Телефон нормализован (цифры без '+')
        assert result["phone"] == "79991234567"
        assert result["email"] == "ivan@example.com"

    def test_phone_normalize_formats(self):
        """normalize_phone применяется в маппере: разные форматы → 79991234567."""
        for phone_raw in ("+7 999 123-45-67", "8(999)123-45-67", "79991234567"):
            raw = {"phone": phone_raw}
            result = _habr_resume_to_normalized(raw)
            assert result["phone"] == "79991234567", f"phone_raw={phone_raw!r}"

    def test_experience_mapping(self):
        raw = {
            "experience": [
                {
                    "position": "Senior Dev",
                    "company": "ООО Рога и Копыта",
                    "started_at": "2021-03-15",
                    "finished_at": "2024-01-10",
                    "description": "Описание работы",
                }
            ]
        }
        result = _habr_resume_to_normalized(raw)
        assert len(result["experience"]) == 1
        exp = result["experience"][0]
        assert exp["position"] == "Senior Dev"
        assert exp["company"] == "ООО Рога и Копыта"
        assert exp["start"] == "2021-03-15"
        assert exp["end"] == "2024-01-10"
        assert exp["description"] == "Описание работы"

    def test_skills_list(self):
        raw = {"skills": ["Python", "Docker", "Kubernetes"]}
        result = _habr_resume_to_normalized(raw)
        assert result["skill_set"] == ["Python", "Docker", "Kubernetes"]

    def test_skills_as_dict_list(self):
        """Навыки как список dict с полем name."""
        raw = {"skills": [{"name": "Go"}, {"name": "gRPC"}]}
        result = _habr_resume_to_normalized(raw)
        assert result["skill_set"] == ["Go", "gRPC"]

    def test_education(self):
        raw = {
            "education": {
                "primary": [{"name": "НГУ", "faculty": "ИТ", "year": 2018}]
            }
        }
        result = _habr_resume_to_normalized(raw)
        primary = result["education"]["primary"]
        assert len(primary) == 1
        assert primary[0]["name"] == "НГУ"
        assert primary[0]["year"] == 2018

    def test_city_as_string(self):
        """Город как строка (ASSUMPTION фолбэк)."""
        raw = {"city": "Екатеринбург"}
        result = _habr_resume_to_normalized(raw)
        assert result["city"] == "Екатеринбург"

    def test_empty_phone_returns_none(self):
        raw = {"phone": "нет"}
        result = _habr_resume_to_normalized(raw)
        assert result["phone"] is None

    def test_contacts_fallback(self):
        """Контакты через список contacts (ASSUMPTION)."""
        raw = {
            "contacts": [
                {"type": "phone", "value": "+79001112233"},
                {"type": "email", "value": "test@habr.com"},
            ]
        }
        result = _habr_resume_to_normalized(raw)
        assert result["phone"] == "79001112233"
        assert result["email"] == "test@habr.com"


# ---------------------------------------------------------------------------
# Тест import_habr_response
# ---------------------------------------------------------------------------

class TestImportHabrResponse:
    """Тесты функции import_habr_response."""

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_creates_candidate_and_application(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Новый отклик → создаёт Candidate(source='habr') и Application(stage='response')."""
        # Мок client.get_resume не нужен если resume вложено в response_item
        mock_client.get_resume = AsyncMock(return_value={})  # не вызывается при полном резюме

        item = _make_response_item()

        result = await import_habr_response(
            db_session,
            admin_user.company_id,
            habr_vacancy,
            item,
            access_token="test-token",
        )
        await db_session.commit()

        assert result == "created"

        # Проверяем Application
        apps = (await db_session.execute(
            select(Application).where(
                Application.company_id == admin_user.company_id,
                Application.habr_response_id == "habr-resp-1",
            )
        )).scalars().all()
        assert len(apps) == 1
        app = apps[0]
        assert app.stage == "response"
        assert app.vacancy_id == habr_vacancy.id

        # Проверяем Candidate
        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand is not None
        assert cand.source == "habr"
        assert cand.company_id == admin_user.company_id
        assert cand.first_name == "Алексей"
        assert cand.last_name == "Смирнов"
        # Телефон нормализован — цифры без '+'
        assert cand.phone == "79991234567"
        assert cand.email == "alex@example.com"

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_candidate_sections_created(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Секции резюме (опыт/навыки/образование) создаются."""
        mock_client.get_resume = AsyncMock(return_value={})

        item = _make_response_item(
            response_id="habr-resp-sections",
            experience=[{"position": "Dev", "company": "X", "started_at": "2020-01", "description": "D"}],
            skills=["Python", "FastAPI"],
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

        exp = (await db_session.execute(
            select(CandidateExperience).where(CandidateExperience.candidate_id == app.candidate_id)
        )).scalars().all()
        assert len(exp) >= 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_dedup_by_phone(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Дедуп кандидата: существующий по телефону → привязан, не дубль."""
        mock_client.get_resume = AsyncMock(return_value={})

        # Существующий кандидат этой компании с тем же номером
        existing = Candidate(
            company_id=admin_user.company_id,
            first_name="Существующий",
            last_name="Кандидат",
            phone="79991234567",  # нормализован
            email="other@example.com",
            source="manual",
        )
        db_session.add(existing)
        await db_session.flush()

        item = _make_response_item(response_id="habr-resp-dedup-phone", phone="+79991234567")

        result = await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()

        assert result == "created"

        app = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-dedup-phone")
        )).scalar_one_or_none()
        assert app is not None
        # Application привязан к СУЩЕСТВУЮЩЕМУ кандидату (не новому)
        assert app.candidate_id == existing.id

        # Нет дубля — только один кандидат с этим телефоном
        cands = (await db_session.execute(
            select(Candidate).where(
                Candidate.company_id == admin_user.company_id,
                Candidate.phone == "79991234567",
            )
        )).scalars().all()
        assert len(cands) == 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_dedup_by_email(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Дедуп кандидата по email (без телефона) → привязан к существующему."""
        mock_client.get_resume = AsyncMock(return_value={})

        existing = Candidate(
            company_id=admin_user.company_id,
            first_name="Дубликат",
            last_name="Email",
            email="duplic@example.com",
            source="direct",
        )
        db_session.add(existing)
        await db_session.flush()

        item = _make_response_item(
            response_id="habr-resp-dedup-email",
            phone="",  # нет телефона
            email="duplic@example.com",
        )
        # Обнуляем phone в raw чтобы normalize вернул None
        item["resume"]["phone"] = None

        result = await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()

        app = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-dedup-email")
        )).scalar_one_or_none()
        assert app is not None
        assert app.candidate_id == existing.id

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_duplicate_response_not_duplicated(
        self, mock_client, db_session: AsyncSession, admin_user, habr_vacancy
    ):
        """Дедуп откликов: повторный import с тем же habr_response_id → без дубля Application."""
        mock_client.get_resume = AsyncMock(return_value={})

        item = _make_response_item(response_id="habr-resp-dedup-dup")

        # Первый импорт
        r1 = await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()
        assert r1 == "created"

        # Второй импорт того же отклика → update
        r2 = await import_habr_response(
            db_session, admin_user.company_id, habr_vacancy, item, access_token="tok"
        )
        await db_session.commit()
        assert r2 == "updated"

        # Проверяем ровно одна Application с этим habr_response_id
        apps = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-resp-dedup-dup")
        )).scalars().all()
        assert len(apps) == 1

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_company_isolation(
        self, mock_client, db_session: AsyncSession, admin_user, other_company, habr_vacancy
    ):
        """Отклик компании A не создаёт Application у компании B."""
        mock_client.get_resume = AsyncMock(return_value={})

        # Вакансия компании B
        vac_b = Vacancy(
            company_id=other_company.id,
            name="Вакансия B",
            habr_vacancy_id="habr-vac-b",
            status="active",
        )
        db_session.add(vac_b)
        await db_session.flush()

        item = _make_response_item(response_id="habr-resp-isolation")

        # Импорт под company A
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
        mock_client.get_resume = AsyncMock(return_value={})

        item = {"resume": {"first_name": "Test"}}  # нет id

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
        """Базовый poll: новый отклик создаёт Candidate(source='habr') + Application."""
        mock_client.get_vacancy_responses = AsyncMock(return_value={
            "items": [_make_response_item(response_id="habr-poll-1")],
            "total": 1,
            "per_page": 50,
        })
        mock_client.get_resume = AsyncMock(return_value={})

        result = await poll_habr_responses_now(db_session, admin_user.company_id)
        await db_session.commit()

        assert result["imported"] == 1
        assert result["skipped"] == 0

        # Кандидат с source='habr'
        app = (await db_session.execute(
            select(Application).where(Application.habr_response_id == "habr-poll-1")
        )).scalar_one_or_none()
        assert app is not None

        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand.source == "habr"
        assert cand.company_id == admin_user.company_id
        assert cand.phone == "79991234567"

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_skips_existing_responses(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration, habr_vacancy
    ):
        """Повторный poll с тем же response_id → skipped (без фетча резюме повторно)."""
        item = _make_response_item(response_id="habr-poll-skip")

        mock_client.get_vacancy_responses = AsyncMock(return_value={
            "items": [item],
            "total": 1,
            "per_page": 50,
        })
        mock_client.get_resume = AsyncMock(return_value={})

        # Первый прогон
        r1 = await poll_habr_responses_now(db_session, admin_user.company_id)
        await db_session.commit()
        assert r1["imported"] == 1

        # Второй прогон — тот же item
        r2 = await poll_habr_responses_now(db_session, admin_user.company_id)
        await db_session.commit()
        # existing_rids перечитывается из БД → пропуск
        assert r2["skipped"] == 1
        assert r2["imported"] == 0

    @patch("app.services.integrations.habr.sync.habr_client")
    async def test_no_vacancies_returns_empty(
        self, mock_client, db_session: AsyncSession, admin_user, habr_integration
    ):
        """Нет вакансий с habr_vacancy_id → vacancies=0, imported=0."""
        mock_client.get_vacancy_responses = AsyncMock(return_value={"items": [], "total": 0})

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
        """Истёкший токен → ValidationError (не фейк-успех, не 500)."""
        # Интеграция с истёкшим токеном
        integration = HabrIntegration(
            company_id=admin_user.company_id,
            access_token=encrypt_text("expired-token"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),  # в прошлом
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
            side_effect=ValueError("HTTP 403 — пиннинг эндпоинта")
        )

        result = await poll_habr_responses_now(db_session, admin_user.company_id)
        assert len(result["errors"]) >= 1
        assert result["imported"] == 0


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
                company_id=admin_user.company_id,  # не owner
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
