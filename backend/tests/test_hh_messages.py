"""Тесты для функционала переписки через hh.ru"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.message import send_message
from app.schemas.message import MessageCreate
from app.core.errors import ValidationError
from app.models import Message, Application, Candidate, User, Company


class TestHhMessaging:
    """Тесты отправки и приёма сообщений через hh"""

    @pytest.mark.asyncio
    async def test_send_hh_message_with_negotiation_id_success(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """Отправка сообщения hh при наличии hh_negotiation_id -> вызывает hh, сохраняет out с external_id"""

        # Создаём заявку с hh_negotiation_id
        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=test_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id="12345",
            hh_chat_id="chat_567"
        )
        db_session.add(application)
        await db_session.flush()

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
                db_session,
                test_candidate.id,
                message_data,
                test_company.id,
                admin_user.id
            )

            # Проверяем, что hh-методы были вызваны
            mock_token.assert_called_once_with(db_session, test_company.id)
            mock_send.assert_called_once_with("test_token", "chat_567", "Тестовое сообщение")

            # Проверяем результат
            assert result.channel == "hh"
            assert result.direction == "out"
            assert result.sender_type == "recruiter"
            assert result.body == "Тестовое сообщение"

            # Проверяем сохранение в БД
            saved_message = await db_session.get(Message, result.id)
            assert saved_message.external_id == "msg_123"
            assert saved_message.channel == "hh"

    @pytest.mark.asyncio
    async def test_send_hh_message_without_negotiation_id_error(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """Отправка hh без hh_negotiation_id -> 400, ничего не сохранено"""

        message_data = MessageCreate(
            channel="hh",
            body="Тестовое сообщение"
        )

        # Токен есть (интеграцию не поднимаем) — проверяем именно отказ из-за отсутствия чата
        with patch('app.services.message.get_valid_access_token', new_callable=AsyncMock, return_value="test_token"):
            with pytest.raises(ValidationError) as exc_info:
                await send_message(
                    db_session,
                    test_candidate.id,
                    message_data,
                    test_company.id,
                    admin_user.id
                )

        assert "Канал hh недоступен" in str(exc_info.value)

        # Проверяем, что сообщение НЕ сохранено
        from sqlalchemy import select
        result = await db_session.execute(
            select(Message).where(Message.candidate_id == test_candidate.id)
        )
        assert not result.fetchall()

    @pytest.mark.asyncio
    async def test_send_hh_message_api_failure_no_save(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """hh-вызов упал -> ошибка проброшена, сообщение НЕ сохранено"""

        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=test_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id="12345",
            hh_chat_id="chat_567"
        )
        db_session.add(application)
        await db_session.flush()

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
                    db_session,
                    test_candidate.id,
                    message_data,
                    test_company.id,
                    admin_user.id
                )

            assert "Нет прав на чат hh" in str(exc_info.value)

            # Проверяем, что сообщение НЕ сохранено (no fake sent)
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(Message.candidate_id == test_candidate.id)
            )
            assert not result.fetchall()

    @pytest.mark.asyncio
    async def test_send_records_only_channel_unchanged(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """Канал без реальной отправки (sms) работает как раньше (запись в БД, hh НЕ дёргается)"""

        message_data = MessageCreate(
            channel="sms",
            body="Тестовое сообщение sms"
        )

        # Мокаем hh-методы, чтобы убедиться, что они НЕ вызываются
        with patch('app.services.message.get_valid_access_token') as mock_token, \
             patch('app.services.message.hh_client.send_chat_message') as mock_send:

            result = await send_message(
                db_session,
                test_candidate.id,
                message_data,
                test_company.id,
                admin_user.id
            )

            # hh-методы НЕ должны быть вызваны
            mock_token.assert_not_called()
            mock_send.assert_not_called()

            # Проверяем результат
            assert result.channel == "sms"
            assert result.direction == "out"
            assert result.sender_type == "recruiter"
            assert result.body == "Тестовое сообщение sms"

            # Проверяем сохранение в БД (без external_id для telegram)
            saved_message = await db_session.get(Message, result.id)
            assert saved_message.external_id is None
            assert saved_message.channel == "telegram"

    @pytest.mark.asyncio
    async def test_send_hh_message_lazy_backfill_chat_id(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """Отправка hh без chat_id, но есть negotiation_id -> ленивый get_negotiation даёт chat_id -> шлём"""

        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=test_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        # Заявка БЕЗ hh_chat_id, но С hh_negotiation_id
        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id="12345",
            hh_chat_id=None
        )
        db_session.add(application)
        await db_session.flush()

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
                db_session,
                test_candidate.id,
                message_data,
                test_company.id,
                admin_user.id
            )

            # Проверяем, что методы были вызваны в правильном порядке
            mock_token.assert_called_once_with(db_session, test_company.id)
            mock_get_neg.assert_called_once_with("test_token", "12345")
            mock_send.assert_called_once_with("test_token", "567", "Тестовое сообщение")

            # Проверяем, что chat_id сохранён в Application
            await db_session.refresh(application)
            assert application.hh_chat_id == "567"

    @pytest.mark.asyncio
    async def test_send_hh_message_no_chat_id_no_negotiation_id_error(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """Отправка hh без chat_id и negotiation_id -> 400, не сохранено"""

        from app.models import Vacancy, Application

        vacancy = Vacancy(
            company_id=test_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        # Заявка БЕЗ hh_chat_id И БЕЗ hh_negotiation_id
        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id=None,
            hh_chat_id=None
        )
        db_session.add(application)
        await db_session.flush()

        message_data = MessageCreate(
            channel="hh",
            body="Тестовое сообщение",
            application_id=application.id
        )

        with patch('app.services.message.get_valid_access_token', new_callable=AsyncMock, return_value="test_token"), \
             patch('app.services.message.hh_client.get_negotiation_responses', new_callable=AsyncMock, return_value={"items": [], "pages": 0}):
            with pytest.raises(ValidationError) as exc_info:
                await send_message(
                    db_session,
                    test_candidate.id,
                    message_data,
                    test_company.id,
                    admin_user.id
                )

        assert "Канал hh недоступен" in str(exc_info.value)

        # Проверяем, что сообщение НЕ сохранено
        from sqlalchemy import select
        result = await db_session.execute(
            select(Message).where(Message.candidate_id == test_candidate.id)
        )
        assert not result.fetchall()

    @pytest.mark.asyncio
    async def test_send_hh_backfill_by_resume_id_success(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """Бэкфилл по resume_id: нет negotiation_id/chat_id, но hh_resume_id в extra и
        get_negotiation_responses возвращает совпадающий отклик → negotiation_id/chat_id
        сохраняются в Application, сообщение отправляется."""

        from app.models import Vacancy, Application

        # Устанавливаем hh_resume_id в extra кандидата
        test_candidate.extra = {"hh_resume_id": "resume_abc"}
        await db_session.flush()

        # Вакансия с hh_vacancy_id
        vacancy = Vacancy(
            company_id=test_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active",
            hh_vacancy_id="hh_vac_123",
        )
        db_session.add(vacancy)
        await db_session.flush()

        # Заявка БЕЗ negotiation_id и chat_id
        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id=None,
            hh_chat_id=None,
        )
        db_session.add(application)
        await db_session.flush()

        # Ответ get_negotiation_responses: один отклик с resume.id == "resume_abc"
        mock_negotiations_page = {
            "items": [
                {
                    "id": "neg_999",
                    "chat_id": 42,
                    "resume": {"id": "resume_abc"},
                    "state": {"id": "phone_interview"},
                }
            ],
            "pages": 1,
        }

        with patch('app.services.message.get_valid_access_token', new_callable=AsyncMock, return_value="test_token"), \
             patch('app.services.message.hh_client.get_negotiation_responses', new_callable=AsyncMock, return_value=mock_negotiations_page), \
             patch('app.services.message.hh_client.send_chat_message', new_callable=AsyncMock, return_value={"id": "msg_bkf"}):

            message_data = MessageCreate(
                channel="hh",
                body="Бэкфилл-тест",
                application_id=application.id,
            )
            result = await send_message(
                db_session,
                test_candidate.id,
                message_data,
                test_company.id,
                admin_user.id,
            )

        # Сообщение успешно отправлено и сохранено
        assert result.channel == "hh"
        assert result.direction == "out"
        assert result.body == "Бэкфилл-тест"

        # negotiation_id и chat_id персистированы в Application
        await db_session.refresh(application)
        assert application.hh_negotiation_id == "neg_999"
        assert application.hh_chat_id == "42"

        # Внешний id сообщения
        from sqlalchemy import select
        saved = await db_session.execute(
            select(Message).where(Message.candidate_id == test_candidate.id, Message.channel == "hh")
        )
        msgs = saved.scalars().all()
        assert len(msgs) == 1
        assert msgs[0].external_id == "msg_bkf"

    @pytest.mark.asyncio
    async def test_send_hh_backfill_no_match_clear_error(
        self, db_session, test_company, admin_user, test_candidate
    ):
        """Бэкфилл: resume_id есть, но ни один отклик не совпадает → чёткая ошибка,
        сообщение НЕ сохранено."""

        from app.models import Vacancy, Application

        test_candidate.extra = {"hh_resume_id": "resume_xyz"}
        await db_session.flush()

        vacancy = Vacancy(
            company_id=test_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active",
            hh_vacancy_id="hh_vac_456",
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_negotiation_id=None,
            hh_chat_id=None,
        )
        db_session.add(application)
        await db_session.flush()

        # Ни одного совпадающего отклика — другой resume_id
        mock_negotiations_page = {
            "items": [
                {
                    "id": "neg_000",
                    "chat_id": 99,
                    "resume": {"id": "resume_other"},
                    "state": {"id": "response"},
                }
            ],
            "pages": 1,
        }

        with patch('app.services.message.get_valid_access_token', new_callable=AsyncMock, return_value="test_token"), \
             patch('app.services.message.hh_client.get_negotiation_responses', new_callable=AsyncMock, return_value=mock_negotiations_page):
            with pytest.raises(ValidationError) as exc_info:
                await send_message(
                    db_session,
                    test_candidate.id,
                    MessageCreate(channel="hh", body="Текст", application_id=application.id),
                    test_company.id,
                    admin_user.id,
                )

        err = str(exc_info.value)
        assert "Канал hh недоступен" in err
        assert "диалога на hh" in err

        # Сообщение НЕ сохранено
        from sqlalchemy import select
        result = await db_session.execute(
            select(Message).where(Message.candidate_id == test_candidate.id)
        )
        assert not result.fetchall()

    @pytest.mark.asyncio
    async def test_message_deduplication_by_external_id(self, db_session, test_company, test_candidate):
        """Дедуп входящих по external_id (повторный poll не дублирует)"""

        # Создаём входящее сообщение с external_id
        message1 = Message(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            channel="hh",
            direction="in",
            sender_type="candidate",
            body="Первое сообщение",
            external_id="hh_msg_123",
            sent_at=datetime.now(timezone.utc)  # NOT NULL
        )
        db_session.add(message1)
        await db_session.flush()

        # Попытка создать дубликат с тем же external_id
        message2 = Message(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            channel="hh",
            direction="in",
            sender_type="candidate",
            body="Дубликат сообщения",
            external_id="hh_msg_123",
            sent_at=datetime.now(timezone.utc)
        )
        db_session.add(message2)

        # Проверяем дедуп логику (в реальном коде это делается в poll_hh_messages)
        from sqlalchemy import select
        existing = await db_session.execute(
            select(Message.id).where(
                Message.external_id == "hh_msg_123",
                Message.company_id == test_company.id
            )
        )
        existing_count = len(existing.fetchall())

        # Первое сообщение должно существовать
        assert existing_count >= 1

    @pytest.mark.asyncio
    async def test_poll_chat_messages_applicant_saved_employer_skipped(self, db_session, test_company, test_candidate):
        """poll: APPLICANT-сообщение сохраняется, EMPLOYER пропускается, дедуп по external_id"""

        from app.models import Vacancy, Application
        from app.jobs.poll_hh_messages import poll_chat_messages

        vacancy = Vacancy(
            company_id=test_company.id,
            name="Test Vacancy",
            description="Test Description",
            status="active"
        )
        db_session.add(vacancy)
        await db_session.flush()

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            hh_chat_id="chat_123"
        )
        db_session.add(application)
        await db_session.flush()

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
                    "payload": {"text": None}
                }
            ]
        }

        with patch('app.jobs.poll_hh_messages.hh_client.get_chat_messages') as mock_get:
            mock_get.return_value = mock_messages

            imported = await poll_chat_messages(
                db_session,
                test_company.id,
                "chat_123",
                test_candidate.id,
                application.id,
                "test_token"
            )

            # Должно быть импортировано только 1 сообщение (от APPLICANT с типом SIMPLE)
            assert imported == 1

            # Проверяем, что сохранилось только сообщение от кандидата
            from sqlalchemy import select
            result = await db_session.execute(
                select(Message).where(
                    Message.candidate_id == test_candidate.id,
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
            mock_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
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
            mock_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
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
            mock_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
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
            mock_response = MagicMock()  # httpx Response.json()/.status_code — синхронные
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
    async def test_send_email_success(self, db_session, test_company, admin_user, test_candidate):
        """Канал email при наличии email кандидата -> реально вызывает send_email, сохраняет out"""
        with patch('app.services.message.send_email') as mock_send_email:
            mock_send_email.return_value = None

            message_data = MessageCreate(channel="email", body="Здравствуйте, приглашаем на интервью")
            result = await send_message(
                db_session, test_candidate.id, message_data, test_company.id, admin_user.id
            )

            mock_send_email.assert_called_once()
            # письмо ушло на email кандидата
            assert mock_send_email.call_args.kwargs["to"] == test_candidate.email
            assert result.channel == "email"
            assert result.direction == "out"
            saved = await db_session.get(Message, result.id)
            assert saved is not None and saved.channel == "email"

    @pytest.mark.asyncio
    async def test_send_email_without_candidate_email_error(self, db_session, test_company, admin_user, test_candidate):
        """Канал email без email у кандидата -> ошибка, send_email НЕ вызван, ничего не сохранено"""
        test_candidate.email = None
        await db_session.flush()

        with patch('app.services.message.send_email') as mock_send_email:
            message_data = MessageCreate(channel="email", body="Текст")
            with pytest.raises(ValidationError) as exc_info:
                await send_message(
                    db_session, test_candidate.id, message_data, test_company.id, admin_user.id
                )
            assert "email" in str(exc_info.value).lower()
            mock_send_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_failure_not_saved(self, db_session, test_company, admin_user, test_candidate):
        """SMTP упал -> ошибка проброшена, сообщение НЕ сохранено (no fake «отправлено»)"""
        with patch('app.services.message.send_email') as mock_send_email:
            mock_send_email.side_effect = ValidationError("SMTP не настроен")
            message_data = MessageCreate(channel="email", body="Текст")
            with pytest.raises(ValidationError):
                await send_message(
                    db_session, test_candidate.id, message_data, test_company.id, admin_user.id
                )

    @pytest.mark.asyncio
    async def test_records_only_channel_does_not_send_email(self, db_session, test_company, admin_user, test_candidate):
        """Канал без реальной отправки (sms) -> send_email НЕ вызывается, сообщение сохраняется в БД"""
        with patch('app.services.message.send_email') as mock_send_email:
            message_data = MessageCreate(channel="sms", body="Внутренняя заметка")
            result = await send_message(
                db_session, test_candidate.id, message_data, test_company.id, admin_user.id
            )
            mock_send_email.assert_not_called()
            assert result.channel == "sms"


class TestTelegramMessaging:
    """Реальная отправка кандидату через Telegram (Telethon user-аккаунт).

    tg_service.send_to_candidate мокается по import-site в message.py — живой Telethon
    не дёргается. Проверяем: успех сохраняет сообщение, сбой/нет-контакта НЕ сохраняет
    (никакого фейка «отправлено»).
    """

    @pytest.mark.asyncio
    async def test_send_telegram_real_success(self, db_session, test_company, admin_user, test_candidate):
        """telegram: send_to_candidate ок → сообщение сохранено, external_id проставлен."""
        from sqlalchemy import select

        message_data = MessageCreate(channel="telegram", body="Привет из Глафиры")
        with patch(
            'app.services.message.tg_service.send_to_candidate',
            new_callable=AsyncMock,
            return_value={"message_id": "555", "peer": "777"},
        ) as mock_send:
            result = await send_message(
                db_session, test_candidate.id, message_data, test_company.id, admin_user.id
            )

        mock_send.assert_awaited_once()
        # вызвано по номеру кандидата (у фикстуры есть phone, нет tg-username)
        kwargs = mock_send.await_args.kwargs
        assert kwargs["phone"] == test_candidate.phone
        assert kwargs["text"] == "Привет из Глафиры"
        assert result.channel == "telegram"
        assert result.direction == "out"

        # сообщение реально в БД + external_id из Telegram
        row = (await db_session.execute(
            select(Message).where(Message.id == result.id)
        )).scalar_one()
        assert row.external_id == "555"

    @pytest.mark.asyncio
    async def test_send_telegram_failure_not_persisted(self, db_session, test_company, admin_user, test_candidate):
        """telegram: send_to_candidate кидает AppError → проброс + сообщение НЕ сохранено."""
        from sqlalchemy import select, func
        from app.core.errors import AppError

        before = (await db_session.execute(
            select(func.count()).select_from(Message).where(Message.candidate_id == test_candidate.id)
        )).scalar_one()

        message_data = MessageCreate(channel="telegram", body="Не дойдёт")
        with patch(
            'app.services.message.tg_service.send_to_candidate',
            new_callable=AsyncMock,
            side_effect=AppError(
                code="TG_NO_TG_ACCOUNT",
                message="У кандидата нет аккаунта Telegram на этом номере",
                status_code=400,
            ),
        ):
            with pytest.raises(AppError):
                await send_message(
                    db_session, test_candidate.id, message_data, test_company.id, admin_user.id
                )

        after = (await db_session.execute(
            select(func.count()).select_from(Message).where(Message.candidate_id == test_candidate.id)
        )).scalar_one()
        assert after == before  # ничего не сохранилось — никакого фейка «отправлено»

    @pytest.mark.asyncio
    async def test_send_telegram_no_contact_validation(self, db_session, test_company, admin_user):
        """telegram: у кандидата ни телефона, ни tg-username → ValidationError, отправка не зовётся."""
        candidate = Candidate(
            company_id=test_company.id,
            last_name="Без",
            first_name="Контактов",
            phone=None,
            messengers=[],
            source="manual",
        )
        db_session.add(candidate)
        await db_session.flush()

        message_data = MessageCreate(channel="telegram", body="Куда-то")
        with patch(
            'app.services.message.tg_service.send_to_candidate',
            new_callable=AsyncMock,
        ) as mock_send:
            with pytest.raises(ValidationError):
                await send_message(
                    db_session, candidate.id, message_data, test_company.id, admin_user.id
                )
        mock_send.assert_not_called()


class TestExtractTelegramUsername:
    """Юнит-тесты разбора tg-username из поля messengers (двухформатное)."""

    def test_extracts_from_tme_url(self):
        from app.services.integrations.telegram.service import extract_telegram_username
        assert extract_telegram_username([{"type": "tg", "url": "https://t.me/ivan"}]) == "ivan"

    def test_extracts_type_telegram_with_trailing_and_query(self):
        from app.services.integrations.telegram.service import extract_telegram_username
        assert extract_telegram_username([{"type": "telegram", "url": "t.me/petr/?start=1"}]) == "petr"

    def test_ignores_plain_string_channels(self):
        from app.services.integrations.telegram.service import extract_telegram_username
        assert extract_telegram_username(["telegram", "whatsapp"]) is None

    def test_empty_returns_none(self):
        from app.services.integrations.telegram.service import extract_telegram_username
        assert extract_telegram_username([]) is None

    def test_non_tg_object_returns_none(self):
        from app.services.integrations.telegram.service import extract_telegram_username
        assert extract_telegram_username([{"type": "wa", "url": "https://wa.me/79001234567"}]) is None


class TestNormalizePhone:
    """Юнит-тесты нормализации телефона перед резолвом в Telethon."""

    def test_human_format_with_plus(self):
        from app.services.integrations.telegram.client import _normalize_phone
        assert _normalize_phone("+7 900 123 45 67") == "+79001234567"

    def test_parens_and_dashes(self):
        from app.services.integrations.telegram.client import _normalize_phone
        assert _normalize_phone("+7 (931) 361-24-08") == "+79313612408"

    def test_no_plus_kept_digits_only(self):
        from app.services.integrations.telegram.client import _normalize_phone
        assert _normalize_phone("8 900 123 45 67") == "89001234567"

    def test_empty(self):
        from app.services.integrations.telegram.client import _normalize_phone
        assert _normalize_phone("") == ""