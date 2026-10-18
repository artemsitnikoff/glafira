"""Тесты настроек AI-модели per-company + динамический каталог OpenRouter.

Каталог моделей теперь ДИНАМИЧЕСКИЙ (live из OpenRouter). В тестах в сеть не
ходим: autouse-фикстура conftest `_mock_openrouter_catalog` подменяет
`fetch_openrouter_models` детерминированным каталогом (_FAKE_OPENROUTER_CATALOG).
Тесты реального fetch помечены @pytest.mark.real_openrouter_catalog и мокают httpx.
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.config import settings as app_settings
from app.models import User, Company, GlafiraSettings
from app.services.settings.glafira import get_company_llm_model
from app.services.glafira import models as glafira_models
from app.services.glafira.models import (
    DEFAULT_MODEL,
    RECOMMENDED_MODELS,
    cost_estimate,
    get_model_options,
    search_models,
    is_valid_model,
    fetch_openrouter_models,
    _prettify_slug,
    SCORING_EST_PROMPT_TOKENS,
    SCORING_EST_COMPLETION_TOKENS,
    USD_RUB_RATE,
)


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
        """GET /settings/ai-model — админ читает; опции идут с оценкой стоимости."""
        headers = await _login_headers(async_client, admin_user)
        response = await async_client.get("/api/v1/settings/ai-model", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "options" in data
        # Каталог-мок содержит все recommended → показываются все 8
        assert len(data["options"]) == len(RECOMMENDED_MODELS)
        # Нет company-настройки → резолвер даёт env GLAFIRA_MODEL или DEFAULT_MODEL
        assert data["current"] == (app_settings.GLAFIRA_MODEL or DEFAULT_MODEL)
        # Порядок сохранён как в RECOMMENDED_MODELS
        assert [o["value"] for o in data["options"]] == RECOMMENDED_MODELS
        # Каждая опция несёт поля оценки стоимости и контекст
        first = data["options"][0]
        assert first["cost_usd"] is not None
        assert first["cost_rub"] is not None  # оценка в рублях присутствует
        assert first["context_length"] is not None
        assert "label" in first and first["label"]

    async def test_get_ai_model_settings_recruiter(self, async_client: AsyncClient, regular_user: User):
        """GET /settings/ai-model — рекрутёр может читать"""
        headers = await _login_headers(async_client, regular_user)
        response = await async_client.get("/api/v1/settings/ai-model", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "options" in data

    async def test_get_ai_model_settings_manager_forbidden(self, async_client: AsyncClient, manager_user: User):
        """GET /settings/ai-model — менеджер не может читать настройки AI"""
        headers = await _login_headers(async_client, manager_user)
        response = await async_client.get("/api/v1/settings/ai-model", headers=headers)

        assert response.status_code == 403

    async def test_get_ai_model_options_live_unavailable(self, async_client: AsyncClient, admin_user: User):
        """GET /settings/ai-model — каталог OpenRouter недоступен → recommended без цен."""
        headers = await _login_headers(async_client, admin_user)
        with patch(
            "app.services.glafira.models.fetch_openrouter_models",
            new=AsyncMock(return_value={}),
        ):
            response = await async_client.get("/api/v1/settings/ai-model", headers=headers)

        assert response.status_code == 200
        data = response.json()
        # live пуст → все recommended, но без оценки стоимости (не падаем)
        assert len(data["options"]) == len(RECOMMENDED_MODELS)
        assert all(o["cost_usd"] is None and o["cost_rub"] is None for o in data["options"])

    async def test_update_ai_model_settings_admin_success(self, async_client: AsyncClient, admin_user: User):
        """PATCH /settings/ai-model — админ может изменять модель (из live-каталога)."""
        headers = await _login_headers(async_client, admin_user)

        new_model = "deepseek/deepseek-v4-flash"
        response = await async_client.patch(
            "/api/v1/settings/ai-model", json={"model": new_model}, headers=headers
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["current"] == new_model
        assert len(data["options"]) == len(RECOMMENDED_MODELS)

    async def test_update_ai_model_settings_recruiter_forbidden(self, async_client: AsyncClient, regular_user: User):
        """PATCH /settings/ai-model — рекрутёр не может изменять модель"""
        headers = await _login_headers(async_client, regular_user)

        response = await async_client.patch(
            "/api/v1/settings/ai-model", json={"model": "deepseek/deepseek-v4-flash"}, headers=headers
        )

        assert response.status_code == 403

    async def test_update_ai_model_settings_invalid_model(self, async_client: AsyncClient, admin_user: User):
        """PATCH /settings/ai-model — модель не из live-каталога → 400"""
        headers = await _login_headers(async_client, admin_user)

        response = await async_client.patch(
            "/api/v1/settings/ai-model", json={"model": "evil/malicious-model"}, headers=headers
        )

        assert response.status_code == 400

    async def test_update_ai_model_accepts_non_recommended_live_model(
        self, async_client: AsyncClient, admin_user: User, db_session: AsyncSession
    ):
        """PATCH принимает ЛЮБУЮ модель из live-каталога, даже не из recommended."""
        headers = await _login_headers(async_client, admin_user)

        catalog = {"openai/gpt-x": {"name": "GPT-X", "prompt": 1e-6, "completion": 2e-6, "context_length": 128000}}
        with patch(
            "app.services.glafira.models.fetch_openrouter_models",
            new=AsyncMock(return_value=catalog),
        ):
            response = await async_client.patch(
                "/api/v1/settings/ai-model", json={"model": "openai/gpt-x"}, headers=headers
            )

        assert response.status_code == 200, response.text
        assert response.json()["current"] == "openai/gpt-x"


class TestAiModelSearch:
    """Тесты эндпоинта поиска моделей GET /settings/ai-model/search"""

    async def test_search_models_substring(self, async_client: AsyncClient, admin_user: User):
        """Поиск по подстроке slug возвращает модели с ценой."""
        headers = await _login_headers(async_client, admin_user)
        response = await async_client.get("/api/v1/settings/ai-model/search?q=claude", headers=headers)

        assert response.status_code == 200
        options = response.json()["options"]
        assert len(options) >= 1
        assert all("claude" in o["value"].lower() for o in options)
        assert all("cost_rub" in o for o in options)

    async def test_search_models_empty_query(self, async_client: AsyncClient, admin_user: User):
        """Пустой запрос → пустой список (без прочёса всего каталога)."""
        headers = await _login_headers(async_client, admin_user)
        response = await async_client.get("/api/v1/settings/ai-model/search?q=", headers=headers)

        assert response.status_code == 200
        assert response.json()["options"] == []

    async def test_search_models_manager_forbidden(self, async_client: AsyncClient, manager_user: User):
        """Менеджер не может искать модели (как и читать настройки AI)."""
        headers = await _login_headers(async_client, manager_user)
        response = await async_client.get("/api/v1/settings/ai-model/search?q=claude", headers=headers)

        assert response.status_code == 403


class TestCompanyModelHelper:
    """Тесты хелпера get_company_llm_model (без статического whitelist)"""

    async def test_get_company_model_no_setting(self, db_session: AsyncSession, test_company: Company):
        """Нет настройки → fallback на env"""
        with patch("app.config.settings.GLAFIRA_MODEL", "anthropic/claude-sonnet-4.6"):
            model = await get_company_llm_model(db_session, test_company.id)
            assert model == "anthropic/claude-sonnet-4.6"

    async def test_get_company_model_valid_setting(self, db_session: AsyncSession, test_company: Company):
        """Есть настройка → её используем"""
        settings_obj = GlafiraSettings(
            company_id=test_company.id,
            llm_model="qwen/qwen3.7-max"
        )
        db_session.add(settings_obj)
        await db_session.commit()

        model = await get_company_llm_model(db_session, test_company.id)
        assert model == "qwen/qwen3.7-max"

    async def test_get_company_model_arbitrary_setting_trusted(self, db_session: AsyncSession, test_company: Company):
        """Сохранённая модель возвращается КАК ЕСТЬ, без whitelist-гейта.

        Регресс-охранник: раньше невалидная (не из белого списка) модель молча
        подменялась на env. Теперь доверяем сохранённому значению (оно валидируется
        против live-каталога в момент PATCH), резолвер env НЕ подставляет."""
        settings_obj = GlafiraSettings(
            company_id=test_company.id,
            llm_model="some/custom-model-9000"
        )
        db_session.add(settings_obj)
        await db_session.commit()

        with patch("app.config.settings.GLAFIRA_MODEL", "anthropic/claude-sonnet-4.6"):
            model = await get_company_llm_model(db_session, test_company.id)
            assert model == "some/custom-model-9000"  # НЕ env

    async def test_get_company_model_empty_env(self, db_session: AsyncSession, test_company: Company):
        """Нет настройки, env пуст → дефолт"""
        with patch("app.config.settings.GLAFIRA_MODEL", None):
            model = await get_company_llm_model(db_session, test_company.id)
            assert model == DEFAULT_MODEL

    async def test_get_company_model_empty_string_setting_falls_back(self, db_session: AsyncSession, test_company: Company):
        """Пустая строка в настройке трактуется как отсутствие → env/дефолт."""
        settings_obj = GlafiraSettings(company_id=test_company.id, llm_model="")
        db_session.add(settings_obj)
        await db_session.commit()

        with patch("app.config.settings.GLAFIRA_MODEL", "anthropic/claude-sonnet-4.6"):
            model = await get_company_llm_model(db_session, test_company.id)
            assert model == "anthropic/claude-sonnet-4.6"


class TestCompanyIsolation:
    """Тесты изоляции настроек между компаниями"""

    async def test_model_setting_per_company_isolated(self, db_session: AsyncSession, admin_user: User):
        """Изменение модели в компании A не влияет на компанию B"""
        company_a_id = admin_user.company_id

        company_b = Company(name="Компания Б")
        db_session.add(company_b)
        await db_session.flush()
        company_b_id = company_b.id

        settings_a = GlafiraSettings(
            company_id=company_a_id,
            llm_model="qwen/qwen3.7-max"
        )
        db_session.add(settings_a)
        await db_session.commit()

        model_a = await get_company_llm_model(db_session, company_a_id)
        model_b = await get_company_llm_model(db_session, company_b_id)

        assert model_a == "qwen/qwen3.7-max"
        # Компания B должна использовать fallback (env или дефолт)
        assert model_b != "qwen/qwen3.7-max"


class TestScoreCandidateWithCompanyModel:
    """Тесты интеграции с score_candidate"""

    async def test_score_candidate_uses_company_model(self, db_session: AsyncSession, admin_user: User):
        """score_candidate использует company-модель"""
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
            from app.models import Candidate
            from app.services.glafira.scoring import score_candidate

            candidate = Candidate(
                company_id=admin_user.company_id,
                last_name="Кандидат",
                first_name="Тест",
                source="manual",
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

            await score_candidate(
                db_session,
                candidate_id=candidate.id,
                vacancy_id=None,
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id,
                source="ТЕСТ"
            )

            mock_call_json.assert_called_once()
            call_args = mock_call_json.call_args
            assert call_args.kwargs["model"] == "deepseek/deepseek-v4-flash"


@pytest.mark.asyncio
async def test_audit_log_on_model_change(async_client: AsyncClient, admin_user: User):
    """Изменение модели записывается в audit_log"""
    headers = await _login_headers(async_client, admin_user)

    payload = {"model": "qwen/qwen3.7-max"}

    with patch("app.api.v1.settings.audit", new_callable=AsyncMock) as mock_audit:
        response = await async_client.patch(
            "/api/v1/settings/ai-model", json=payload, headers=headers
        )

    assert response.status_code == 200, response.text

    mock_audit.assert_called_once()
    call_args = mock_audit.call_args
    assert call_args.kwargs["action"] == "update_ai_model"
    assert call_args.kwargs["actor_type"] == "human"
    assert call_args.kwargs["after"]["llm_model"] == "qwen/qwen3.7-max"


class TestModelCatalogFunctions:
    """Юнит-тесты функций каталога (на моке fetch_openrouter_models из conftest)."""

    def test_cost_estimate_formula(self):
        """cost_estimate = EST_PROMPT*prompt + EST_COMPLETION*completion, + рубли."""
        prompt_per_token = 3e-6
        completion_per_token = 1.5e-5
        est = cost_estimate(prompt_per_token, completion_per_token)
        expected_usd = round(
            SCORING_EST_PROMPT_TOKENS * prompt_per_token
            + SCORING_EST_COMPLETION_TOKENS * completion_per_token,
            4,
        )
        assert est["usd"] == expected_usd
        assert est["rub"] == round(expected_usd * USD_RUB_RATE, 2)

    def test_prettify_slug(self):
        assert _prettify_slug("anthropic/claude-sonnet-5.5") == "Claude Sonnet 5.5"
        assert _prettify_slug("deepseek/deepseek-v4-flash") == "Deepseek V4 Flash"

    async def test_get_model_options_with_live(self):
        """С каталогом-моком — все recommended с ценой и в правильном порядке."""
        options = await get_model_options()
        assert [o["value"] for o in options] == RECOMMENDED_MODELS
        assert all(o["cost_usd"] is not None for o in options)
        assert all(o["cost_rub"] is not None for o in options)

    async def test_get_model_options_empty_live(self):
        """Каталог недоступен → все recommended без цены (не падаем)."""
        with patch(
            "app.services.glafira.models.fetch_openrouter_models",
            new=AsyncMock(return_value={}),
        ):
            options = await get_model_options()
        assert [o["value"] for o in options] == RECOMMENDED_MODELS
        assert all(o["cost_usd"] is None for o in options)

    async def test_get_model_options_skips_absent(self):
        """Recommended, которого НЕТ в live-каталоге, не показывается."""
        partial = {"deepseek/deepseek-v4-flash": {"name": "DeepSeek", "prompt": 1e-7, "completion": 2e-7, "context_length": 128000}}
        with patch(
            "app.services.glafira.models.fetch_openrouter_models",
            new=AsyncMock(return_value=partial),
        ):
            options = await get_model_options()
        assert [o["value"] for o in options] == ["deepseek/deepseek-v4-flash"]

    async def test_search_models_empty_query_returns_empty(self):
        assert await search_models("") == []
        assert await search_models("   ") == []

    async def test_search_models_substring(self):
        results = await search_models("gemini")
        assert len(results) == 1
        assert results[0]["value"] == "google/gemini-3.1-flash-lite"
        assert results[0]["cost_rub"] is not None

    async def test_search_models_skips_free_batch_and_caps(self):
        catalog = {
            "a/model-free:free": {"name": "F", "prompt": 0.0, "completion": 0.0, "context_length": 1},
            "a/model-batch:batch": {"name": "B", "prompt": 0.0, "completion": 0.0, "context_length": 1},
            "a/model-real": {"name": "R", "prompt": 1e-7, "completion": 1e-7, "context_length": 1},
        }
        with patch(
            "app.services.glafira.models.fetch_openrouter_models",
            new=AsyncMock(return_value=catalog),
        ):
            results = await search_models("model")
            assert [r["value"] for r in results] == ["a/model-real"]
            # кап limit соблюдается
            capped = await search_models("model", limit=0)
            assert capped == []

    async def test_is_valid_model_live(self):
        assert await is_valid_model("anthropic/claude-sonnet-5.5") is True
        assert await is_valid_model("evil/nope") is False
        assert await is_valid_model("") is False

    async def test_is_valid_model_fallback_when_catalog_empty(self):
        """Каталог недоступен → разрешаем только recommended (fallback)."""
        with patch(
            "app.services.glafira.models.fetch_openrouter_models",
            new=AsyncMock(return_value={}),
        ):
            # recommended проходит
            assert await is_valid_model("anthropic/claude-sonnet-5.5") is True
            # произвольная — нет
            assert await is_valid_model("openai/gpt-x") is False


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Мок httpx.AsyncClient как async-контекст-менеджера."""

    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._resp


@pytest.mark.real_openrouter_catalog
class TestFetchOpenrouterModels:
    """Реальный fetch_openrouter_models (мок httpx, без сети, сброс кэша)."""

    def _reset_cache(self):
        glafira_models._models_cache = None

    async def test_parses_pricing_and_caches(self, monkeypatch):
        self._reset_cache()
        payload = {
            "data": [
                {
                    "id": "anthropic/claude-sonnet-5.5",
                    "name": "Claude Sonnet 5.5",
                    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                    "context_length": 200000,
                },
                {"id": None, "name": "skip me", "pricing": {}},  # без id — отбрасывается
            ]
        }
        fake = _FakeClient(resp=_FakeResp(200, payload))
        monkeypatch.setattr(glafira_models.httpx, "AsyncClient", lambda **kw: fake)
        try:
            result = await fetch_openrouter_models()
            assert "anthropic/claude-sonnet-5.5" in result
            entry = result["anthropic/claude-sonnet-5.5"]
            assert isinstance(entry["prompt"], float) and entry["prompt"] == 0.000003
            assert isinstance(entry["completion"], float) and entry["completion"] == 0.000015
            assert entry["context_length"] == 200000
            assert None not in result and len(result) == 1
            # второй вызов берёт из кэша — повторного HTTP нет
            await fetch_openrouter_models()
            assert fake.calls == 1
        finally:
            self._reset_cache()

    async def test_non_200_graceful_empty(self, monkeypatch):
        self._reset_cache()
        fake = _FakeClient(resp=_FakeResp(500, {}))
        monkeypatch.setattr(glafira_models.httpx, "AsyncClient", lambda **kw: fake)
        try:
            result = await fetch_openrouter_models()
            assert result == {}
        finally:
            self._reset_cache()

    async def test_exception_graceful_empty(self, monkeypatch):
        self._reset_cache()
        fake = _FakeClient(exc=RuntimeError("network down"))
        monkeypatch.setattr(glafira_models.httpx, "AsyncClient", lambda **kw: fake)
        try:
            result = await fetch_openrouter_models()
            assert result == {}
        finally:
            self._reset_cache()
