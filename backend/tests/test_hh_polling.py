"""Тесты для hh.ru polling и интеграций"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.integrations.hh import service as hh_service, client as hh_client
from app.models import Vacancy, Application, Candidate


class TestHhClient:
    """Тесты hh-клиента"""

    @patch('app.services.integrations.hh.client._get_client')
    async def test_get_employer_vacancies(self, mock_get_client):
        """Тест получения вакансий работодателя"""
        mock_response = AsyncMock()
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
        mock_response = AsyncMock()
        mock_response.json.return_value = {
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
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = await hh_client.get_negotiation_responses("token", "vacancy123", page=0)

        assert "items" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["resume"]["first_name"] == "Иван"

    @patch('app.services.integrations.hh.client._get_client')
    async def test_publish_vacancy(self, mock_get_client):
        """Тест публикации вакансии"""
        mock_response = AsyncMock()
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

        assert imported is True

        # Проверяем, что создались кандидат и Application
        candidates = await db_session.execute(
            "SELECT * FROM candidates WHERE company_id = :company_id AND source = 'hh'",
            {"company_id": str(test_company.id)}
        )
        candidate = candidates.fetchone()
        assert candidate is not None
        assert candidate.first_name == "Анна"
        assert candidate.last_name == "Сидорова"
        assert candidate.city == "Екатеринбург"

        applications = await db_session.execute(
            "SELECT * FROM applications WHERE hh_negotiation_id = 'neg123'",
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

        assert imported is False  # Пропущен как дубль

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

        assert imported is True

        # Проверяем, что кандидат создался с дефолтными значениями
        candidates = await db_session.execute(
            "SELECT * FROM candidates WHERE company_id = :company_id AND source = 'hh' ORDER BY created_at DESC LIMIT 1",
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

    @patch('app.services.integrations.hh.service.get_valid_access_token')
    @patch('app.services.integrations.hh.client.get_negotiation_responses')
    async def test_poll_vacancy_responses(
        self, mock_get_responses, mock_get_token, db_session, test_company, test_vacancy
    ):
        """Тест polling откликов для одной вакансии"""
        from app.jobs.poll_hh_responses import poll_vacancy_responses

        # Настройка моков
        mock_get_token.return_value = "valid_token"
        mock_get_responses.return_value = {
            "items": [
                {
                    "id": "resp1",
                    "resume": {"first_name": "Тест", "last_name": "Кандидат1"}
                },
                {
                    "id": "resp2",
                    "resume": {"first_name": "Тест", "last_name": "Кандидат2"}
                }
            ],
            "pages": 1
        }

        # Устанавливаем hh_vacancy_id
        test_vacancy.hh_vacancy_id = "hh_vac_test"

        # Запускаем polling
        stats = await poll_vacancy_responses(db_session, "token", test_vacancy)

        # Проверяем результат
        assert stats["imported"] == 2
        assert stats["skipped"] == 0

        # Проверяем, что создались Application'ы
        applications = await db_session.execute(
            "SELECT COUNT(*) as count FROM applications WHERE vacancy_id = :vacancy_id AND hh_negotiation_id IS NOT NULL",
            {"vacancy_id": str(test_vacancy.id)}
        )
        count = applications.scalar()
        assert count == 2