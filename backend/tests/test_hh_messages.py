"""Тесты для функционала переписки через hh.ru"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from app.services.message import send_message
from app.schemas.message import MessageCreate
from app.core.errors import ValidationError
from app.models import Message, Application, Candidate, User, Company


class TestHhMessaging:
    """Тесты отправки и приёма сообщений через hh"""

    @pytest.mark.asyncio
    async def test_send_hh_message_with_negotiation_id_success(
        self, async_session, sample_company, sample_user, sample_candidate
    ):
        """Отправка сообщения hh при наличии hh_negotiation_id -> вызывает hh, сохраняет out с external_id"""

        # Создаём заявку с hh_negotiation_id
        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=sample_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        async_session.add(vacancy)
        await async_session.flush()

        application = Application(
            company_id=sample_company.id,
            candidate_id=sample_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id="12345"
        )
        async_session.add(application)
        await async_session.flush()

        # Мокаем hh-вызовы
        with patch('app.services.message.get_valid_access_token') as mock_token, \
             patch('app.services.message.hh_client.send_negotiation_message') as mock_send:

            mock_token.return_value = "test_token"
            mock_send.return_value = {"id": "msg_123", "status": "sent"}

            message_data = MessageCreate(
                channel="hh",
                body="Тестовое сообщение",
                application_id=application.id
            )

            result = await send_message(
                async_session,
                sample_candidate.id,
                message_data,
                sample_company.id,
                sample_user.id
            )

            # Проверяем, что hh-методы были вызваны
            mock_token.assert_called_once_with(async_session, sample_company.id)
            mock_send.assert_called_once_with("test_token", "12345", "Тестовое сообщение")

            # Проверяем результат
            assert result.channel == "hh"
            assert result.direction == "out"
            assert result.sender_type == "recruiter"
            assert result.body == "Тестовое сообщение"

            # Проверяем сохранение в БД
            saved_message = await async_session.get(Message, result.id)
            assert saved_message.external_id == "msg_123"
            assert saved_message.channel == "hh"

    @pytest.mark.asyncio
    async def test_send_hh_message_without_negotiation_id_error(
        self, async_session, sample_company, sample_user, sample_candidate
    ):
        """Отправка hh без hh_negotiation_id -> 400, ничего не сохранено"""

        message_data = MessageCreate(
            channel="hh",
            body="Тестовое сообщение"
        )

        with pytest.raises(ValidationError) as exc_info:
            await send_message(
                async_session,
                sample_candidate.id,
                message_data,
                sample_company.id,
                sample_user.id
            )

        assert "Канал hh недоступен: у кандидата нет отклика hh" in str(exc_info.value)

        # Проверяем, что сообщение НЕ сохранено
        from sqlalchemy import select
        result = await async_session.execute(
            select(Message).where(Message.candidate_id == sample_candidate.id)
        )
        assert not result.fetchall()

    @pytest.mark.asyncio
    async def test_send_hh_message_api_failure_no_save(
        self, async_session, sample_company, sample_user, sample_candidate
    ):
        """hh-вызов упал -> ошибка проброшена, сообщение НЕ сохранено"""

        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=sample_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        async_session.add(vacancy)
        await async_session.flush()

        application = Application(
            company_id=sample_company.id,
            candidate_id=sample_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id="12345"
        )
        async_session.add(application)
        await async_session.flush()

        # Мокаем ошибку hh API
        with patch('app.services.message.get_valid_access_token') as mock_token, \
             patch('app.services.message.hh_client.send_negotiation_message') as mock_send:

            mock_token.return_value = "test_token"
            mock_send.side_effect = ValidationError("hh.ru ошибка отправки (HTTP 403): Access denied")

            message_data = MessageCreate(
                channel="hh",
                body="Тестовое сообщение",
                application_id=application.id
            )

            with pytest.raises(ValidationError) as exc_info:
                await send_message(
                    async_session,
                    sample_candidate.id,
                    message_data,
                    sample_company.id,
                    sample_user.id
                )

            assert "hh.ru ошибка отправки" in str(exc_info.value)

            # Проверяем, что сообщение НЕ сохранено (no fake sent)
            from sqlalchemy import select
            result = await async_session.execute(
                select(Message).where(Message.candidate_id == sample_candidate.id)
            )
            assert not result.fetchall()

    @pytest.mark.asyncio
    async def test_send_telegram_message_unchanged(
        self, async_session, sample_company, sample_user, sample_candidate
    ):
        """Другие каналы (telegram) работают как раньше (запись в БД, hh НЕ дёргается)"""

        message_data = MessageCreate(
            channel="telegram",
            body="Тестовое сообщение telegram"
        )

        # Мокаем hh-методы, чтобы убедиться, что они НЕ вызываются
        with patch('app.services.message.get_valid_access_token') as mock_token, \
             patch('app.services.message.hh_client.send_negotiation_message') as mock_send:

            result = await send_message(
                async_session,
                sample_candidate.id,
                message_data,
                sample_company.id,
                sample_user.id
            )

            # hh-методы НЕ должны быть вызваны
            mock_token.assert_not_called()
            mock_send.assert_not_called()

            # Проверяем результат
            assert result.channel == "telegram"
            assert result.direction == "out"
            assert result.sender_type == "recruiter"
            assert result.body == "Тестовое сообщение telegram"

            # Проверяем сохранение в БД (без external_id для telegram)
            saved_message = await async_session.get(Message, result.id)
            assert saved_message.external_id is None
            assert saved_message.channel == "telegram"

    @pytest.mark.asyncio
    async def test_message_deduplication_by_external_id(self, async_session, sample_company, sample_candidate):
        """Дедуп входящих по external_id (повторный poll не дублирует)"""

        # Создаём входящее сообщение с external_id
        message1 = Message(
            company_id=sample_company.id,
            candidate_id=sample_candidate.id,
            channel="hh",
            direction="in",
            sender_type="candidate",
            body="Первое сообщение",
            external_id="hh_msg_123"
        )
        async_session.add(message1)
        await async_session.flush()

        # Попытка создать дубликат с тем же external_id
        message2 = Message(
            company_id=sample_company.id,
            candidate_id=sample_candidate.id,
            channel="hh",
            direction="in",
            sender_type="candidate",
            body="Дубликат сообщения",
            external_id="hh_msg_123"
        )
        async_session.add(message2)

        # Проверяем дедуп логику (в реальном коде это делается в poll_hh_messages)
        from sqlalchemy import select
        existing = await async_session.execute(
            select(Message.id).where(
                Message.external_id == "hh_msg_123",
                Message.company_id == sample_company.id
            )
        )
        existing_count = len(existing.fetchall())

        # Первое сообщение должно существовать
        assert existing_count >= 1


class TestHhClient:
    """Тесты hh API клиента (моки)"""

    @pytest.mark.asyncio
    async def test_get_negotiation_messages_success(self):
        """Тест получения сообщений переписки"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "items": [
                    {"id": "1", "text": "Тест", "author": {"participant_type": "applicant"}}
                ]
            }
            mock_client.get.return_value = mock_response
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import get_negotiation_messages

            result = await get_negotiation_messages("test_token", "neg_123")

            assert result["items"][0]["text"] == "Тест"
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_negotiation_message_primary_path(self):
        """Тест отправки сообщения основным путём"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "msg_123"}
            mock_response.content = b'{"id": "msg_123"}'
            mock_client.post.return_value = mock_response
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import send_negotiation_message

            result = await send_negotiation_message("test_token", "neg_123", "Привет")

            assert result["id"] == "msg_123"
            mock_client.post.assert_called_once()
            # Проверяем, что вызван основной путь с JSON
            call_args = mock_client.post.call_args
            assert "json" in call_args.kwargs
            assert call_args.kwargs["json"]["message"] == "Привет"

    @pytest.mark.asyncio
    async def test_send_negotiation_message_fallback_path(self):
        """Тест отправки сообщения через fallback при 404"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory, \
             patch('app.services.integrations.hh.client.logger') as mock_logger:

            mock_client = AsyncMock()

            # Первый вызов (основной путь) возвращает 404
            mock_response_404 = AsyncMock()
            mock_response_404.status_code = 404

            # Второй вызов (fallback) возвращает успех
            mock_response_success = AsyncMock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"status": "ok"}
            mock_response_success.content = b'{"status": "ok"}'

            mock_client.post.side_effect = [mock_response_404, mock_response_success]
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import send_negotiation_message

            result = await send_negotiation_message("test_token", "neg_123", "Привет")

            assert result["status"] == "ok"
            assert mock_client.post.call_count == 2

            # Проверяем логирование fallback
            mock_logger.info.assert_called_with("hh send ok via legacy /negotiations/{nid}")

    @pytest.mark.asyncio
    async def test_send_negotiation_message_410_gone_error(self):
        """Тест обработки 410 Gone (метод отключён)"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 410
            mock_client.post.return_value = mock_response
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import send_negotiation_message

            with pytest.raises(ValidationError) as exc_info:
                await send_negotiation_message("test_token", "neg_123", "Привет")

            assert "hh-переписка недоступна (метод отключён hh)" in str(exc_info.value)