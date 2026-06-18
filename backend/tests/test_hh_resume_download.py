"""Тесты скачивания PDF резюме hh в раздел Документы кандидата.

Офлайн — никакой сети, все внешние вызовы замокированы по import-site.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select

from app.models import Document, Candidate
from app.services.integrations.hh import service as hh_service


# ---------------------------------------------------------------------------
# Вспомогательные данные
# ---------------------------------------------------------------------------

_PDF_BYTES = b"%PDF-1.4 fake pdf content"

_FULL_RESUME = {
    "id": "abc123",
    "first_name": "Иван",
    "last_name": "Петров",
    "download": {
        "pdf": {"url": "https://hh.ru/api_resume_converter/abc123/Иван_Петров.pdf?type=pdf"},
        "rtf": {"url": "https://hh.ru/api_resume_converter/abc123/Иван_Петров.rtf?type=rtf"},
    },
}

_RESUME_NO_DOWNLOAD = {
    "id": "nofile",
    "first_name": "Нет",
    "last_name": "Файла",
}


# ---------------------------------------------------------------------------
# Тесты save_hh_resume_document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSaveHhResumeDocument:
    """Тесты хелпера сохранения PDF резюме hh."""

    @patch("app.services.integrations.hh.service.storage_service")
    @patch("app.services.integrations.hh.service.hh_client")
    async def test_creates_document_on_success(
        self,
        mock_hh_client,
        mock_storage,
        db_session,
        test_company,
        test_candidate,
    ):
        """При успешной загрузке создаётся Document(source='hh', file_type='pdf')."""
        mock_hh_client.download_resume_file = AsyncMock(return_value=_PDF_BYTES)
        mock_storage.save = AsyncMock(return_value="company/cand/uuid_resume.pdf")

        result = await hh_service.save_hh_resume_document(
            session=db_session,
            company_id=test_candidate.company_id,
            candidate=test_candidate,
            full_resume=_FULL_RESUME,
            access_token="fake_token",
        )

        assert result is True

        doc = (await db_session.execute(
            select(Document).where(
                Document.candidate_id == test_candidate.id,
                Document.source == "hh",
            )
        )).scalar_one_or_none()

        assert doc is not None
        assert doc.file_type == "pdf"
        assert doc.size_bytes == len(_PDF_BYTES)
        assert doc.company_id == test_candidate.company_id
        assert "Резюме hh" in doc.filename
        assert doc.filename.endswith(".pdf")

    @patch("app.services.integrations.hh.service.storage_service")
    @patch("app.services.integrations.hh.service.hh_client")
    async def test_sets_hh_resume_file_saved_flag(
        self,
        mock_hh_client,
        mock_storage,
        db_session,
        test_company,
        test_candidate,
    ):
        """После сохранения candidate.extra['hh_resume_file_saved'] == True."""
        mock_hh_client.download_resume_file = AsyncMock(return_value=_PDF_BYTES)
        mock_storage.save = AsyncMock(return_value="company/cand/uuid_resume.pdf")

        await hh_service.save_hh_resume_document(
            session=db_session,
            company_id=test_candidate.company_id,
            candidate=test_candidate,
            full_resume=_FULL_RESUME,
            access_token="fake_token",
        )

        assert (test_candidate.extra or {}).get("hh_resume_file_saved") is True
        assert (test_candidate.extra or {}).get("hh_resume_id") == "abc123"

    @patch("app.services.integrations.hh.service.storage_service")
    @patch("app.services.integrations.hh.service.hh_client")
    async def test_dedup_by_flag_returns_false(
        self,
        mock_hh_client,
        mock_storage,
        db_session,
        test_company,
        test_candidate,
    ):
        """Второй вызов возвращает False и НЕ создаёт второй Document (дедуп по флагу extra)."""
        mock_hh_client.download_resume_file = AsyncMock(return_value=_PDF_BYTES)
        mock_storage.save = AsyncMock(return_value="company/cand/uuid_resume.pdf")

        # Первый вызов — успех
        r1 = await hh_service.save_hh_resume_document(
            session=db_session,
            company_id=test_candidate.company_id,
            candidate=test_candidate,
            full_resume=_FULL_RESUME,
            access_token="fake_token",
        )
        assert r1 is True

        # Второй вызов — дедуп
        r2 = await hh_service.save_hh_resume_document(
            session=db_session,
            company_id=test_candidate.company_id,
            candidate=test_candidate,
            full_resume=_FULL_RESUME,
            access_token="fake_token",
        )
        assert r2 is False

        # Документ ровно один
        docs = (await db_session.execute(
            select(Document).where(
                Document.candidate_id == test_candidate.id,
                Document.source == "hh",
            )
        )).scalars().all()
        assert len(docs) == 1

    @patch("app.services.integrations.hh.service.storage_service")
    @patch("app.services.integrations.hh.service.hh_client")
    async def test_dedup_by_existing_document(
        self,
        mock_hh_client,
        mock_storage,
        db_session,
        test_company,
        test_candidate,
    ):
        """Если в БД уже есть Document(source='hh') — возвращает False без обращения к storage."""
        from datetime import datetime, timezone
        existing = Document(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            filename="Резюме hh — Иван Петров.pdf",
            file_type="pdf",
            size_bytes=100,
            storage_path="some/path.pdf",
            source="hh",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(existing)
        await db_session.flush()

        result = await hh_service.save_hh_resume_document(
            session=db_session,
            company_id=test_candidate.company_id,
            candidate=test_candidate,
            full_resume=_FULL_RESUME,
            access_token="fake_token",
        )

        assert result is False
        mock_storage.save.assert_not_called()

    @patch("app.services.integrations.hh.service.storage_service")
    @patch("app.services.integrations.hh.service.hh_client")
    async def test_no_download_url_returns_false(
        self,
        mock_hh_client,
        mock_storage,
        db_session,
        test_company,
        test_candidate,
    ):
        """Если в резюме нет поля download.pdf.url — возвращает False, storage не вызывается."""
        result = await hh_service.save_hh_resume_document(
            session=db_session,
            company_id=test_candidate.company_id,
            candidate=test_candidate,
            full_resume=_RESUME_NO_DOWNLOAD,
            access_token="fake_token",
        )

        assert result is False
        mock_hh_client.download_resume_file.assert_not_called()
        mock_storage.save.assert_not_called()

    @patch("app.services.integrations.hh.service.storage_service")
    @patch("app.services.integrations.hh.service.hh_client")
    async def test_download_returns_none_returns_false(
        self,
        mock_hh_client,
        mock_storage,
        db_session,
        test_company,
        test_candidate,
    ):
        """Если download_resume_file вернул None (403/404/429/таймаут) — возвращает False без записи."""
        mock_hh_client.download_resume_file = AsyncMock(return_value=None)

        result = await hh_service.save_hh_resume_document(
            session=db_session,
            company_id=test_candidate.company_id,
            candidate=test_candidate,
            full_resume=_FULL_RESUME,
            access_token="fake_token",
        )

        assert result is False
        mock_storage.save.assert_not_called()

        # Документ не создан
        doc = (await db_session.execute(
            select(Document).where(
                Document.candidate_id == test_candidate.id,
                Document.source == "hh",
            )
        )).scalar_one_or_none()
        assert doc is None


# ---------------------------------------------------------------------------
# Тесты download_resume_file в клиенте
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDownloadResumeFile:
    """Тесты метода hh_client.download_resume_file."""

    @patch("app.services.integrations.hh.client.httpx.AsyncClient")
    async def test_returns_bytes_on_200(self, mock_async_client_cls):
        """HTTP 200 → возвращает bytes."""
        from app.services.integrations.hh import client as hh_client

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _PDF_BYTES

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client_cls.return_value = mock_client_instance

        result = await hh_client.download_resume_file("tok", "https://hh.ru/fake.pdf")

        assert result == _PDF_BYTES

    @patch("app.services.integrations.hh.client.httpx.AsyncClient")
    async def test_returns_none_on_403(self, mock_async_client_cls):
        """HTTP 403 → None (нет услуги)."""
        from app.services.integrations.hh import client as hh_client

        mock_response = AsyncMock()
        mock_response.status_code = 403
        mock_response.content = b""

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client_cls.return_value = mock_client_instance

        result = await hh_client.download_resume_file("tok", "https://hh.ru/fake.pdf")
        assert result is None

    @patch("app.services.integrations.hh.client.httpx.AsyncClient")
    async def test_returns_none_on_429(self, mock_async_client_cls):
        """HTTP 429 → None (суточный лимит)."""
        from app.services.integrations.hh import client as hh_client

        mock_response = AsyncMock()
        mock_response.status_code = 429
        mock_response.content = b""

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client_cls.return_value = mock_client_instance

        result = await hh_client.download_resume_file("tok", "https://hh.ru/fake.pdf")
        assert result is None

    @patch("app.services.integrations.hh.client.httpx.AsyncClient")
    async def test_returns_none_if_too_large(self, mock_async_client_cls):
        """Файл > 10 МБ → None."""
        from app.services.integrations.hh import client as hh_client

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b"x" * (11 * 1024 * 1024)  # 11 MB

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client_cls.return_value = mock_client_instance

        result = await hh_client.download_resume_file("tok", "https://hh.ru/big.pdf")
        assert result is None

    @patch("app.services.integrations.hh.client.httpx.AsyncClient")
    async def test_returns_none_on_exception(self, mock_async_client_cls):
        """Исключение сети → None (best-effort)."""
        import httpx
        from app.services.integrations.hh import client as hh_client

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_async_client_cls.return_value = mock_client_instance

        result = await hh_client.download_resume_file("tok", "https://hh.ru/fake.pdf")
        assert result is None
