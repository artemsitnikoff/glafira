"""Тесты синхронизации отказов hh-кандидатов"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from sqlalchemy import select

from app.services.integrations.hh.service import sync_company_rejections, POLITE_REJECTION_TEXT
from app.models import Application, Candidate, Message


class TestHhRejectionSync:
    """Тесты автоматической синхронизации отказов с hh.ru"""

    @pytest.mark.asyncio
    async def test_sync_rejected_hh_candidate_success(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест успешной синхронизации отказа hh-кандидата"""

        # Вежливое сообщение шлётся ТОЛЬКО при включённом auto_reject_message на вакансии
        # (discard на hh идёт независимо). Включаем, чтобы проверить отправку сообщения.
        test_vacancy.auto_reject_message = True

        # Создаём отклонённую заявку с hh_negotiation_id, но без hh_discard_synced_at
        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id="test_nego_123",
            hh_chat_id="test_chat_456",
            reject_reason="Не подходит опыт",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        # Моки hh-клиента
        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token, \
             patch('app.services.integrations.hh.client.discard_negotiation') as mock_discard, \
             patch('app.services.integrations.hh.client.send_chat_message') as mock_send_msg:

            mock_token.return_value = "test_token"
            mock_discard.return_value = True  # Успешный 204 response
            mock_send_msg.return_value = {"id": "msg_789"}

            # Вызываем синхронизацию
            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            # Проверяем статистику
            assert stats["discarded"] == 1
            assert stats["failed"] == 0
            assert stats["skipped_no_token"] == 0

            # Проверяем вызовы hh-клиента
            mock_discard.assert_called_once_with("test_token", "test_nego_123")
            mock_send_msg.assert_called_once_with("test_token", "test_chat_456", POLITE_REJECTION_TEXT)

            # Проверяем обновление application
            await db_session.refresh(application)
            assert application.hh_discard_synced_at is not None

            # Проверяем создание исходящего сообщения
            messages = await db_session.execute(
                select(Message).where(
                    Message.application_id == application.id,
                    Message.direction == "out",
                    Message.channel == "hh"
                )
            )
            message = messages.scalar_one_or_none()
            assert message is not None
            assert message.sender_type == "ai"
            assert message.body == POLITE_REJECTION_TEXT
            assert message.external_id == "msg_789"

    @pytest.mark.asyncio
    async def test_sync_with_lazy_chat_id_resolution(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест ленивого получения chat_id из negotiation"""

        # Вежливое сообщение шлётся только при auto_reject_message=True (см. сервис)
        test_vacancy.auto_reject_message = True

        # Создаём заявку без chat_id
        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id="test_nego_456",
            hh_chat_id=None,  # Отсутствует
            reject_reason="Не подходит",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token, \
             patch('app.services.integrations.hh.client.get_negotiation') as mock_get_nego, \
             patch('app.services.integrations.hh.client.discard_negotiation') as mock_discard, \
             patch('app.services.integrations.hh.client.send_chat_message') as mock_send_msg:

            mock_token.return_value = "test_token"
            mock_get_nego.return_value = {"chat_id": "resolved_chat_789"}
            mock_discard.return_value = True
            mock_send_msg.return_value = {"id": "msg_555"}

            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            # Проверяем, что chat_id был получен и сохранён
            mock_get_nego.assert_called_once_with("test_token", "test_nego_456")
            await db_session.refresh(application)
            assert application.hh_chat_id == "resolved_chat_789"

            # Проверяем отправку сообщения с полученным chat_id
            mock_send_msg.assert_called_once_with("test_token", "resolved_chat_789", POLITE_REJECTION_TEXT)

            assert stats["discarded"] == 1

    @pytest.mark.asyncio
    async def test_sync_discard_failure_no_sync_flag(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест: при сбое discard флаг синхронизации не ставится (ретрай)"""

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id="test_nego_fail",
            hh_chat_id="test_chat_fail",
            reject_reason="Не подходит",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token, \
             patch('app.services.integrations.hh.client.discard_negotiation') as mock_discard, \
             patch('app.services.integrations.hh.client.send_chat_message') as mock_send_msg:

            mock_token.return_value = "test_token"
            mock_discard.side_effect = Exception("hh API error")

            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            # Проверяем статистику
            assert stats["discarded"] == 0
            assert stats["failed"] == 1

            # Проверяем, что флаг НЕ установлен (ретрай на следующем проходе)
            await db_session.refresh(application)
            assert application.hh_discard_synced_at is None

            # Сообщение не должно было отправляться
            mock_send_msg.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_message_failure_keeps_discard(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест: сбой отправки сообщения не откатывает discard"""

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id="test_nego_msg_fail",
            hh_chat_id="test_chat_msg_fail",
            reject_reason="Не подходит",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token, \
             patch('app.services.integrations.hh.client.discard_negotiation') as mock_discard, \
             patch('app.services.integrations.hh.client.send_chat_message') as mock_send_msg:

            mock_token.return_value = "test_token"
            mock_discard.return_value = True  # Успешно
            mock_send_msg.side_effect = Exception("Chat message failed")

            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            # discard считается успешным, даже если сообщение не отправилось
            assert stats["discarded"] == 1
            assert stats["failed"] == 0

            # Флаг синхронизации должен быть установлен
            await db_session.refresh(application)
            assert application.hh_discard_synced_at is not None

            # Исходящее сообщение не должно было быть сохранено
            messages = await db_session.execute(
                select(Message).where(
                    Message.application_id == application.id,
                    Message.direction == "out"
                )
            )
            assert messages.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_sync_idempotency(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест идемпотентности: уже синхронизированные не обрабатываются повторно"""

        # Создаём уже синхронизированную заявку
        sync_time = datetime.now(timezone.utc)
        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id="test_nego_synced",
            hh_chat_id="test_chat_synced",
            hh_discard_synced_at=sync_time,  # Уже синхронизирована
            reject_reason="Уже отклонён",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token, \
             patch('app.services.integrations.hh.client.discard_negotiation') as mock_discard:

            mock_token.return_value = "test_token"

            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            # Никакие действия не выполняются
            assert stats["discarded"] == 0
            assert stats["failed"] == 0
            mock_discard.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skips_non_hh_rejections(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест: отказы без hh_negotiation_id не обрабатываются"""

        # Создаём обычную (не-hh) отклонённую заявку
        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id=None,  # Не hh-кандидат
            reject_reason="Обычный отказ",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token, \
             patch('app.services.integrations.hh.client.discard_negotiation') as mock_discard:

            mock_token.return_value = "test_token"

            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            # Никакие hh-действия не выполняются
            assert stats["discarded"] == 0
            assert stats["failed"] == 0
            mock_discard.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_no_valid_token(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест обработки отсутствия валидного токена"""

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id="test_nego_no_token",
            reject_reason="Не подходит",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token:
            # Эмулируем отсутствие интеграции/токена
            from app.core.errors import NotFoundError
            mock_token.side_effect = NotFoundError("Интеграция hh.ru не найдена")

            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            # Пропускаем из-за отсутствия токена
            assert stats["discarded"] == 0
            assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_sync_already_discarded_wrong_state(
        self, db_session, test_company, admin_user, test_vacancy, test_candidate
    ):
        """Тест: отклик уже в отказе на hh (discard→False, wrong_state) → помечаем
        synced, сообщение НЕ шлём, не считаем ошибкой (не ретраим)."""

        application = Application(
            company_id=test_company.id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="rejected",
            hh_negotiation_id="test_nego_already_discarded",
            hh_chat_id="test_chat_ad",
            reject_reason="Не подходит",
            reject_side="company"
        )
        db_session.add(application)
        await db_session.commit()

        with patch('app.services.integrations.hh.service.get_valid_access_token') as mock_token, \
             patch('app.services.integrations.hh.client.discard_negotiation') as mock_discard, \
             patch('app.services.integrations.hh.client.get_negotiation') as mock_get_nego, \
             patch('app.services.integrations.hh.client.send_chat_message') as mock_send_msg:

            mock_token.return_value = "test_token"
            mock_discard.return_value = False  # wrong_state — голый discard не прошёл
            # Проверка реального состояния на hh: отклик УЖЕ в отказе → already_discarded
            mock_get_nego.return_value = {"employer_state": {"id": "discard_by_employer"}}

            stats = await sync_company_rejections(db_session, test_company.id, limit=10)

            assert stats["discarded"] == 0
            assert stats["already_discarded"] == 1
            assert stats["failed"] == 0
            # Сообщение НЕ отправляется (кандидат уже отклонён на hh)
            mock_send_msg.assert_not_called()
            # Флаг synced ВЫСТАВЛЕН (повторно не берём)
            await db_session.refresh(application)
            assert application.hh_discard_synced_at is not None
            assert stats["skipped_no_token"] == -1  # Индикатор отсутствия токена