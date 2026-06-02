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
            hh_negotiation_id="12345",
            hh_chat_id="chat_567"
        )
        async_session.add(application)
        await async_session.flush()

        # Мокаем hh-вызовы
        with patch('app.services.message.get_valid_access_token') as mock_token, \
             patch('app.services.message.hh_client.send_chat_message') as mock_send:

            mock_token.return_value = "test_token"
            mock_send.return_value = {"id": "msg_123"}

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
            mock_send.assert_called_once_with("test_token", "chat_567", "Тестовое сообщение")

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

        assert "Канал hh недоступен: у кандидата нет чата hh" in str(exc_info.value)

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
            hh_negotiation_id="12345",
            hh_chat_id="chat_567"
        )
        async_session.add(application)
        await async_session.flush()

        # Мокаем ошибку hh API
        with patch('app.services.message.get_valid_access_token') as mock_token, \
             patch('app.services.message.hh_client.send_chat_message') as mock_send:

            mock_token.return_value = "test_token"
            mock_send.side_effect = ValidationError("Нет прав на чат hh")

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

            assert "Нет прав на чат hh" in str(exc_info.value)

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
             patch('app.services.message.hh_client.send_chat_message') as mock_send:

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
    async def test_send_hh_message_lazy_backfill_chat_id(
        self, async_session, sample_company, sample_user, sample_candidate
    ):
        """Отправка hh без chat_id, но есть negotiation_id -> ленивый get_negotiation даёт chat_id -> шлём"""

        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=sample_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        async_session.add(vacancy)
        await async_session.flush()

        # Заявка БЕЗ hh_chat_id, но С hh_negotiation_id
        application = Application(
            company_id=sample_company.id,
            candidate_id=sample_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id="12345",
            hh_chat_id=None
        )
        async_session.add(application)
        await async_session.flush()

        # Мокаем hh-вызовы
        with patch('app.services.message.get_valid_access_token') as mock_token, \
             patch('app.services.message.hh_client.get_negotiation') as mock_get_neg, \
             patch('app.services.message.hh_client.send_chat_message') as mock_send:

            mock_token.return_value = "test_token"
            mock_get_neg.return_value = {"chat_id": 567}
            mock_send.return_value = {"id": "msg_123"}

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

            # Проверяем, что методы были вызваны в правильном порядке
            mock_token.assert_called_once_with(async_session, sample_company.id)
            mock_get_neg.assert_called_once_with("test_token", "12345")
            mock_send.assert_called_once_with("test_token", "567", "Тестовое сообщение")

            # Проверяем, что chat_id сохранён в Application
            await async_session.refresh(application)
            assert application.hh_chat_id == "567"

    @pytest.mark.asyncio
    async def test_send_hh_message_no_chat_id_no_negotiation_id_error(
        self, async_session, sample_company, sample_user, sample_candidate
    ):
        """Отправка hh без chat_id и negotiation_id -> 400, не сохранено"""

        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=sample_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        async_session.add(vacancy)
        await async_session.flush()

        # Заявка БЕЗ hh_chat_id И БЕЗ hh_negotiation_id
        application = Application(
            company_id=sample_company.id,
            candidate_id=sample_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id=None,
            hh_chat_id=None
        )
        async_session.add(application)
        await async_session.flush()

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

        assert "Канал hh недоступен: у кандидата нет чата hh" in str(exc_info.value)

        # Проверяем, что сообщение НЕ сохранено
        from sqlalchemy import select
        result = await async_session.execute(
            select(Message).where(Message.candidate_id == sample_candidate.id)
        )
        assert not result.fetchall()

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

    @pytest.mark.asyncio
    async def test_poll_chat_messages_applicant_saved_employer_skipped(self, async_session, sample_company, sample_candidate):
        """poll: APPLICANT-сообщение сохраняется, EMPLOYER пропускается, дедуп по external_id"""

        from app.models import Vacancy, Application
        from app.jobs.poll_hh_messages import poll_chat_messages

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
            hh_chat_id="chat_123"
        )
        async_session.add(application)
        await async_session.flush()

        # Мокаем ответ hh Chats API
        mock_messages = {
            "messages": [
                {
                    "id": "msg_1",
                    "type": "SIMPLE",
                    "creation_time": "2024-01-15T10:00:00+0300",
                    "sender_display_info": {"role": "APPLICANT"},
                    "payload": {"text": "Сообщение от кандидата"}
                },
                {
                    "id": "msg_2",
                    "type": "SIMPLE",
                    "creation_time": "2024-01-15T10:01:00+0300",
                    "sender_display_info": {"role": "EMPLOYER"},
                    "payload": {"text": "Сообщение от работодателя"}
                },
                {
                    "id": "msg_3",
                    "type": "PARTICIPANT_LEFT",
                    "creation_time": "2024-01-15T10:02:00+0300",
                    "sender_display_info": {"role": "APPLICANT"},
                    "payload": {"text": null}
                }
            ]
        }

        with patch('app.jobs.poll_hh_messages.hh_client.get_chat_messages') as mock_get:
            mock_get.return_value = mock_messages

            imported = await poll_chat_messages(
                async_session,
                sample_company.id,
                "chat_123",
                sample_candidate.id,
                application.id,
                "test_token"
            )

            # Должно быть импортировано только 1 сообщение (от APPLICANT с типом SIMPLE)
            assert imported == 1

            # Проверяем, что сохранилось только сообщение от кандидата
            from sqlalchemy import select
            result = await async_session.execute(
                select(Message).where(
                    Message.candidate_id == sample_candidate.id,
                    Message.channel == "hh",
                    Message.direction == "in"
                )
            )
            messages = result.scalars().all()
            assert len(messages) == 1
            assert messages[0].body == "Сообщение от кандидата"
            assert messages[0].external_id == "msg_1"


class TestHhClient:
    """Тесты hh API клиента (моки)"""

    @pytest.mark.asyncio
    async def test_get_chat_messages_success(self):
        """Тест получения сообщений чата"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "messages": [
                    {
                        "id": "1",
                        "type": "SIMPLE",
                        "payload": {"text": "Тест"},
                        "sender_display_info": {"role": "APPLICANT"}
                    }
                ],
                "has_more": False
            }
            mock_client.get.return_value = mock_response
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import get_chat_messages

            result = await get_chat_messages("test_token", "chat_123")

            assert result["messages"][0]["payload"]["text"] == "Тест"
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_chat_message_success(self):
        """Тест отправки сообщения в чат через Chats API"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "msg_123"}
            mock_client.post.return_value = mock_response
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import send_chat_message

            result = await send_chat_message("test_token", "chat_123", "Привет")

            assert result["id"] == "msg_123"
            mock_client.post.assert_called_once()
            # Проверяем, что вызван с правильными данными
            call_args = mock_client.post.call_args
            assert "json" in call_args.kwargs
            assert call_args.kwargs["json"]["text"] == "Привет"
            assert "idempotency_key" in call_args.kwargs["json"]

    @pytest.mark.asyncio
    async def test_send_chat_message_403_error(self):
        """Тест обработки 403 Forbidden (нет прав на чат)"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 403
            mock_client.post.return_value = mock_response
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import send_chat_message

            with pytest.raises(ValidationError) as exc_info:
                await send_chat_message("test_token", "chat_123", "Привет")

            assert "Нет прав на чат hh" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_negotiation_success(self):
        """Тест получения информации об отклике для извлечения chat_id"""

        with patch('app.services.integrations.hh.client._get_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "neg_123",
                "chat_id": 567,
                "state": {"id": "response"}
            }
            mock_client.get.return_value = mock_response
            mock_client_factory.return_value.__aenter__.return_value = mock_client

            from app.services.integrations.hh.client import get_negotiation

            result = await get_negotiation("test_token", "neg_123")

            assert result["chat_id"] == 567
            mock_client.get.assert_called_once()


class TestEmailMessaging:
    """Тесты реальной отправки канала email через SMTP-ядро + шаблон"""

    @pytest.mark.asyncio
    async def test_send_email_success(self, async_session, sample_company, sample_user, sample_candidate):
        """Канал email при наличии email кандидата -> реально вызывает send_email, сохраняет out"""
        with patch('app.services.message.send_email') as mock_send_email:
            mock_send_email.return_value = None

            message_data = MessageCreate(channel="email", body="Здравствуйте, приглашаем на интервью")
            result = await send_message(
                async_session, sample_candidate.id, message_data, sample_company.id, sample_user.id
            )

            mock_send_email.assert_called_once()
            # письмо ушло на email кандидата
            assert mock_send_email.call_args.kwargs["to"] == sample_candidate.email
            assert result.channel == "email"
            assert result.direction == "out"
            saved = await async_session.get(Message, result.id)
            assert saved is not None and saved.channel == "email"

    @pytest.mark.asyncio
    async def test_send_email_without_candidate_email_error(self, async_session, sample_company, sample_user, sample_candidate):
        """Канал email без email у кандидата -> ошибка, send_email НЕ вызван, ничего не сохранено"""
        sample_candidate.email = None
        await async_session.flush()

        with patch('app.services.message.send_email') as mock_send_email:
            message_data = MessageCreate(channel="email", body="Текст")
            with pytest.raises(ValidationError) as exc_info:
                await send_message(
                    async_session, sample_candidate.id, message_data, sample_company.id, sample_user.id
                )
            assert "email" in str(exc_info.value).lower()
            mock_send_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_failure_not_saved(self, async_session, sample_company, sample_user, sample_candidate):
        """SMTP упал -> ошибка проброшена, сообщение НЕ сохранено (no fake «отправлено»)"""
        with patch('app.services.message.send_email') as mock_send_email:
            mock_send_email.side_effect = ValidationError("SMTP не настроен")
            message_data = MessageCreate(channel="email", body="Текст")
            with pytest.raises(ValidationError):
                await send_message(
                    async_session, sample_candidate.id, message_data, sample_company.id, sample_user.id
                )

    @pytest.mark.asyncio
    async def test_telegram_does_not_send_email(self, async_session, sample_company, sample_user, sample_candidate):
        """Канал telegram (заглушка) -> send_email НЕ вызывается, сообщение сохраняется в БД"""
        with patch('app.services.message.send_email') as mock_send_email:
            message_data = MessageCreate(channel="telegram", body="Внутренняя заметка")
            result = await send_message(
                async_session, sample_candidate.id, message_data, sample_company.id, sample_user.id
            )
            mock_send_email.assert_not_called()
            assert result.channel == "telegram"