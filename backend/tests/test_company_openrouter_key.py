"""Тесты перевода LLM-вызовов на ключ компании.

Помечены real_openrouter_key → autouse-дефолт резолвера из conftest НЕ применяется,
проверяем настоящее поведение get_company_openrouter_key.
"""

import pytest
from unittest.mock import patch, AsyncMock
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import OpenRouterNotConfiguredError
from app.services.settings.glafira import get_company_openrouter_key, get_glafira_settings
from app.services.settings.crypto import encrypt_text
from app.services.glafira.scoring import score_candidate

pytestmark = pytest.mark.real_openrouter_key

# Стабильный валидный Fernet-ключ на модуль (encrypt и decrypt в одном тесте — один ключ)
_TEST_FERNET_KEY = Fernet.generate_key().decode()


def _set_fernet(monkeypatch):
    monkeypatch.setattr("app.config.settings.FERNET_KEY", _TEST_FERNET_KEY)


@pytest.mark.asyncio
async def test_get_company_openrouter_key_success(db_session: AsyncSession, test_company, monkeypatch):
    """Резолвер возвращает расшифрованный ключ компании."""
    _set_fernet(monkeypatch)

    test_key = "test-api-key-12345"
    gs = await get_glafira_settings(db_session, test_company.id)
    gs.openrouter_api_key = encrypt_text(test_key)
    await db_session.commit()

    resolved_key = await get_company_openrouter_key(db_session, test_company.id)
    assert resolved_key == test_key


@pytest.mark.asyncio
async def test_get_company_openrouter_key_not_configured(db_session: AsyncSession, test_company):
    """Нет ключа у компании → OpenRouterNotConfiguredError (не fallback, не 500)."""
    gs = await get_glafira_settings(db_session, test_company.id)
    gs.openrouter_api_key = None
    await db_session.commit()

    with pytest.raises(OpenRouterNotConfiguredError):
        await get_company_openrouter_key(db_session, test_company.id)


@pytest.mark.asyncio
async def test_company_key_isolation(db_session: AsyncSession, test_company, second_company, monkeypatch):
    """Каждая компания получает ТОЛЬКО свой ключ (изоляция арендаторов)."""
    _set_fernet(monkeypatch)

    key_company_1 = "key-company-1"
    key_company_2 = "key-company-2"

    gs1 = await get_glafira_settings(db_session, test_company.id)
    gs1.openrouter_api_key = encrypt_text(key_company_1)
    gs2 = await get_glafira_settings(db_session, second_company.id)
    gs2.openrouter_api_key = encrypt_text(key_company_2)
    await db_session.commit()

    resolved_1 = await get_company_openrouter_key(db_session, test_company.id)
    resolved_2 = await get_company_openrouter_key(db_session, second_company.id)

    assert resolved_1 == key_company_1
    assert resolved_2 == key_company_2
    assert resolved_1 != resolved_2


@pytest.mark.asyncio
async def test_scoring_uses_company_key(db_session: AsyncSession, test_candidate, test_company, monkeypatch):
    """score_candidate передаёт в call_json ключ КОМПАНИИ (не глобальный env)."""
    _set_fernet(monkeypatch)

    company_key = "company-specific-key"
    gs = await get_glafira_settings(db_session, test_company.id)
    gs.openrouter_api_key = encrypt_text(company_key)
    await db_session.commit()

    mock_response = {
        "score": 75,
        "verdict": "good",
        "summary": "test summary",
        "strengths": ["skill1"],
        "risks": ["risk1"],
        "requirements_match": [],
        "forecast": "positive",
    }

    with patch("app.services.glafira.scoring.call_json", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        await score_candidate(
            db_session,
            candidate_id=test_candidate.id,
            vacancy_id=None,
            company_id=test_company.id,
            actor_user_id=None,
        )
        mock_call.assert_called_once()
        assert mock_call.call_args.kwargs["api_key"] == company_key


@pytest.mark.asyncio
async def test_scoring_fails_without_company_key(db_session: AsyncSession, test_candidate, test_company):
    """score_candidate без ключа компании → OpenRouterNotConfiguredError (не 500, не глобальный)."""
    gs = await get_glafira_settings(db_session, test_company.id)
    gs.openrouter_api_key = None
    await db_session.commit()

    with pytest.raises(OpenRouterNotConfiguredError):
        await score_candidate(
            db_session,
            candidate_id=test_candidate.id,
            vacancy_id=None,
            company_id=test_company.id,
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_ai_model_api_has_openrouter_key_flag(async_client, auth_headers, test_company, db_session, monkeypatch):
    """GET /settings/ai-model отдаёт флаг has_openrouter_key (без самого ключа)."""
    _set_fernet(monkeypatch)

    response = await async_client.get("/api/v1/settings/ai-model", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["has_openrouter_key"] is False

    gs = await get_glafira_settings(db_session, test_company.id)
    gs.openrouter_api_key = encrypt_text("test-key")
    await db_session.commit()

    response = await async_client.get("/api/v1/settings/ai-model", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["has_openrouter_key"] is True


@pytest.mark.asyncio
async def test_set_openrouter_key_via_api(async_client, auth_headers, test_company, db_session, monkeypatch):
    """PATCH /settings/ai-model сохраняет ключ зашифрованным; резолвер его расшифровывает."""
    _set_fernet(monkeypatch)

    new_key = "new-openrouter-key-123"
    response = await async_client.patch(
        "/api/v1/settings/ai-model",
        json={"model": "anthropic/claude-sonnet-4.6", "openrouter_api_key": new_key},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_openrouter_key"] is True

    resolved_key = await get_company_openrouter_key(db_session, test_company.id)
    assert resolved_key == new_key


@pytest.mark.asyncio
async def test_key_not_logged_in_audit(async_client, auth_headers, test_company, db_session, monkeypatch):
    """Сам ключ НЕ попадает в audit_log (только флаг openrouter_key_set)."""
    from app.models import AuditLog
    from sqlalchemy import select

    _set_fernet(monkeypatch)

    secret_key = "very-secret-key-456"
    await async_client.patch(
        "/api/v1/settings/ai-model",
        json={"model": "anthropic/claude-sonnet-4.6", "openrouter_api_key": secret_key},
        headers=auth_headers,
    )

    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.company_id == test_company.id)
        .where(AuditLog.action == "update_ai_model")
        .order_by(AuditLog.created_at.desc())
    )
    audit_entries = result.scalars().all()
    assert len(audit_entries) > 0
    latest_audit = audit_entries[0]

    assert secret_key not in str(latest_audit.changes)
    assert "openrouter_key_set" in str(latest_audit.changes.get("after", {}))
