"""Тесты настроек AI-модели per-company"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.models import User, Company, GlafiraSettings
from app.services.settings.glafira import get_company_llm_model
from app.services.glafira.models import ALLOWED_MODEL_VALUES, DEFAULT_MODEL


async def _login_headers(async_client: AsyncClient, user: User) -> dict[str, str]:
    """Реальный логин: patch('app.deps.get_current_user') НЕ работает с FastAPI DI
    (зависимость зарезолвлена при сборке роутера), даёт 401. Берём настоящий токен."""
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Glafira2026!"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestAiModelSettings:
    """Тесты API настроек AI-модели"""

    async def test_get_ai_model_settings_admin(self, async_client: AsyncClient, admin_user: User):
        """GET /settings/ai-model - админ может читать"""
        headers = await _login_headers(async_client, admin_user)
        response = await async_client.get("/api/v1/settings/ai-model", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "options" in data
        assert len(data["options"]) == 4  # 4 модели в белом списке
        assert data["current"] == DEFAULT_MODEL  # дефолт при отсутствии настройки

    async def test_get_ai_model_settings_recruiter(self, async_client: AsyncClient, regular_user: User):
        """GET /settings/ai-model - рекрутёр может читать"""
        headers = await _login_headers(async_client, regular_user)
        response = await async_client.get("/api/v1/settings/ai-model", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "options" in data

    async def test_get_ai_model_settings_manager_forbidden(self, async_client: AsyncClient, manager_user: User):
        """GET /settings/ai-model - менеджер не может читать настройки AI"""
        headers = await _login_headers(async_client, manager_user)
        response = await async_client.get("/api/v1/settings/ai-model", headers=headers)

        assert response.status_code == 403

    async def test_update_ai_model_settings_admin_success(self, async_client: AsyncClient, admin_user: User):
        """PATCH /settings/ai-model - админ может изменять модель"""
        headers = await _login_headers(async_client, admin_user)

        new_model = "deepseek/deepseek-v4-flash"
        response = await async_client.patch(
            "/api/v1/settings/ai-model", json={"model": new_model}, headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["current"] == new_model
        assert len(data["options"]) == 4

    async def test_update_ai_model_settings_recruiter_forbidden(self, async_client: AsyncClient, regular_user: User):
        """PATCH /settings/ai-model - рекрутёр не может изменять модель"""
        headers = await _login_headers(async_client, regular_user)

        response = await async_client.patch(
            "/api/v1/settings/ai-model", json={"model": "deepseek/deepseek-v4-flash"}, headers=headers
        )

        assert response.status_code == 403

    async def test_update_ai_model_settings_invalid_model(self, async_client: AsyncClient, admin_user: User):
        """PATCH /settings/ai-model - валидация белого списка"""
        headers = await _login_headers(async_client, admin_user)

        response = await async_client.patch(
            "/api/v1/settings/ai-model", json={"model": "evil/malicious-model"}, headers=headers
        )

        assert response.status_code == 400


class TestCompanyModelHelper:
    """Тесты хелпера get_company_llm_model"""

    async def test_get_company_model_no_setting(self, db_session: AsyncSession, test_company: Company):
        """Нет настройки → fallback на env"""
        with patch("app.config.settings.GLAFIRA_MODEL", "anthropic/claude-sonnet-4.6"):
            model = await get_company_llm_model(db_session, test_company.id)
            assert model == "anthropic/claude-sonnet-4.6"

    async def test_get_company_model_valid_setting(self, db_session: AsyncSession, test_company: Company):
        """Есть валидная настройка → её используем"""
        # Создаём настройку с llm_model
        settings_obj = GlafiraSettings(
            company_id=test_company.id,
            llm_model="qwen/qwen3.7-max"
        )
        db_session.add(settings_obj)
        await db_session.commit()

        model = await get_company_llm_model(db_session, test_company.id)
        assert model == "qwen/qwen3.7-max"

    async def test_get_company_model_invalid_setting(self, db_session: AsyncSession, test_company: Company):
        """Невалидная настройка (не в белом списке) → fallback на env"""
        settings_obj = GlafiraSettings(
            company_id=test_company.id,
            llm_model="evil/malicious-model"
        )
        db_session.add(settings_obj)
        await db_session.commit()

        with patch("app.config.settings.GLAFIRA_MODEL", "anthropic/claude-sonnet-4.6"):
            model = await get_company_llm_model(db_session, test_company.id)
            assert model == "anthropic/claude-sonnet-4.6"

    async def test_get_company_model_empty_env(self, db_session: AsyncSession, test_company: Company):
        """Нет настройки, env пуст → дефолт"""
        with patch("app.config.settings.GLAFIRA_MODEL", None):
            model = await get_company_llm_model(db_session, test_company.id)
            assert model == DEFAULT_MODEL


class TestCompanyIsolation:
    """Тесты изоляции настроек между компаниями"""

    async def test_model_setting_per_company_isolated(self, db_session: AsyncSession, admin_user: User):
        """Изменение модели в компании A не влияет на компанию B"""
        # Компания A (из фикстуры)
        company_a_id = admin_user.company_id

        # Создаём компанию B (модель Company имеет только name)
        company_b = Company(name="Компания Б")
        db_session.add(company_b)
        await db_session.flush()
        company_b_id = company_b.id

        # Задаём модель для компании A
        settings_a = GlafiraSettings(
            company_id=company_a_id,
            llm_model="qwen/qwen3.7-max"
        )
        db_session.add(settings_a)
        await db_session.commit()

        # Проверяем изоляцию
        model_a = await get_company_llm_model(db_session, company_a_id)
        model_b = await get_company_llm_model(db_session, company_b_id)

        assert model_a == "qwen/qwen3.7-max"
        # Компания B должна использовать fallback (env или дефолт)
        assert model_b != "qwen/qwen3.7-max"


class TestScoreCandidateWithCompanyModel:
    """Тесты интеграции с score_candidate"""

    async def test_score_candidate_uses_company_model(self, db_session: AsyncSession, admin_user: User):
        """score_candidate использует company-модель"""
        # Мокируем call_json чтобы проверить какая модель передаётся
        mock_call_json = AsyncMock(return_value={
            "score": 75,
            "verdict": "good",
            "summary": "Хороший кандидат",
            "strengths": ["Опыт"],
            "risks": ["Нет рисков"],
            "requirements_match": [],
            "forecast": "Успешно",
            "questions": []
        })

        with patch("app.services.glafira.scoring.call_json", mock_call_json):
            # Создаём кандидата и настройку модели
            from app.models import Candidate
            from app.services.glafira.scoring import score_candidate

            candidate = Candidate(
                company_id=admin_user.company_id,
                last_name="Кандидат",  # full_name — вычисляемое свойство (нет сеттера)
                first_name="Тест",
                source="manual",  # NOT NULL
                email="test@example.com",
                resume_text="Опытный разработчик"
            )
            db_session.add(candidate)

            settings_obj = GlafiraSettings(
                company_id=admin_user.company_id,
                llm_model="deepseek/deepseek-v4-flash"
            )
            db_session.add(settings_obj)
            await db_session.commit()

            # Оцениваем кандидата
            await score_candidate(
                db_session,
                candidate_id=candidate.id,
                vacancy_id=None,
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id,
                source="ТЕСТ"
            )

            # Проверяем что call_json был вызван с правильной моделью
            mock_call_json.assert_called_once()
            call_args = mock_call_json.call_args
            assert call_args.kwargs["model"] == "deepseek/deepseek-v4-flash"


@pytest.mark.asyncio
async def test_audit_log_on_model_change(async_client: AsyncClient, admin_user: User):
    """Изменение модели записывается в audit_log"""
    headers = await _login_headers(async_client, admin_user)

    payload = {"model": "qwen/qwen3.7-max"}

    # audit импортирован в namespace роутера → патчим там; AsyncMock (его await-ят)
    with patch("app.api.v1.settings.audit", new_callable=AsyncMock) as mock_audit:
        response = await async_client.patch(
            "/api/v1/settings/ai-model", json=payload, headers=headers
        )

    assert response.status_code == 200

    # Проверяем что audit был вызван
    mock_audit.assert_called_once()
    call_args = mock_audit.call_args
    assert call_args.kwargs["action"] == "update_ai_model"
    assert call_args.kwargs["actor_type"] == "human"
    assert call_args.kwargs["after"]["llm_model"] == "qwen/qwen3.7-max"