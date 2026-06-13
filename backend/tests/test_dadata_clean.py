"""Tests for DaData Clean API functionality"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.dadata import clean_phone, clean_email, clean_name


class TestDaDataCleanAPI:

    @patch('app.services.dadata.settings.DADATA_API_KEY', 'test_key')
    @patch('app.services.dadata.settings.DADATA_SECRET_KEY', 'test_secret')
    async def test_clean_phone_success(self):
        """Test successful phone cleaning"""
        mock_response_data = [{
            "phone": "+7 495 123 45 67",
            "type": "Мобильный",
            "provider": "МТС",
            "region": "Москва",
            "qc": 0
        }]

        with patch('app.services.dadata.httpx.AsyncClient') as mock_client:
            # httpx Response.json()/.raise_for_status() — СИНХРОННЫЕ; client.post — async.
            _resp = MagicMock()
            _resp.json.return_value = mock_response_data
            _resp.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=_resp)

            result = await clean_phone("79951234567")

            assert result["phone"] == "+7 495 123 45 67"
            assert result["qc"] == 0
            assert result["provider"] == "МТС"

    @patch('app.services.dadata.settings.DADATA_API_KEY', '')
    @patch('app.services.dadata.settings.DADATA_SECRET_KEY', '')
    async def test_clean_phone_no_keys(self):
        """Test phone cleaning without API keys"""
        result = await clean_phone("79951234567")
        assert result is None

    async def test_clean_phone_empty_input(self):
        """Test phone cleaning with empty input"""
        result = await clean_phone("")
        assert result is None

        result = await clean_phone("   ")
        assert result is None

        result = await clean_phone(None)
        assert result is None

    @patch('app.services.dadata.settings.DADATA_API_KEY', 'test_key')
    @patch('app.services.dadata.settings.DADATA_SECRET_KEY', 'test_secret')
    async def test_clean_email_success(self):
        """Test successful email cleaning"""
        mock_response_data = [{
            "email": "test@example.com",
            "type": "Личный",
            "qc": 0
        }]

        with patch('app.services.dadata.httpx.AsyncClient') as mock_client:
            # httpx Response.json()/.raise_for_status() — СИНХРОННЫЕ; client.post — async.
            _resp = MagicMock()
            _resp.json.return_value = mock_response_data
            _resp.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=_resp)

            result = await clean_email("test@example.com")

            assert result["email"] == "test@example.com"
            assert result["qc"] == 0

    @patch('app.services.dadata.settings.DADATA_API_KEY', 'test_key')
    @patch('app.services.dadata.settings.DADATA_SECRET_KEY', 'test_secret')
    async def test_clean_name_success(self):
        """Test successful name cleaning"""
        mock_response_data = [{
            "surname": "Иванов",
            "name": "Иван",
            "patronymic": "Иванович",
            "gender": "М",
            "qc": 0
        }]

        with patch('app.services.dadata.httpx.AsyncClient') as mock_client:
            # httpx Response.json()/.raise_for_status() — СИНХРОННЫЕ; client.post — async.
            _resp = MagicMock()
            _resp.json.return_value = mock_response_data
            _resp.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=_resp)

            result = await clean_name("Иванов Иван Иванович")

            assert result["surname"] == "Иванов"
            assert result["name"] == "Иван"
            assert result["patronymic"] == "Иванович"
            assert result["gender"] == "М"
            assert result["qc"] == 0

    @patch('app.services.dadata.settings.DADATA_API_KEY', 'test_key')
    @patch('app.services.dadata.settings.DADATA_SECRET_KEY', 'test_secret')
    async def test_clean_api_network_error(self):
        """Test graceful handling of network errors"""
        import httpx

        with patch('app.services.dadata.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.HTTPError("Network error")

            result = await clean_phone("79951234567")
            assert result is None

            result = await clean_email("test@example.com")
            assert result is None

            result = await clean_name("Тест")
            assert result is None