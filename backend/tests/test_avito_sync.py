"""Тесты синхронизации откликов Авито Работа.

Все вызовы avito_client мокаются по import-site (sync.py).
Проверяется реальная инфраструктура: дедуп, Application, normalize_phone, company-изоляция, audit.

Структура мок-отклика строго по Swagger Авито Job API:
  apply: {
    id, vacancy_id, created_at, state,
    applicant: {
      data: {first_name, last_name, patronymic, birthday, citizenship, education, gender},
      resume_id
    },
    contacts: {phones: [{value}], chat: {value}},
    enriched_properties: {phone: {value}, experience, age, citizenship}
  }

Телефон: contacts.phones[].value (72002000014) ИЛИ enriched_properties.phone.value (+79213223344).
⚠️ НЕ утверждаем «pytest зелёный» без прогона на VPS.
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Vacancy, Application, Candidate
from app.models.avito_integration import AvitoIntegration
from app.services.integrations.avito import sync as avito_sync
from app.services.integrations.avito.sync import (
    import_avito_application,
    poll_avito_responses_now,
    _avito_application_to_normalized,
    _enrich_normalized_from_resume_v2,
)
from app.services.integrations.avito import service as avito_service
from app.services.settings.crypto import encrypt_text
from app.core.errors import ValidationError


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def avito_vacancy(db_session: AsyncSession, admin_user) -> Vacancy:
    """Вакансия с привязанным avito_vacancy_id."""
    v = Vacancy(
        company_id=admin_user.company_id,
        name="Backend Developer (Авито)",
        status="active",
        avito_vacancy_id="avito-vac-001",
    )
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)
    return v


@pytest_asyncio.fixture
async def avito_integration(db_session: AsyncSession, admin_user) -> AvitoIntegration:
    """AvitoIntegration с credentials и кэшированным токеном."""
    integration = AvitoIntegration(
        company_id=admin_user.company_id,
        client_id=encrypt_text("test-client-id"),
        client_secret=encrypt_text("test-client-secret"),
        access_token=encrypt_text("test-avito-access-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(integration)
    await db_session.commit()
    await db_session.refresh(integration)
    return integration


def _make_avito_apply(
    apply_id: str = "avito-app-1",
    vacancy_id: str = "avito-vac-001",
    first_name: str = "Иван",
    last_name: str = "Петров",
    patronymic: str = "Сергеевич",
    phone_contacts: str | None = "72002000014",
    phone_enriched: str | None = None,
    resume_id: str | None = "resume-001",
    age: int | None = 30,
    experience: str | None = "3 года",
) -> dict:
    """Конструктор мок-отклика Авито (реальная структура из Swagger Job API)."""
    contacts_phones = []
    if phone_contacts:
        contacts_phones = [{"value": phone_contacts}]

    enriched_phone: dict = {}
    if phone_enriched:
        enriched_phone = {"value": phone_enriched}

    apply = {
        "id": apply_id,
        "vacancy_id": vacancy_id,
        "created_at": "2026-06-20T10:00:00Z",
        "state": "active",
        "applicant": {
            "data": {
                "first_name": first_name,
                "last_name": last_name,
                "patronymic": patronymic,
                "birthday": "1995-01-15",
                "citizenship": "RU",
                "education": "higher",
                "gender": "male",
            },
            "resume_id": resume_id,
        },
        "contacts": {
            "phones": contacts_phones,
            "chat": {"value": "https://avito.ru/chat/123"},
        },
        "enriched_properties": {
            "phone": enriched_phone,
            "experience": experience,
            "age": age,
            "citizenship": "RU",
        },
    }
    return apply


def _make_resume_v2(
    experience_list: list | None = None,
    education_list: list | None = None,
    salary_amount: int | None = None,
    salary_currency: str = "RUB",
    description: str = "",
) -> dict:
    """Конструктор мок-резюме v2 (GET /job/v2/resumes/{id})."""
    return {
        "experience_list": experience_list or [
            {
                "work_start": "2020-01",
                "work_finish": "2023-12",
                "company": "ООО Тест",
                "position": "Python Developer",
                "responsibilities": "Разработка backend-сервисов",
            }
        ],
        "education_list": education_list or [
            {
                "name": "МГУ",
                "faculty": "Прикладная математика",
                "specialization": "Информационные системы",
                "year_of_graduation": 2019,
            }
        ],
        "language_list": [{"language": "russian", "proficiency": "native"}],
        "salary": {"amount": salary_amount, "currency": salary_currency} if salary_amount else None,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Тесты маппера _avito_application_to_normalized
# ---------------------------------------------------------------------------

class TestAvitoApplicationMapper:
    """Тест маппера Авито-отклика → нормализованный dict."""

    def test_basic_fields_fio_phone(self):
        """ФИО и телефон из contacts.phones[].value (72002000014)."""
        apply = _make_avito_apply(
            first_name="Мария",
            last_name="Иванова",
            patronymic="Юрьевна",
            phone_contacts="72002000014",
        )
        result = _avito_application_to_normalized(apply)
        assert result["first_name"] == "Мария"
        assert result["last_name"] == "Иванова"
        assert result["middle_name"] == "Юрьевна"
        # normalize_phone('72002000014') → '72002000014' (уже 11 цифр, первая 7)
        assert result["phone"] == "72002000014"

    def test_phone_from_contacts_format_plus_seven(self):
        """Телефон в формате +79213223344 из contacts.phones нормализуется корректно."""
        apply = _make_avito_apply(phone_contacts="+79213223344", phone_enriched=None)
        result = _avito_application_to_normalized(apply)
        assert result["phone"] == "79213223344"

    def test_phone_fallback_to_enriched_properties(self):
        """Если contacts.phones пуст — берём enriched_properties.phone.value."""
        apply = _make_avito_apply(phone_contacts=None, phone_enriched="+79213223344")
        result = _avito_application_to_normalized(apply)
        assert result["phone"] == "79213223344"

    def test_no_phone_both_empty(self):
        """Оба источника пусты → phone=None."""
        apply = _make_avito_apply(phone_contacts=None, phone_enriched=None)
        result = _avito_application_to_normalized(apply)
        assert result["phone"] is None

    def test_email_always_none(self):
        """email в отклике Авито отсутствует — всегда None."""
        apply = _make_avito_apply()
        result = _avito_application_to_normalized(apply)
        assert result["email"] is None

    def test_resume_id_extracted(self):
        """resume_id берётся из applicant.resume_id."""
        apply = _make_avito_apply(resume_id="my-resume-777")
        result = _avito_application_to_normalized(apply)
        assert result["resume_id"] == "my-resume-777"

    def test_extra_age_experience(self):
        """age, avito_experience, citizenship из enriched_properties → extra."""
        apply = _make_avito_apply(age=28, experience="5 лет")
        result = _avito_application_to_normalized(apply)
        assert result["extra"]["age"] == 28
        assert result["extra"]["avito_experience"] == "5 лет"
        assert result["extra"]["citizenship"] == "RU"

    def test_empty_apply_no_crash(self):
        """Пустой отклик → без исключений, все поля None/пусто."""
        result = _avito_application_to_normalized({})
        assert result["first_name"] == ""
        assert result["last_name"] == ""
        assert result["phone"] is None
        assert result["email"] is None
        assert result["resume_id"] is None


class TestEnrichFromResumeV2:
    """Тест обогащения нормализованного dict из резюме v2."""

    def test_experience_list_mapped(self):
        """experience_list[{work_start, position, company, responsibilities}] → experience."""
        normalized = {"experience": [], "education": {"primary": []}, "title": None,
                      "salary_from": None, "currency": "RUB"}
        resume = _make_resume_v2(experience_list=[{
            "work_start": "2021-01",
            "work_finish": "2024-03",
            "company": "ООО АИ",
            "position": "ML Engineer",
            "responsibilities": "Обучение моделей",
        }])
        result = _enrich_normalized_from_resume_v2(normalized, resume)
        assert len(result["experience"]) == 1
        exp = result["experience"][0]
        assert exp["position"] == "ML Engineer"
        assert exp["company"] == "ООО АИ"
        assert exp["start"] == "2021-01"
        assert exp["end"] == "2024-03"
        assert "Обучение" in exp["description"]

    def test_education_list_mapped(self):
        """education_list → education.primary с name/organization/year."""
        normalized = {"experience": [], "education": {"primary": []}, "title": None,
                      "salary_from": None, "currency": "RUB"}
        resume = _make_resume_v2(education_list=[{
            "name": "НГУ",
            "faculty": "ПМ",
            "specialization": "ИС",
            "year_of_graduation": 2020,
        }])
        result = _enrich_normalized_from_resume_v2(normalized, resume)
        primary = result["education"]["primary"]
        assert len(primary) == 1
        assert primary[0]["name"] == "НГУ"
        assert primary[0]["year"] == "2020"

    def test_salary_mapped(self):
        """salary.amount/currency → salary_from, currency."""
        normalized = {"experience": [], "education": {"primary": []}, "title": None,
                      "salary_from": None, "currency": "RUB"}
        resume = _make_resume_v2(salary_amount=150000, salary_currency="RUB")
        result = _enrich_normalized_from_resume_v2(normalized, resume)
        assert result["salary_from"] == 150000
        assert result["currency"] == "RUB"


# ---------------------------------------------------------------------------
# Тесты import_avito_application
# ---------------------------------------------------------------------------

class TestImportAvitoApplication:
    """Тесты функции import_avito_application."""

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_creates_candidate_with_phone(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Новый отклик → Candidate с телефоном из contacts.phones (БЕСПЛАТНО)."""
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())
        apply = _make_avito_apply(
            apply_id="avito-app-test-1",
            phone_contacts="72002000014",
        )

        result = await import_avito_application(
            db_session,
            admin_user.company_id,
            avito_vacancy,
            apply,
            access_token="test-token",
        )
        await db_session.commit()

        assert result == "created"

        # Application создан
        app = (await db_session.execute(
            select(Application).where(
                Application.company_id == admin_user.company_id,
                Application.avito_application_id == "avito-app-test-1",
            )
        )).scalar_one_or_none()
        assert app is not None
        assert app.stage == "response"
        assert app.vacancy_id == avito_vacancy.id

        # Кандидат: source='avito', phone нормализован
        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand is not None
        assert cand.source == "avito"
        assert cand.company_id == admin_user.company_id
        assert cand.external_source == "avito"
        # normalize_phone('72002000014') → '72002000014'
        assert cand.phone == "72002000014"
        assert cand.first_name == "Иван"
        assert cand.last_name == "Петров"

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_phone_format_plus_seven(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Телефон +79213223344 из contacts.phones нормализуется → 79213223344."""
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())
        apply = _make_avito_apply(
            apply_id="avito-app-phone-plus",
            phone_contacts="+79213223344",
            phone_enriched=None,
        )

        await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()

        app = (await db_session.execute(
            select(Application).where(Application.avito_application_id == "avito-app-phone-plus")
        )).scalar_one_or_none()
        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand.phone == "79213223344"

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_phone_from_enriched_properties(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Телефон из enriched_properties.phone.value (+79213223344) — запасной источник."""
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())
        apply = _make_avito_apply(
            apply_id="avito-app-enriched-phone",
            phone_contacts=None,        # contacts.phones пуст
            phone_enriched="+79213223344",  # берём отсюда
        )

        await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()

        app = (await db_session.execute(
            select(Application).where(Application.avito_application_id == "avito-app-enriched-phone")
        )).scalar_one_or_none()
        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand.phone == "79213223344"

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_resume_v2_enrichment_sections(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Обогащение из resume v2: секции опыт/образование создаются."""
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2(
            experience_list=[{
                "work_start": "2022-01", "work_finish": "2024-12",
                "company": "ООО X", "position": "Backend Dev",
                "responsibilities": "FastAPI + PostgreSQL",
            }],
            education_list=[{
                "name": "МГУ", "faculty": "ПМ",
                "specialization": "ИС", "year_of_graduation": 2021,
            }],
        ))
        apply = _make_avito_apply(apply_id="avito-app-sections", resume_id="resume-sections-1")

        await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()

        app = (await db_session.execute(
            select(Application).where(Application.avito_application_id == "avito-app-sections")
        )).scalar_one_or_none()

        from app.models import CandidateExperience, CandidateEducation
        exps = (await db_session.execute(
            select(CandidateExperience).where(CandidateExperience.candidate_id == app.candidate_id)
        )).scalars().all()
        assert len(exps) >= 1
        assert exps[0].position == "Backend Dev"

        edus = (await db_session.execute(
            select(CandidateEducation).where(CandidateEducation.candidate_id == app.candidate_id)
        )).scalars().all()
        assert len(edus) >= 1

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_resume_v2_failure_does_not_crash(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Сбой get_resume_v2 → best-effort, Application всё равно создаётся."""
        mock_client.get_resume_v2 = AsyncMock(side_effect=ValueError("HTTP 500 Авито упал"))
        apply = _make_avito_apply(apply_id="avito-app-v2fail", resume_id="resume-fail")

        result = await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()

        assert result == "created"
        app = (await db_session.execute(
            select(Application).where(Application.avito_application_id == "avito-app-v2fail")
        )).scalar_one_or_none()
        assert app is not None

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_dedup_candidate_by_phone(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Дедуп кандидата: существующий с тем же телефоном → привязать (не создавать дубля)."""
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())

        # Существующий кандидат с тем же телефоном
        existing_cand = Candidate(
            company_id=admin_user.company_id,
            first_name="Существующий",
            last_name="Кандидат",
            source="direct",
            phone="79213223344",
        )
        db_session.add(existing_cand)
        await db_session.flush()

        apply = _make_avito_apply(
            apply_id="avito-app-dedup",
            phone_contacts="+79213223344",  # normalize → 79213223344
        )

        result = await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()

        assert result == "created"
        app = (await db_session.execute(
            select(Application).where(Application.avito_application_id == "avito-app-dedup")
        )).scalar_one_or_none()
        assert app is not None
        # Application привязан к СУЩЕСТВУЮЩЕМУ кандидату (не новый дубль)
        assert app.candidate_id == existing_cand.id

        # Новый Candidate НЕ создавался
        cands = (await db_session.execute(
            select(Candidate).where(
                Candidate.company_id == admin_user.company_id,
                Candidate.phone == "79213223344",
            )
        )).scalars().all()
        assert len(cands) == 1

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_dedup_application_by_avito_application_id(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Дедуп отклика: повторный import с тем же avito_application_id → 'updated', не дубль."""
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())
        apply = _make_avito_apply(apply_id="avito-app-dupapp")

        r1 = await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()
        assert r1 == "created"

        r2 = await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()
        assert r2 == "updated"

        apps = (await db_session.execute(
            select(Application).where(Application.avito_application_id == "avito-app-dupapp")
        )).scalars().all()
        assert len(apps) == 1

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_company_isolation(
        self, mock_client, db_session: AsyncSession, admin_user, other_company, avito_vacancy
    ):
        """Отклик компании A не создаёт Application у компании B."""
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())
        apply = _make_avito_apply(apply_id="avito-app-isolation")

        await import_avito_application(
            db_session, admin_user.company_id, avito_vacancy, apply,
            access_token="tok",
        )
        await db_session.commit()

        # Компания B — пусто
        apps_b = (await db_session.execute(
            select(Application).where(
                Application.company_id == other_company.id,
                Application.avito_application_id == "avito-app-isolation",
            )
        )).scalars().all()
        assert len(apps_b) == 0

        # Компания A — есть
        apps_a = (await db_session.execute(
            select(Application).where(
                Application.company_id == admin_user.company_id,
                Application.avito_application_id == "avito-app-isolation",
            )
        )).scalars().all()
        assert len(apps_a) == 1

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_raises_on_missing_id(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Отклик без поля id → ValueError (честно, не фейк-успех)."""
        apply = {"vacancy_id": "avito-vac-001", "applicant": {"data": {}}}

        with pytest.raises(ValueError, match="id"):
            await import_avito_application(
                db_session, admin_user.company_id, avito_vacancy, apply,
                access_token="tok",
            )


# ---------------------------------------------------------------------------
# Тесты poll_avito_responses_now
# ---------------------------------------------------------------------------

class TestPollAvitoResponsesNow:
    """Тесты функции poll_avito_responses_now."""

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_basic_poll_imports_with_phone(
        self, mock_client, db_session: AsyncSession, admin_user,
        avito_integration, avito_vacancy
    ):
        """Базовый poll: новый отклик → Candidate(source='avito', phone=нормализован) + Application."""
        apply = _make_avito_apply(
            apply_id="avito-poll-1",
            vacancy_id="avito-vac-001",
            phone_contacts="72002000014",
        )
        mock_client.get_application_ids = AsyncMock(return_value={
            "applies": [{"id": "avito-poll-1", "state": "active",
                         "created_at": "2026-06-20T10:00:00Z",
                         "updated_at": "2026-06-20T10:00:00Z"}],
            "cursor": None,
        })
        mock_client.get_applications_by_ids = AsyncMock(return_value={
            "applies": [apply],
        })
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())

        result = await poll_avito_responses_now(db_session, admin_user.company_id)
        await db_session.commit()

        assert result["imported"] == 1
        assert result["skipped"] == 0

        app = (await db_session.execute(
            select(Application).where(Application.avito_application_id == "avito-poll-1")
        )).scalar_one_or_none()
        assert app is not None
        assert app.stage == "response"

        cand = await db_session.get(Candidate, app.candidate_id)
        assert cand.source == "avito"
        assert cand.company_id == admin_user.company_id
        assert cand.phone == "72002000014"

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_skips_existing_application_ids(
        self, mock_client, db_session: AsyncSession, admin_user,
        avito_integration, avito_vacancy
    ):
        """Повторный poll с тем же avito_application_id → skipped (дедуп set)."""
        apply = _make_avito_apply(apply_id="avito-poll-skip", vacancy_id="avito-vac-001")

        mock_client.get_application_ids = AsyncMock(return_value={
            "applies": [{"id": "avito-poll-skip", "state": "active",
                         "created_at": "2026-06-20T10:00:00Z",
                         "updated_at": "2026-06-20T10:00:00Z"}],
            "cursor": None,
        })
        mock_client.get_applications_by_ids = AsyncMock(return_value={"applies": [apply]})
        mock_client.get_resume_v2 = AsyncMock(return_value=_make_resume_v2())

        r1 = await poll_avito_responses_now(db_session, admin_user.company_id)
        await db_session.commit()
        assert r1["imported"] == 1

        # Сколько заявок в БД после первого poll
        count_after_first = len((await db_session.execute(
            select(Application).where(Application.company_id == admin_user.company_id)
        )).scalars().all())

        # Второй poll — тот же id уже в existing_aids → отсекается ДО батча
        # (sync.py:546: `aid not in existing_aids`), поэтому резюме повторно не фетчится
        # и новых заявок не создаётся. Прод-корректный сигнал дедупа: imported == 0
        # и общее число заявок в БД не изменилось.
        r2 = await poll_avito_responses_now(db_session, admin_user.company_id)
        await db_session.commit()
        assert r2["imported"] == 0

        count_after_second = len((await db_session.execute(
            select(Application).where(Application.company_id == admin_user.company_id)
        )).scalars().all())
        assert count_after_second == count_after_first  # дедуп: новых заявок нет

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_no_vacancies_returns_zero(
        self, mock_client, db_session: AsyncSession, admin_user, avito_integration
    ):
        """Нет вакансий с avito_vacancy_id → vacancies=0, imported=0 (без вызова API)."""
        result = await poll_avito_responses_now(db_session, admin_user.company_id)
        assert result["vacancies"] == 0
        assert result["imported"] == 0
        mock_client.get_application_ids.assert_not_called()

    async def test_no_integration_raises_validation_error(
        self, db_session: AsyncSession, admin_user
    ):
        """Нет AvitoIntegration → ValidationError честно, не 500."""
        with pytest.raises(ValidationError, match="[Аа]вито"):
            await poll_avito_responses_now(db_session, admin_user.company_id)

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_api_error_in_get_ids_returns_error_in_stats(
        self, mock_client, db_session: AsyncSession, admin_user,
        avito_integration, avito_vacancy
    ):
        """Ошибка get_application_ids → error в stats, не 500."""
        mock_client.get_application_ids = AsyncMock(
            side_effect=ValueError("HTTP 503")
        )

        result = await poll_avito_responses_now(db_session, admin_user.company_id)
        assert len(result["errors"]) >= 1
        assert result["imported"] == 0

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_token_cached_no_second_token_call(
        self, mock_client, db_session: AsyncSession, admin_user,
        avito_integration, avito_vacancy
    ):
        """Токен кэширован (expires_at в будущем) → get_access_token НЕ вызывается."""
        mock_client.get_application_ids = AsyncMock(return_value={"applies": [], "cursor": None})

        # Патчируем клиент токена (должен НЕ вызываться при валидном кэше)
        with patch("app.services.integrations.avito.service.avito_client") as mock_token_client:
            mock_token_client.get_access_token = AsyncMock(
                return_value={"access_token": "new-token", "expires_in": 3600}
            )
            await poll_avito_responses_now(db_session, admin_user.company_id)

        # get_access_token НЕ должен вызываться (токен в кэше валиден)
        mock_token_client.get_access_token.assert_not_called()

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_expired_token_triggers_refresh(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Токен истёк → автоматически получаем новый через client_credentials."""
        # Интеграция с истёкшим токеном
        integration = AvitoIntegration(
            company_id=admin_user.company_id,
            client_id=encrypt_text("expired-client-id"),
            client_secret=encrypt_text("expired-client-secret"),
            access_token=encrypt_text("old-token"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),  # истёк
        )
        db_session.add(integration)
        await db_session.flush()

        mock_client.get_application_ids = AsyncMock(return_value={"applies": [], "cursor": None})

        with patch("app.services.integrations.avito.service.avito_client") as mock_token_client:
            mock_token_client.get_access_token = AsyncMock(
                return_value={"access_token": "refreshed-token", "expires_in": 3600}
            )
            await poll_avito_responses_now(db_session, admin_user.company_id)
            # get_access_token должен быть вызван (рефреш)
            mock_token_client.get_access_token.assert_awaited_once()

    @patch("app.services.integrations.avito.sync.avito_client")
    async def test_402_from_token_raises_validation_error(
        self, mock_client, db_session: AsyncSession, admin_user, avito_vacancy
    ):
        """Авито вернул 402 при получении токена → ValidationError (не 500)."""
        integration = AvitoIntegration(
            company_id=admin_user.company_id,
            client_id=encrypt_text("bad-client-id"),
            client_secret=encrypt_text("bad-client-secret"),
            access_token=None,  # нет кэша — потребует рефреша
            expires_at=None,
        )
        db_session.add(integration)
        await db_session.flush()

        with patch("app.services.integrations.avito.service.avito_client") as mock_token_client:
            mock_token_client.get_access_token = AsyncMock(
                side_effect=ValueError("HTTP 402 — подписка/доступ Авито")
            )
            with pytest.raises(ValidationError, match="402|[Аа]вито"):
                await poll_avito_responses_now(db_session, admin_user.company_id)


# ---------------------------------------------------------------------------
# Тесты avito_service (save_config, get_status, link/unlink/disconnect)
# ---------------------------------------------------------------------------

class TestAvitoService:
    """Тесты сервиса управления интеграцией Авито."""

    async def test_save_config_stores_encrypted(
        self, db_session: AsyncSession, admin_user
    ):
        """save_config сохраняет client_id/secret зашифрованными (Fernet)."""
        await avito_service.save_config(
            db_session,
            company_id=admin_user.company_id,
            client_id="my-client-id",
            client_secret="my-client-secret",
            user_id=admin_user.id,
        )
        await db_session.commit()

        integration = (await db_session.execute(
            select(AvitoIntegration).where(AvitoIntegration.company_id == admin_user.company_id)
        )).scalar_one_or_none()
        assert integration is not None
        # В БД — зашифровано, не plaintext
        assert integration.client_id != "my-client-id"
        assert integration.client_secret != "my-client-secret"
        # Можно расшифровать
        from app.services.settings.crypto import decrypt_text
        assert decrypt_text(integration.client_id) == "my-client-id"
        assert decrypt_text(integration.client_secret) == "my-client-secret"
        # Кэш токена сброшен
        assert integration.access_token is None
        assert integration.expires_at is None

    async def test_get_status_connected(
        self, db_session: AsyncSession, admin_user, avito_integration
    ):
        """get_status возвращает connected=True если есть credentials."""
        status = await avito_service.get_status(db_session, admin_user.company_id)
        assert status["connected"] is True

    async def test_get_status_not_connected(
        self, db_session: AsyncSession, admin_user
    ):
        """get_status возвращает connected=False если нет интеграции."""
        status = await avito_service.get_status(db_session, admin_user.company_id)
        assert status["connected"] is False

    async def test_link_vacancy_sets_avito_vacancy_id(
        self, db_session: AsyncSession, admin_user
    ):
        """link_avito_vacancy ставит avito_vacancy_id на вакансию."""
        vacancy = Vacancy(
            company_id=admin_user.company_id,
            name="Test Avito Link",
            status="active",
        )
        db_session.add(vacancy)
        await db_session.flush()

        await avito_service.link_avito_vacancy(
            db_session,
            vacancy_id=vacancy.id,
            avito_vacancy_id="avito-vac-new-123",
            company_id=admin_user.company_id,
            user_id=admin_user.id,
        )
        await db_session.commit()

        refreshed = await db_session.get(Vacancy, vacancy.id)
        assert refreshed.avito_vacancy_id == "avito-vac-new-123"

    async def test_link_wrong_company_raises_not_found(
        self, db_session: AsyncSession, admin_user, other_company
    ):
        """link_avito_vacancy на вакансию чужой компании → NotFoundError."""
        from app.core.errors import NotFoundError

        vacancy = Vacancy(
            company_id=other_company.id,
            name="Чужая вакансия",
            status="active",
        )
        db_session.add(vacancy)
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await avito_service.link_avito_vacancy(
                db_session,
                vacancy_id=vacancy.id,
                avito_vacancy_id="avito-123",
                company_id=admin_user.company_id,
                user_id=admin_user.id,
            )

    async def test_unlink_clears_avito_vacancy_id(
        self, db_session: AsyncSession, admin_user
    ):
        """unlink_avito_vacancy обнуляет avito_vacancy_id."""
        vacancy = Vacancy(
            company_id=admin_user.company_id,
            name="Test Avito Unlink",
            status="active",
            avito_vacancy_id="avito-to-unlink",
        )
        db_session.add(vacancy)
        await db_session.flush()

        await avito_service.unlink_avito_vacancy(
            db_session,
            vacancy_id=vacancy.id,
            company_id=admin_user.company_id,
            user_id=admin_user.id,
        )
        await db_session.commit()

        refreshed = await db_session.get(Vacancy, vacancy.id)
        assert refreshed.avito_vacancy_id is None

    async def test_disconnect_clears_credentials(
        self, db_session: AsyncSession, admin_user, avito_integration
    ):
        """disconnect обнуляет client_id/secret и кэш токена."""
        await avito_service.disconnect(db_session, admin_user.company_id, admin_user.id)
        await db_session.commit()

        await db_session.refresh(avito_integration)
        assert avito_integration.client_id is None
        assert avito_integration.client_secret is None
        assert avito_integration.access_token is None

    async def test_save_config_empty_credentials_raises(
        self, db_session: AsyncSession, admin_user
    ):
        """save_config с пустыми credentials → ValidationError."""
        with pytest.raises(ValidationError, match="[Оо]бязательны|client_id"):
            await avito_service.save_config(
                db_session,
                company_id=admin_user.company_id,
                client_id="",
                client_secret="my-secret",
                user_id=admin_user.id,
            )


# ---------------------------------------------------------------------------
# Тесты get_valid_access_token
# ---------------------------------------------------------------------------

class TestGetValidAccessToken:
    """Тесты получения/рефреша access_token Авито (client_credentials)."""

    async def test_no_integration_raises(self, db_session: AsyncSession, admin_user):
        """Нет AvitoIntegration → ValidationError."""
        with pytest.raises(ValidationError, match="[Аа]вито"):
            await avito_service.get_valid_access_token(db_session, admin_user.company_id)

    async def test_cached_token_returned_without_refresh(
        self, db_session: AsyncSession, admin_user, avito_integration
    ):
        """Валидный кэш токена → decrypt и вернуть, НЕ дёргать /token."""
        with patch("app.services.integrations.avito.service.avito_client") as mock_tc:
            mock_tc.get_access_token = AsyncMock(return_value={"access_token": "NEW"})
            token, employee_of = await avito_service.get_valid_access_token(
                db_session, admin_user.company_id
            )
        assert token == "test-avito-access-token"
        mock_tc.get_access_token.assert_not_called()

    async def test_expired_token_refreshes(
        self, db_session: AsyncSession, admin_user
    ):
        """Истёкший токен → /token вызывается, новый токен сохраняется."""
        integration = AvitoIntegration(
            company_id=admin_user.company_id,
            client_id=encrypt_text("cid"),
            client_secret=encrypt_text("csecret"),
            access_token=encrypt_text("old-token"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # истёк
        )
        db_session.add(integration)
        await db_session.flush()

        with patch("app.services.integrations.avito.service.avito_client") as mock_tc:
            mock_tc.get_access_token = AsyncMock(
                return_value={"access_token": "refreshed-token", "expires_in": 7200}
            )
            token, _ = await avito_service.get_valid_access_token(
                db_session, admin_user.company_id
            )

        assert token == "refreshed-token"
        mock_tc.get_access_token.assert_awaited_once()

        # Новый токен сохранён
        await db_session.refresh(integration)
        from app.services.settings.crypto import decrypt_text
        assert decrypt_text(integration.access_token) == "refreshed-token"

    async def test_402_error_raises_validation_error(
        self, db_session: AsyncSession, admin_user
    ):
        """Авито вернул 402 при client_credentials → ValidationError."""
        integration = AvitoIntegration(
            company_id=admin_user.company_id,
            client_id=encrypt_text("cid"),
            client_secret=encrypt_text("csecret"),
            access_token=None,
            expires_at=None,
        )
        db_session.add(integration)
        await db_session.flush()

        with patch("app.services.integrations.avito.service.avito_client") as mock_tc:
            mock_tc.get_access_token = AsyncMock(
                side_effect=ValueError("HTTP 402 — подписка")
            )
            with pytest.raises(ValidationError, match="402|подпис"):
                await avito_service.get_valid_access_token(
                    db_session, admin_user.company_id
                )
