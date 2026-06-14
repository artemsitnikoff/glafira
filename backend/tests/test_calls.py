"""Тесты для функциональности звонков Mango Office"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.models import Call, CallSyncJob, Candidate
from app.services.call_sync import _parse_stats_csv, create_call_sync_job
from app.core.errors import ConflictError

pytestmark = pytest.mark.asyncio


# Моки для внешних сервисов
@pytest.fixture
def mock_mango_client():
    """Мок Mango Client"""
    mock = AsyncMock()
    mock.request_stats.return_value = {"key": "test_key_123"}
    mock.get_stats_result.return_value = """records;start;finish;answer;from_extension;from_number;to_extension;to_number;disconnect_reason;entry_id;line_number
record1;1640995200;1640995260;1;101;+79001234567;;+79007654321;completed;call_001;line_001
record2;1640995300;1640995320;0;;+79001111111;102;+79002222222;no_answer;call_002;line_002"""
    mock.download_recording.return_value = b"fake_mp3_data"
    return mock


@pytest.fixture
def mock_transcription():
    """Мок функций транскрибации"""
    mock = AsyncMock()
    mock.return_value = {
        "success": True,
        "full_text": "S1 [0:00]: Здравствуйте, это рекрутер\nS2 [0:05]: Здравствуйте, слушаю",
        "segments": [
            {"speaker": "S1", "start": 0.0, "end": 3.0, "text": "Здравствуйте, это рекрутер"},
            {"speaker": "S2", "start": 5.0, "end": 7.0, "text": "Здравствуйте, слушаю"}
        ],
        "speakers_count": 2,
        "error": None
    }
    return mock


@pytest.fixture
def mock_analysis():
    """Мок анализа звонка"""
    mock = AsyncMock()
    mock.return_value = {
        "summary": "Первичный контакт с кандидатом",
        "hint": "Хорошее начало разговора",
        "hint_tone": "good"
    }
    return mock


class TestCSVParsing:
    """Тесты парсинга CSV от Mango Office"""

    def test_parse_stats_csv_success(self):
        """Тест успешного парсинга CSV"""
        csv_content = """records;start;finish;answer;from_extension;from_number;to_extension;to_number;disconnect_reason;entry_id;line_number
record1;1640995200;1640995260;1;101;;;+79007654321;completed;call_001;line_001
;1640995300;1640995320;0;;+79001111111;102;;no_answer;call_002;line_002"""

        calls = _parse_stats_csv(csv_content)

        assert len(calls) == 2

        # Первый звонок: исходящий (есть from_extension и внешний to_number)
        call1 = calls[0]
        assert call1["external_id"] == "call_001"
        assert call1["direction"] == "out"
        assert call1["candidate_number"] == "+79007654321"
        assert call1["duration_sec"] == 60

        # Второй звонок: входящий (есть to_extension и внешний from_number)
        call2 = calls[1]
        assert call2["external_id"] == "call_002"
        assert call2["direction"] == "in"
        assert call2["candidate_number"] == "+79001111111"

    def test_parse_csv_empty(self):
        """Тест парсинга пустого CSV"""
        calls = _parse_stats_csv("")
        assert calls == []

    def test_parse_csv_malformed_rows(self):
        """Тест обработки некорректных строк CSV"""
        csv_content = """records;start;finish;answer;from_extension;from_number;to_extension;to_number;disconnect_reason;entry_id;line_number
short_row;123
;1640995200;1640995260;1;101;;102;+79007654321;completed;;
normal;1640995300;1640995320;0;;+79001111111;102;;no_answer;call_002;line_002"""

        calls = _parse_stats_csv(csv_content)

        # Должна остаться только одна валидная запись
        assert len(calls) == 1
        assert calls[0]["external_id"] == "call_002"


class TestPhoneMatching:
    """Тесты сопоставления номеров телефонов с кандидатами"""

    async def test_phone_matching_various_formats(self, async_client, db_session, test_company, test_candidate):
        """Тест матчинга номеров в разных форматах"""
        from app.services.candidate_dedup import find_duplicate_candidates

        # Обновляем телефон кандидата
        test_candidate.phone = "+79001234567"
        await db_session.commit()

        # Тестируем разные форматы одного номера
        test_formats = [
            "+79001234567",  # международный
            "79001234567",   # без плюса
            "89001234567",   # российский формат
            "+7 900 123 45 67"  # с пробелами
        ]

        for phone_format in test_formats:
            candidates = await find_duplicate_candidates(
                db_session, test_company.id, phone_format, None
            )
            assert len(candidates) == 1
            assert candidates[0].id == test_candidate.id

    async def test_phone_matching_company_isolation(self, async_client, db_session):
        """Тест изоляции по компаниям при матчинге телефонов"""
        from app.services.candidate_dedup import find_duplicate_candidates
        from app.models import Company

        # Создаем вторую компанию и кандидата
        company_b = Company(name="Компания B")
        db_session.add(company_b)
        await db_session.flush()

        candidate_b = Candidate(
            company_id=company_b.id,
            last_name="Б",
            first_name="Кандидат",
            source="manual",
            phone="+79001234567"
        )
        db_session.add(candidate_b)
        await db_session.commit()

        # Ищем из компании A - не должно найти кандидата из компании B
        from app.config import settings
        company_a_id = settings.DEFAULT_COMPANY_ID

        candidates = await find_duplicate_candidates(
            db_session, company_a_id, "+79001234567", None
        )
        assert len(candidates) == 0  # Не должно найти кандидата из другой компании


class TestCallSyncJob:
    """Тесты джобов синхронизации звонков"""

    async def test_create_sync_job_success(self, db_session, test_company, admin_user):
        """Тест успешного создания джоба синхронизации"""
        job = await create_call_sync_job(
            db_session, test_company.id, admin_user.id
        )

        assert job.company_id == test_company.id
        assert job.status == "running"
        assert job.total == 0
        assert job.matched == 0
        assert job.created == 0

    async def test_create_sync_job_conflict(self, db_session, test_company, admin_user):
        """Тест конфликта при создании второго джоба"""
        # Создаем первый джоб
        await create_call_sync_job(db_session, test_company.id, admin_user.id)

        # Попытка создать второй должна вызвать ConflictError
        with pytest.raises(ConflictError):
            await create_call_sync_job(db_session, test_company.id, admin_user.id)


class TestCallAPI:
    """Тесты API эндпоинтов звонков"""

    async def test_get_candidate_calls_empty(self, async_client, test_candidate, admin_headers):
        """Тест получения пустого списка звонков кандидата"""
        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/calls",
            headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_candidate_calls_with_data(self, async_client, db_session, test_candidate, admin_headers):
        """Тест получения списка звонков с данными"""
        # Создаем тестовый звонок
        call = Call(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            external_id="test_call_001",
            direction="out",
            from_number="+79001111111",
            to_number=test_candidate.phone,
            duration_sec=120,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            transcribe_status="none"
        )
        db_session.add(call)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/candidates/{test_candidate.id}/calls",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["external_id"] == "test_call_001"
        assert data[0]["direction"] == "out"
        assert data[0]["duration_sec"] == 120

    async def test_get_candidate_calls_not_found(self, async_client, admin_headers):
        """Тест 404 для несуществующего кандидата"""
        fake_id = str(uuid4())
        response = await async_client.get(
            f"/api/v1/candidates/{fake_id}/calls",
            headers=admin_headers
        )
        assert response.status_code == 404

    async def test_get_call_by_id(self, async_client, db_session, test_candidate, admin_headers):
        """Тест получения звонка по ID"""
        call = Call(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            external_id="test_call_002",
            direction="in",
            transcript="Тестовая расшифровка",
            transcribe_status="done"
        )
        db_session.add(call)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/calls/{call.id}",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(call.id)
        assert data["transcript"] == "Тестовая расшифровка"

    @patch('app.services.integrations.mango.service.get_status')
    async def test_start_sync_mango_not_configured(self, mock_get_status, async_client, admin_headers):
        """Тест запуска синхронизации без настроенного Mango"""
        mock_get_status.return_value = {"configured": False, "verified": False}

        response = await async_client.post(
            "/api/v1/calls/sync",
            headers=admin_headers
        )
        # Должен создать джоб, который завершится с ошибкой в фоне
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data

    async def test_manager_access_forbidden(self, async_client, manager_headers):
        """Тест запрета доступа для manager роли"""
        response = await async_client.post(
            "/api/v1/calls/sync",
            headers=manager_headers
        )
        assert response.status_code == 403

    @patch('app.services.glafira.transcription.transcribe_audio')
    async def test_transcribe_call_success(self, mock_transcribe, async_client, db_session,
                                         test_candidate, admin_headers, mock_transcription):
        """Тест успешной расшифровки звонка"""
        mock_transcribe.return_value = mock_transcription.return_value

        # Создаем звонок с записью
        call = Call(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            external_id="test_call_003",
            recording_id="rec_123",
            transcribe_status="none"
        )
        db_session.add(call)
        await db_session.commit()

        # Мокаем загрузку записи и Mango клиент
        with patch('app.services.integrations.mango.service.get_status') as mock_status, \
             patch('app.api.v1.calls.MangoClient') as mock_client_class:

            mock_status.return_value = {"configured": True, "verified": True}
            mock_client = AsyncMock()
            mock_client.download_recording.return_value = b"fake_mp3_data"
            mock_client_class.return_value = mock_client

            response = await async_client.post(
                f"/api/v1/calls/{call.id}/transcribe",
                headers=admin_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["transcribe_status"] == "running"

    async def test_transcribe_call_no_recording(self, async_client, db_session,
                                              test_candidate, admin_headers):
        """Тест расшифровки звонка без записи"""
        call = Call(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            external_id="test_call_004",
            recording_id=None,  # Нет записи
            transcribe_status="none"
        )
        db_session.add(call)
        await db_session.commit()

        response = await async_client.post(
            f"/api/v1/calls/{call.id}/transcribe",
            headers=admin_headers
        )
        assert response.status_code == 400
        assert "нет записи" in response.json()["error"]["message"].lower()

    async def test_transcribe_call_already_done(self, async_client, db_session,
                                              test_candidate, admin_headers):
        """Тест кэширования готовой расшифровки"""
        call = Call(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            external_id="test_call_005",
            recording_id="rec_456",
            transcript="Готовая расшифровка",
            transcribe_status="done"
        )
        db_session.add(call)
        await db_session.commit()

        response = await async_client.post(
            f"/api/v1/calls/{call.id}/transcribe",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["transcript"] == "Готовая расшифровка"
        assert data["transcribe_status"] == "done"

    async def test_transcribe_call_toctou_protection(self, async_client, db_session,
                                                   test_candidate, admin_headers):
        """Тест TOCTOU-защиты при одновременной расшифровке"""
        call = Call(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            external_id="test_call_006",
            recording_id="rec_789",
            transcribe_status="running"  # Уже выполняется
        )
        db_session.add(call)
        await db_session.commit()

        response = await async_client.post(
            f"/api/v1/calls/{call.id}/transcribe",
            headers=admin_headers
        )
        assert response.status_code == 409  # Conflict