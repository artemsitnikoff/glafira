"""Tests for exception handlers"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import Request
from starlette.testclient import TestClient
import httpx

from app.main import app
from app.core.errors import generic_exception_handler, GlafiraParseError
from app.services.glafira.client import call_json, call_text


class TestGenericExceptionHandler:

    async def test_generic_exception_handler_returns_500_with_unified_format(self):
        """Test that generic_exception_handler returns 500 with correct format"""
        request = Request({"type": "http", "method": "GET", "url": "http://test", "headers": []})
        exc = Exception("test exception")

        response = await generic_exception_handler(request, exc)

        assert response.status_code == 500

        # Parse the response body
        import json
        body = json.loads(response.body)

        assert body == {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутренняя ошибка сервера",
                "details": None
            }
        }

    def test_generic_exception_handler_via_testclient(self):
        """Test generic exception handler via integration test"""
        # Create a route that raises an unhandled exception
        from fastapi import APIRouter
        test_router = APIRouter()

        @test_router.get("/test-exception")
        async def test_exception():
            raise ValueError("test boom")

        app.include_router(test_router)

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/test-exception")

                assert response.status_code == 500
                body = response.json()
                assert body["error"]["code"] == "INTERNAL_ERROR"
                assert body["error"]["message"] == "Внутренняя ошибка сервера"
                assert body["error"]["details"] is None
                # Verify that exception text "test boom" does not leak in response
                assert "test boom" not in str(body)
                assert "ValueError" not in str(body)
        finally:
            # Clean up - remove the test router
            app.router.routes = [r for r in app.router.routes if not (hasattr(r, 'path') and r.path == "/test-exception")]


class TestGlafiraClientNetworkErrors:

    @patch('app.config.settings.OPENROUTER_API_KEY', 'test-key')
    async def test_call_json_network_error_raises_glafira_parse_error(self):
        """Test that network errors in call_json raise GlafiraParseError"""

        with patch('app.services.glafira.client._make_openrouter_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(GlafiraParseError) as exc_info:
                await call_json(
                    system="test system",
                    user="test user"
                )

            assert exc_info.value.status_code == 502
            assert exc_info.value.details is not None
            assert "Сетевая ошибка при обращении к OpenRouter" in exc_info.value.details["reason"]
            assert "ConnectError" in exc_info.value.details["reason"]

    @patch('app.config.settings.OPENROUTER_API_KEY', 'test-key')
    async def test_call_text_network_error_raises_glafira_parse_error(self):
        """Test that network errors in call_text raise GlafiraParseError"""

        with patch('app.services.glafira.client._make_openrouter_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = httpx.ReadTimeout("Read timeout")

            with pytest.raises(GlafiraParseError) as exc_info:
                await call_text(
                    system="test system",
                    user="test user"
                )

            assert exc_info.value.status_code == 502
            assert exc_info.value.details is not None
            assert "Сетевая ошибка при обращении к OpenRouter" in exc_info.value.details["reason"]
            assert "ReadTimeout" in exc_info.value.details["reason"]

    @patch('app.config.settings.OPENROUTER_API_KEY', '')
    async def test_empty_api_key_still_raises_glafira_parse_error(self):
        """Test that empty OPENROUTER_API_KEY still raises GlafiraParseError immediately"""

        with pytest.raises(GlafiraParseError) as exc_info:
            await call_json(system="test", user="test")

        assert "OPENROUTER_API_KEY not configured" in exc_info.value.details["reason"]

        with pytest.raises(GlafiraParseError) as exc_info:
            await call_text(system="test", user="test")

        assert "OPENROUTER_API_KEY not configured" in exc_info.value.details["reason"]