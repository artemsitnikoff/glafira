"""Тесты self-healing отказа hh: discard_negotiation берёт URL из actions[].url
самого hh (GET /negotiations/{id}), а НЕ из хардкода.

Контракт discard_negotiation (сохраняется):
    True          — отклонён сейчас (204);
    False         — недоступен для отказа (нет action / wrong_state / resume_not_found / 404);
    raise         — транзиент (сеть / сбой get_negotiation / прочие ошибки).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.integrations.hh import client as hh_client
from app.core.errors import ValidationError


# URL, который САМ hh отдаёт в actions[].url активного отклика (self-healing источник).
DISCARD_URL = "https://api.hh.ru/negotiations/discard_by_employer/nego_123"


def _nego_with_discard_action(enabled: bool = True, method: str = "PUT") -> dict:
    """Объект отклика hh с действием discard_by_employer (как в реальном ответе)."""
    return {
        "id": "nego_123",
        "state": {"id": "response"},
        "employer_state": {"id": "response"},
        "chat_id": "chat_1",
        "actions": [
            {"id": "view", "enabled": True, "method": "GET",
             "url": "https://api.hh.ru/negotiations/nego_123"},
            {"id": "discard_by_employer", "enabled": enabled, "method": method,
             "url": DISCARD_URL},
        ],
    }


class TestDiscardNegotiationSelfHealing:
    """discard_negotiation тянет url/method действия из actions[] самого hh."""

    @patch('app.services.integrations.hh.client._get_client')
    @patch('app.services.integrations.hh.client.get_negotiation')
    async def test_discard_uses_url_from_actions_and_returns_true_on_204(
        self, mock_get_nego, mock_get_client
    ):
        """actions содержит discard_by_employer(enabled) + PUT на его url вернул 204
        → True; и PUT ушёл ИМЕННО на url из actions (а не на хардкод-путь)."""
        mock_get_nego.return_value = _nego_with_discard_action(enabled=True, method="PUT")

        # httpx Response: .status_code/.text — синхронные → MagicMock.
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = await hh_client.discard_negotiation("test_token", "nego_123")

        assert result is True
        # get_negotiation вызван ровно раз (источник url) — с тем же токеном/id.
        mock_get_nego.assert_awaited_once_with("test_token", "nego_123")
        # HTTP-запрос ушёл именно на url из actions[] (self-healing), method="PUT".
        mock_client.request.assert_awaited_once()
        call_args = mock_client.request.await_args
        assert call_args.args[0] == "PUT"
        assert call_args.args[1] == DISCARD_URL
        # Bearer-заголовок проставлен.
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer test_token"

    @patch('app.services.integrations.hh.client._get_client')
    @patch('app.services.integrations.hh.client.get_negotiation')
    async def test_no_discard_action_returns_false_without_http(
        self, mock_get_nego, mock_get_client
    ):
        """actions пустой (нет discard_by_employer) → False, и HTTP-запрос НЕ вызывался
        вовсе (никакого хардкод-фолбэка на старый URL)."""
        mock_get_nego.return_value = {
            "id": "nego_123",
            "state": {"id": "discard_by_applicant"},
            "actions": [
                {"id": "view", "enabled": True, "method": "GET",
                 "url": "https://api.hh.ru/negotiations/nego_123"},
            ],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_get_client.return_value = mock_client

        result = await hh_client.discard_negotiation("test_token", "nego_123")

        assert result is False
        # PUT/любой HTTP-запрос НЕ должен был уйти — раз hh не предлагает discard.
        mock_client.request.assert_not_called()

    @patch('app.services.integrations.hh.client._get_client')
    @patch('app.services.integrations.hh.client.get_negotiation')
    async def test_discard_action_disabled_returns_false_without_http(
        self, mock_get_nego, mock_get_client
    ):
        """action discard_by_employer есть, но enabled=false → трактуем как отсутствие
        действия → False, HTTP не вызывается."""
        mock_get_nego.return_value = _nego_with_discard_action(enabled=False)

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_get_client.return_value = mock_client

        result = await hh_client.discard_negotiation("test_token", "nego_123")

        assert result is False
        mock_client.request.assert_not_called()

    @patch('app.services.integrations.hh.client._get_client')
    @patch('app.services.integrations.hh.client.get_negotiation')
    async def test_put_403_resume_not_found_returns_false(
        self, mock_get_nego, mock_get_client
    ):
        """action есть, но PUT вернул 403 resume_not_found → False (недоступно, ретрай
        не поможет — вызывающий пометит synced)."""
        mock_get_nego.return_value = _nego_with_discard_action(enabled=True)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = '{"errors":[{"type":"resume_not_found"}]}'

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = await hh_client.discard_negotiation("test_token", "nego_123")

        assert result is False
        # запрос всё же ушёл на url из actions[]
        mock_client.request.assert_awaited_once()
        assert mock_client.request.await_args.args[1] == DISCARD_URL

    @patch('app.services.integrations.hh.client._get_client')
    @patch('app.services.integrations.hh.client.get_negotiation')
    async def test_get_negotiation_error_propagates_as_raise(
        self, mock_get_nego, mock_get_client
    ):
        """get_negotiation бросил (сеть/сбой) → discard_negotiation пробрасывает
        исключение (транзиент → ретрай вызывающим), НЕ возвращает False;
        HTTP-запрос отказа даже не начинается."""
        mock_get_nego.side_effect = ValidationError("Ошибка получения отклика hh.ru: timeout")

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_get_client.return_value = mock_client

        with pytest.raises(ValidationError):
            await hh_client.discard_negotiation("test_token", "nego_123")

        # До HTTP-запроса отказа не дошли (url взять неоткуда).
        mock_client.request.assert_not_called()
