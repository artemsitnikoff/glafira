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
        assert application.stage == "added"

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
        assert stats["skipped"] == 1