"""Тесты для hh.ru polling и интеграций"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import text
from app.services.integrations.hh import service as hh_service, client as hh_client
from app.models import Vacancy, Application, Candidate


class TestHhClient:
    """Тесты hh-клиента"""

    @patch('app.services.integrations.hh.client._get_client')
    async def test_get_employer_vacancies(self, mock_get_client):
        """Тест получения вакансий работодателя"""
        mock_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"id": "123", "name": "Python Developer", "area": {"name": "Москва"}},
                {"id": "456", "name": "QA Engineer", "area": None}
            ],
            "pages": 1,
            "page": 0
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = await hh_client.get_employer_vacancies("token", "employer123", page=0, per_page=50)

        assert "items" in result
        assert len(result["items"]) == 2
        assert result["items"][0]["id"] == "123"
        mock_client.get.assert_called_once()

    @patch('app.services.integrations.hh.client._get_client')
    async def test_get_negotiation_responses(self, mock_get_client):
        """Тест получения откликов"""
        # get_negotiation_responses делает ДВА get-запроса:
        # 1) /negotiations → коллекции по статусам (нужен 'collections' c id='response')
        # 2) url коллекции 'response' → собственно отклики (нужен 'items')
        collections_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
        collections_response.status_code = 200
        collections_response.json.return_value = {
            "collections": [
                {"id": "response", "url": "https://api.hh.ru/negotiations/response?vacancy_id=vacancy123"}
            ]
        }
        collections_response.raise_for_status.return_value = None

        items_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
        items_response.status_code = 200
        items_response.json.return_value = {
            "items": [
                {
                    "id": "neg1",
                    "resume": {
                        "first_name": "Иван",
                        "last_name": "Петров",
                        "area": {"name": "Санкт-Петербург"}
                    }
                }
            ],
            "pages": 1
        }
        items_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        # первый get → коллекции, второй get → отклики
        mock_client.get.side_effect = [collections_response, items_response]
        mock_get_client.return_value = mock_client

        result = await hh_client.get_negotiation_responses("token", "vacancy123", page=0)

        assert "items" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["resume"]["first_name"] == "Иван"

    @patch('app.services.integrations.hh.client._get_client')
    async def test_publish_vacancy(self, mock_get_client):
        """Тест публикации вакансии"""
        mock_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "new_vacancy_123"}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_get_client.return_value = mock_client

        payload = {"name": "Test Vacancy", "description": "Test Description"}
        result = await hh_client.publish_vacancy("token", payload)

        assert result["id"] == "new_vacancy_123"
        mock_client.post.assert_called_once()


class TestHhService:
    """Тесты hh-сервиса"""

    async def test_import_response_creates_new(self, db_session, test_company, test_vacancy):
        """Тест импорта нового отклика"""
        item = {
            "id": "neg123",
            "resume": {
                "first_name": "Анна",
                "last_name": "Сидорова",
                "area": {"name": "Екатеринбург"}
            }
        }

        # Импортируем отклик
        imported = await hh_service.import_response(
            db_session, test_company.id, test_vacancy, item
        )

        assert imported == "created"

        # Проверяем, что создались кандидат и Application
        candidates = await db_session.execute(
            text("SELECT * FROM candidates WHERE company_id = :company_id AND source = 'hh'"),
            {"company_id": str(test_company.id)}
        )
        candidate = candidates.fetchone()
        assert candidate is not None
        assert candidate.first_name == "Анна"
        assert candidate.last_name == "Сидорова"
        assert candidate.city == "Екатеринбург"

        applications = await db_session.execute(
            text("SELECT * FROM applications WHERE hh_negotiation_id = 'neg123'"),
        )
        application = applications.fetchone()
        assert application is not None
        # hh-отклик попадает в этап «Отклик» (response), не «added» (тот — для ручного
        # добавления). import_response: stage = 'rejected' если discard, иначе 'response'.
        assert application.stage == "response"

    async def test_import_response_skips_duplicate(self, db_session, test_company, test_vacancy, test_candidate):
        """Тест дедупликации при повторном импорте"""
        # Создаём существующий Application с hh_negotiation_id
        existing_app = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="added",
            hh_negotiation_id="neg123"
        )
        db_session.add(existing_app)
        await db_session.commit()

        item = {
            "id": "neg123",  # Тот же ID
            "resume": {"first_name": "Другой", "last_name": "Кандидат"}
        }

        # Импортируем отклик
        imported = await hh_service.import_response(
            db_session, test_company.id, test_vacancy, item
        )

        assert imported == "updated"  # Существующая заявка обновляется (create-or-update), не пропускается

    async def test_import_response_handles_missing_fields(self, db_session, test_company, test_vacancy):
        """Тест обработки неполных данных resume"""
        item = {
            "id": "neg456",
            "resume": {
                # Нет first_name и last_name
                "area": None  # И нет города
            }
        }

        imported = await hh_service.import_response(
            db_session, test_company.id, test_vacancy, item
        )

        assert imported == "created"

        # Проверяем, что кандидат создался с дефолтными значениями
        candidates = await db_session.execute(
            text("SELECT * FROM candidates WHERE company_id = :company_id AND source = 'hh' ORDER BY created_at DESC LIMIT 1"),
            {"company_id": str(test_company.id)}
        )
        candidate = candidates.fetchone()
        assert candidate is not None
        assert candidate.first_name == "Неизвестно"  # Дефолт
        assert candidate.last_name == ""
        assert candidate.city is None

    async def test_link_unlink_vacancy(self, db_session, test_company, test_vacancy, admin_user):
        """Тест привязки и отвязки вакансии"""
        # Привязка
        await hh_service.link_vacancy(
            db_session, test_vacancy.id, "hh_vac_123", test_company.id, admin_user.id
        )
        await db_session.commit()

        # Перезагружаем вакансию
        await db_session.refresh(test_vacancy)
        assert test_vacancy.hh_vacancy_id == "hh_vac_123"

        # Отвязка
        await hh_service.unlink_vacancy(
            db_session, test_vacancy.id, test_company.id, admin_user.id
        )
        await db_session.commit()

        await db_session.refresh(test_vacancy)
        assert test_vacancy.hh_vacancy_id is None


class TestHhPollingJob:
    """Тесты джоба polling откликов"""

    async def test_poll_company_responses_maps_stats(self, db_session, test_company):
        """Джоб poll_company_responses оборачивает hh_service.poll_responses_now и
        отдаёт {imported, skipped}. (Per-vacancy poll_vacancy_responses удалён —
        импорт одного отклика покрыт TestHhService.test_import_response_*.)"""
        from app.jobs.poll_hh_responses import poll_company_responses

        with patch(
            'app.services.integrations.hh.service.poll_responses_now',
            new_callable=AsyncMock,
            return_value={"imported": 2, "skipped": 1},
        ):
            stats = await poll_company_responses(db_session, test_company.id)

        assert stats["imported"] == 2


# ---------------------------------------------------------------------------
# Тесты: list_hh_vacancies с полем linked
# ---------------------------------------------------------------------------

class TestListHhVacanciesLinked:
    """list_hh_vacancies возвращает linked=True для уже привязанных вакансий."""

    async def test_linked_flag(self, db_session, test_company, test_vacancy, admin_user):
        """Одна вакансия уже привязана → linked=True, другая → linked=False."""
        from app.services.settings.crypto import encrypt_text
        from app.models import HhIntegration
        from cryptography.fernet import Fernet

        # Генерируем FERNET_KEY для шифрования
        import app.config as _cfg
        test_key = Fernet.generate_key().decode()
        orig_key = _cfg.settings.FERNET_KEY
        _cfg.settings.FERNET_KEY = test_key

        try:
            # Создаём hh-интеграцию с employer_id
            integration = HhIntegration(
                company_id=test_company.id,
                hh_employer_id="emp_001",
                access_token=encrypt_text("tok"),
                refresh_token=encrypt_text("ref"),
                expires_at=__import__("datetime").datetime(2099, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            )
            db_session.add(integration)

            # Привязываем test_vacancy к hh_id "hh_111"
            test_vacancy.hh_vacancy_id = "hh_111"
            await db_session.commit()

            # Мокаем hh API: две вакансии — одна привязана (hh_111), другая нет (hh_222)
            mock_data = {
                "items": [
                    {"id": "hh_111", "name": "Вакансия привязана", "area": {"name": "Москва"}},
                    {"id": "hh_222", "name": "Вакансия свободна", "area": None},
                ],
                "pages": 1,
                "page": 0,
            }

            with patch(
                "app.services.integrations.hh.client.get_employer_vacancies",
                new_callable=AsyncMock,
                return_value=mock_data,
            ), patch(
                "app.services.integrations.hh.service.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="tok",
            ):
                result = await hh_service.list_hh_vacancies(db_session, test_company.id)

            assert len(result) == 2
            by_id = {r["id"]: r for r in result}
            assert by_id["hh_111"]["linked"] is True
            assert by_id["hh_222"]["linked"] is False
            # Проверяем поле area
            assert by_id["hh_111"]["area"] == "Москва"
            assert by_id["hh_222"]["area"] is None

        finally:
            _cfg.settings.FERNET_KEY = orig_key
            # Убираем hh_vacancy_id с test_vacancy чтобы не влиять на другие тесты
            test_vacancy.hh_vacancy_id = None
            await db_session.commit()


# ---------------------------------------------------------------------------
# Тесты: import_hh_vacancies
# ---------------------------------------------------------------------------

class TestImportHhVacancies:
    """import_hh_vacancies создаёт вакансии, пропускает уже привязанные, не падает на ошибке одной."""

    async def test_creates_vacancy_and_sets_hh_id(self, db_session, test_company, admin_user):
        """Успешный импорт: создаёт вакансию, проставляет hh_vacancy_id."""
        from app.services.settings.crypto import encrypt_text
        from app.models import HhIntegration
        from cryptography.fernet import Fernet
        import app.config as _cfg

        test_key = Fernet.generate_key().decode()
        orig_key = _cfg.settings.FERNET_KEY
        _cfg.settings.FERNET_KEY = test_key

        try:
            integration = HhIntegration(
                company_id=test_company.id,
                hh_employer_id="emp_002",
                access_token=encrypt_text("tok2"),
                refresh_token=encrypt_text("ref2"),
                expires_at=__import__("datetime").datetime(2099, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            )
            db_session.add(integration)
            await db_session.commit()

            full_vacancy = {
                "name": "Backend Python Developer",
                "description": "<p>Ищем разработчика</p>",
                "area": {"name": "Санкт-Петербург"},
                "salary": {"from": 150000, "to": 250000, "currency": "RUR"},
                "employment": {"id": "full"},
            }

            with patch(
                "app.services.integrations.hh.service.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="tok2",
            ), patch(
                "app.services.integrations.hh.client.get_vacancy_by_id",
                new_callable=AsyncMock,
                return_value=full_vacancy,
            ):
                result = await hh_service.import_hh_vacancies(
                    db_session, test_company.id, admin_user.id, ["hh_500"]
                )

            assert result["created"] == 1
            assert result["skipped"] == 0
            assert result["failed"] == 0
            assert "Backend Python Developer" in result["created_names"]

            # Проверяем что вакансия создана и hh_vacancy_id проставлен
            from sqlalchemy import select as sa_select
            from app.models import Vacancy as VacancyModel
            rows = (await db_session.execute(
                sa_select(VacancyModel).where(
                    VacancyModel.company_id == test_company.id,
                    VacancyModel.hh_vacancy_id == "hh_500",
                )
            )).scalars().all()
            assert len(rows) == 1
            vac = rows[0]
            assert vac.salary_from == 150000
            assert vac.salary_to == 250000
            assert vac.currency == "RUB"  # RUR → RUB
            assert vac.external_source == "hh"
            assert vac.external_id == "hh_500"

        finally:
            _cfg.settings.FERNET_KEY = orig_key

    async def test_skips_already_linked(self, db_session, test_company, test_vacancy, admin_user):
        """Вакансия уже привязана → попадает в skipped, не создаётся дубль."""
        from cryptography.fernet import Fernet
        import app.config as _cfg
        from app.services.settings.crypto import encrypt_text
        from app.models import HhIntegration

        test_key = Fernet.generate_key().decode()
        orig_key = _cfg.settings.FERNET_KEY
        _cfg.settings.FERNET_KEY = test_key

        try:
            integration = HhIntegration(
                company_id=test_company.id,
                hh_employer_id="emp_003",
                access_token=encrypt_text("tok3"),
                refresh_token=encrypt_text("ref3"),
                expires_at=__import__("datetime").datetime(2099, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            )
            db_session.add(integration)
            test_vacancy.hh_vacancy_id = "hh_already"
            await db_session.commit()

            with patch(
                "app.services.integrations.hh.service.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="tok3",
            ):
                result = await hh_service.import_hh_vacancies(
                    db_session, test_company.id, admin_user.id, ["hh_already"]
                )

            assert result["created"] == 0
            assert result["skipped"] == 1
            assert result["failed"] == 0

        finally:
            _cfg.settings.FERNET_KEY = orig_key
            test_vacancy.hh_vacancy_id = None
            await db_session.commit()

    async def test_failed_vacancy_does_not_abort_others(self, db_session, test_company, admin_user):
        """Ошибка на одной вакансии (get_vacancy_by_id→None) не ломает остальные."""
        from cryptography.fernet import Fernet
        import app.config as _cfg
        from app.services.settings.crypto import encrypt_text
        from app.models import HhIntegration

        test_key = Fernet.generate_key().decode()
        orig_key = _cfg.settings.FERNET_KEY
        _cfg.settings.FERNET_KEY = test_key

        try:
            integration = HhIntegration(
                company_id=test_company.id,
                hh_employer_id="emp_004",
                access_token=encrypt_text("tok4"),
                refresh_token=encrypt_text("ref4"),
                expires_at=__import__("datetime").datetime(2099, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            )
            db_session.add(integration)
            await db_session.commit()

            good_vacancy = {
                "name": "QA Engineer",
                "description": None,
                "area": {"name": "Казань"},
                "salary": None,
                "employment": None,
            }

            # Первый вызов → None (ошибка), второй → хорошая вакансия
            side_effects = [None, good_vacancy]

            with patch(
                "app.services.integrations.hh.service.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="tok4",
            ), patch(
                "app.services.integrations.hh.client.get_vacancy_by_id",
                new_callable=AsyncMock,
                side_effect=side_effects,
            ):
                result = await hh_service.import_hh_vacancies(
                    db_session, test_company.id, admin_user.id, ["hh_bad", "hh_good"]
                )

            assert result["failed"] == 1
            assert result["created"] == 1
            assert "QA Engineer" in result["created_names"]
            assert len(result["errors"]) == 1

        finally:
            _cfg.settings.FERNET_KEY = orig_key
        assert stats["skipped"] == 1