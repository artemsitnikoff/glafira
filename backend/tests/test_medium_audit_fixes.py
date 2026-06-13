"""Тесты для исправлений Medium аудита"""

import json
import pytest
from uuid import uuid4

from app.services.glafira.client import _clean_markdown_fences
from app.schemas.settings import GlafiraSettingsUpdate


class TestRegexFenceFix:
    """Тесты исправления regex для очистки markdown fences"""

    def test_clean_markdown_fences_normal_case(self):
        """Обычная очистка ```json блоков"""
        text = "```json\n{\"test\": \"value\"}\n```"
        result = _clean_markdown_fences(text)
        assert result == '{"test": "value"}'

    def test_clean_markdown_fences_without_json_keyword(self):
        """Очистка ``` блоков без json"""
        text = "```\n{\"test\": \"value\"}\n```"
        result = _clean_markdown_fences(text)
        assert result == '{"test": "value"}'

    def test_clean_markdown_fences_preserves_internal_backticks(self):
        """JSON со строками, содержащими ``` в середине, не должен ломаться"""
        text = '```json\n{"prompt": "Use ```bash command``` here", "code": "```\\ntest\\n```"}\n```'
        result = _clean_markdown_fences(text)
        expected = '{"prompt": "Use ```bash command``` here", "code": "```\\ntest\\n```"}'
        assert result == expected

    def test_clean_markdown_fences_multiline_json_with_backticks(self):
        """Многострочный JSON с ``` внутри значений"""
        # JSON в одну строку (literal-переносы внутри значения сделали бы JSON невалидным);
        # внутри значений — маркеры ``` , которые НЕ должны быть съедены чисткой внешних fence.
        text = '''```json
{"description": "Code: ```python``` inline", "notes": "Another ``` marker"}
```'''
        result = _clean_markdown_fences(text)
        # Внешние ```json...``` убраны, внутренние ``` сохранены
        assert result.startswith('{')
        assert result.endswith('}')
        assert '```python```' in result
        # JSON валиден, внутренние ``` на месте в значении
        parsed = json.loads(result)
        assert '```python```' in parsed["description"]

    def test_clean_markdown_fences_no_fences(self):
        """Текст без fence блоков остается неизменным"""
        text = '{"test": "value"}'
        result = _clean_markdown_fences(text)
        assert result == '{"test": "value"}'


class TestSettingsLiteralValidation:
    """Тесты Literal валидации для GlafiraSettings"""

    def test_glafira_settings_update_valid_values(self):
        """Валидные значения проходят валидацию"""
        valid_data = {
            "tone": "friendly",
            "default_mode": "A",
            "turnover_source": "none"
        }
        schema = GlafiraSettingsUpdate(**valid_data)
        assert schema.tone == "friendly"
        assert schema.default_mode == "A"
        assert schema.turnover_source == "none"

    def test_glafira_settings_update_invalid_tone(self):
        """Невалидный tone отклоняется"""
        with pytest.raises(ValueError) as exc_info:
            GlafiraSettingsUpdate(tone="invalid_tone")
        assert "Input should be 'friendly', 'formal' or 'business'" in str(exc_info.value)

    def test_glafira_settings_update_invalid_default_mode(self):
        """Невалидный default_mode отклоняется"""
        with pytest.raises(ValueError) as exc_info:
            GlafiraSettingsUpdate(default_mode="Z")
        assert "Input should be 'A', 'B' or 'C'" in str(exc_info.value)

    def test_glafira_settings_update_invalid_turnover_source(self):
        """Невалидный turnover_source отклоняется"""
        with pytest.raises(ValueError) as exc_info:
            GlafiraSettingsUpdate(turnover_source="invalid_source")
        assert "Input should be 'none' or 'bitrix24'" in str(exc_info.value)


@pytest.mark.asyncio
class TestRBACFixes:
    """Тесты RBAC исправлений"""

    async def test_manager_cannot_remove_candidate_tag(
        self,
        async_client,
        manager_user
    ):
        """Менеджер не может удалять теги кандидатов"""
        # Логинимся как менеджер
        login_response = await async_client.post("/api/v1/auth/login", json={
            "email": manager_user.email,
            "password": "Glafira2026!"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Пытаемся удалить тег (любой валидный UUID)
        fake_candidate_id = str(uuid4())
        fake_tag_id = str(uuid4())
        response = await async_client.delete(
            f"/api/v1/candidates/{fake_candidate_id}/tags/{fake_tag_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"]

    async def test_manager_cannot_score_candidate(
        self,
        async_client,
        manager_user,
        test_candidate,
        test_vacancy
    ):
        """Менеджер не может оценивать кандидатов"""
        # Логинимся как менеджер
        login_response = await async_client.post("/api/v1/auth/login", json={
            "email": manager_user.email,
            "password": "Glafira2026!"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Пытаемся оценить кандидата с валидным телом
        response = await async_client.post(
            "/api/v1/glafira/score",
            json={
                "candidate_id": str(test_candidate.id),
                "vacancy_id": str(test_vacancy.id)
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"]

    async def test_manager_cannot_start_screening(
        self,
        async_client,
        manager_user,
        test_candidate
    ):
        """Менеджер не может запускать скрининг"""
        # Логинимся как менеджер
        login_response = await async_client.post("/api/v1/auth/login", json={
            "email": manager_user.email,
            "password": "Glafira2026!"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Пытаемся запустить скрининг с валидным телом
        response = await async_client.post(
            "/api/v1/glafira/screening/start",
            json={
                "candidate_id": str(test_candidate.id)
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"]

    async def test_admin_can_score_candidate(
        self,
        async_client,
        auth_headers,
        test_candidate,
        test_vacancy
    ):
        """Админ может оценивать кандидатов (не блокируется)"""
        # Пытаемся оценить кандидата (OPENROUTER_API_KEY пустой → не будет реального вызова)
        response = await async_client.post(
            "/api/v1/glafira/score",
            json={
                "candidate_id": str(test_candidate.id),
                "vacancy_id": str(test_vacancy.id)
            },
            headers=auth_headers
        )
        # Не должно быть 403 RBAC ошибки (может быть другие ошибки из-за пустого ключа)
        assert response.status_code != 403

    async def test_settings_update_422_on_invalid_literal(
        self,
        async_client,
        auth_headers
    ):
        """PATCH /settings/glafira с невалидными Literal значениями возвращает 422"""
        # Пытаемся обновить с невалидными значениями
        response = await async_client.patch(
            "/api/v1/settings/glafira",
            json={
                "tone": "invalid_tone",
                "default_mode": "Z"
            },
            headers=auth_headers
        )
        assert response.status_code == 422