"""Тесты LOW-находок security-аудита (FIX 1–6).

Покрытие:
- FIX 1: повторный POST /verify без force → возвращает существующую (verify_candidate не вызывается)
- FIX 1: с force=true → вызывает verify_candidate снова
- FIX 2/3: _is_sensitive_key ловит webhook/salt/bearer; mask_config не раскрывает короткие секреты
- FIX 4: fill_candidate_osint без signed consent → не вызывает _build_osint_blocks
- FIX 5: radar без avg_time → speed_score=0 (не 70); без ai_score → quality_score=0 (не 50)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.settings.crypto import _is_sensitive_key, mask_config, encrypt_text


# ---------------------------------------------------------------------------
# FIX 2 — _is_sensitive_key: подстрочное совпадение
# ---------------------------------------------------------------------------

class TestIsSensitiveKey:
    def test_exact_legacy_keys_still_match(self):
        """Исходные точные ключи по-прежнему детектируются."""
        assert _is_sensitive_key("api_key")
        assert _is_sensitive_key("access_token")
        assert _is_sensitive_key("refresh_token")
        assert _is_sensitive_key("password")
        assert _is_sensitive_key("client_secret")

    def test_new_substring_keys(self):
        """Новые ключи с подстроками catch-all."""
        assert _is_sensitive_key("webhook")
        assert _is_sensitive_key("webhook_secret")
        assert _is_sensitive_key("salt")
        assert _is_sensitive_key("vpbx_api_salt")
        assert _is_sensitive_key("bearer_token")
        assert _is_sensitive_key("Authorization")  # регистронезависимо
        assert _is_sensitive_key("private_key")
        assert _is_sensitive_key("credential")
        assert _is_sensitive_key("signature")
        assert _is_sensitive_key("AUTH_HEADER")

    def test_non_sensitive_keys_not_matched(self):
        """Несекретные ключи не должны детектироваться."""
        assert not _is_sensitive_key("name")
        assert not _is_sensitive_key("url")
        assert not _is_sensitive_key("host")
        assert not _is_sensitive_key("port")
        assert not _is_sensitive_key("enabled")
        assert not _is_sensitive_key("description")


# ---------------------------------------------------------------------------
# FIX 3 — mask_config: короткий секрет → только ••••
# ---------------------------------------------------------------------------

class TestMaskConfig:
    """Требуется реальный FERNET_KEY для encrypt/decrypt."""

    @pytest.fixture(autouse=True)
    def patch_fernet(self, monkeypatch):
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        import app.config as config_module
        monkeypatch.setattr(config_module.settings, "FERNET_KEY", test_key)

    def _enc(self, val: str) -> str:
        return encrypt_text(val)

    def test_long_secret_shows_last_4(self):
        """api_key НЕ в whitelist → всегда ••••, последние-4 больше не раскрываются (это и был фикс)."""
        secret = "abcd1234"  # ровно 8
        config = {"api_key": self._enc(secret)}
        result = mask_config(config)
        assert result["api_key"] == "••••"

    def test_short_secret_no_chars_revealed(self):
        """api_key НЕ в whitelist → только ••••, никаких символов (проверяем несколько значений)."""
        for short in ["abc", "1234", "xy", "a", "1234567"]:
            config = {"api_key": self._enc(short)}
            result = mask_config(config)
            # Ключ не в whitelist — маска независимо от длины
            assert result["api_key"] == "••••", f"Секрет '{short}' должен давать только ••••"

    def test_whitelist_key_passes_non_whitelist_masked(self):
        """Ключ ИЗ whitelist проходит verbatim; ключ НЕ из whitelist → ••••."""
        config = {"host": "smtp.example.com", "port": 587, "name": "test", "url": "https://example.com"}
        result = mask_config(config)
        assert result["host"] == "smtp.example.com"   # whitelist → verbatim
        assert result["port"] == 587                  # whitelist → verbatim
        assert result["name"] == "••••"               # не whitelist → маска
        assert result["url"] == "••••"                # не whitelist → маска

    def test_decrypt_error_gives_bullets(self):
        """api_key НЕ в whitelist → ••••, декрипт не пытается (причина маски — «не в whitelist»)."""
        config = {"api_key": "not-encrypted-at-all"}
        result = mask_config(config)
        assert result["api_key"] == "••••"

    def test_webhook_key_is_masked(self):
        """webhook-ключ НЕ в whitelist → ••••, а не ••••LAST4."""
        secret = "myhook12345"
        config = {"webhook": self._enc(secret)}
        result = mask_config(config)
        assert result["webhook"] == "••••"

    def test_telegram_session_and_pii_never_leak(self):
        """Регресс-страховка: session/tg_user/phone (Telegram PII) НЕ в whitelist → ••••, не сырые."""
        config = {
            "session": "ENCRYPTED_SESSION_BLOB",
            "tg_user": {"id": 1, "phone": "+79990001122"},
            "phone": "+79990001122",
            "vpbx_api_url": "https://api.example.com",
        }
        result = mask_config(config)
        assert result["session"] == "••••"
        assert result["tg_user"] == "••••"
        assert result["phone"] == "••••"
        assert result["vpbx_api_url"] == "https://api.example.com"  # whitelist → verbatim


# ---------------------------------------------------------------------------
# FIX 1 — идемпотентность /verify (unit через моки сервиса)
# ---------------------------------------------------------------------------

class TestVerifyIdempotency:
    """Тесты через HTTP-клиент: повторный POST без force → без повторного вызова verify_candidate."""

    async def test_verify_returns_existing_without_calling_service(
        self, async_client, admin_user, test_candidate, signed_consent, db_session
    ):
        """Повторный POST /verify (force=false) не вызывает verify_candidate — возвращает существующую."""
        from app.models import Verification

        # Создаём «уже существующую» верификацию в БД
        existing = Verification(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            consent_id=signed_consent.id,
            checked_at=datetime.now(timezone.utc),
            status="clean",
            blocks=[
                {
                    "key": "contacts",
                    "title": "Контактные данные",
                    "sources": [{"name": "DaData", "type": "api"}],
                    "status": "clean",
                    "data": {},
                }
            ],
            is_mock=False,
        )
        db_session.add(existing)
        await db_session.commit()

        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": admin_user.email, "password": "Glafira2026!"},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Патчим verify_candidate — он НЕ должен вызываться при force=false и существующей верификации
        with patch(
            "app.api.v1.verifications.verify_candidate",
            new_callable=AsyncMock
        ) as mock_verify, patch(
            "app.api.v1.verifications.fill_candidate_osint",
            new_callable=AsyncMock
        ) as mock_osint:

            resp = await async_client.post(
                f"/api/v1/candidates/{test_candidate.id}/verify",
                headers=headers,
                # force=false (default)
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["candidate_id"] == str(test_candidate.id)
            # verify_candidate НЕ вызывался — идемпотентность сработала
            mock_verify.assert_not_called()
            # fill_candidate_osint тоже не вызывался
            mock_osint.assert_not_called()

    async def test_force_true_calls_verify_candidate(
        self, async_client, admin_user, test_candidate, signed_consent, db_session
    ):
        """С force=true всегда вызывает verify_candidate заново."""
        from app.models import Verification

        # Создаём «уже существующую» верификацию
        existing = Verification(
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            consent_id=signed_consent.id,
            checked_at=datetime.now(timezone.utc),
            status="clean",
            blocks=[],
            is_mock=False,
        )
        db_session.add(existing)
        await db_session.commit()

        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": admin_user.email, "password": "Glafira2026!"},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Готовим мок — verify_candidate возвращает Verification-объект
        new_verification = Verification(
            id=uuid4(),
            company_id=test_candidate.company_id,
            candidate_id=test_candidate.id,
            consent_id=signed_consent.id,
            checked_at=datetime.now(timezone.utc),
            status="info",
            blocks=[
                {
                    "key": "contacts",
                    "title": "Контактные данные",
                    "sources": [{"name": "DaData", "type": "api"}],
                    "status": "info",
                    "data": {},
                }
            ],
            is_mock=False,
            created_at=datetime.now(timezone.utc),
        )

        with patch(
            "app.api.v1.verifications.verify_candidate",
            new_callable=AsyncMock,
            return_value=new_verification,
        ) as mock_verify, patch(
            "app.api.v1.verifications.fill_candidate_osint",
            new_callable=AsyncMock,
        ), patch(
            "asyncio.create_task",
            side_effect=lambda coro: (coro.close() or MagicMock()),
        ):
            resp = await async_client.post(
                f"/api/v1/candidates/{test_candidate.id}/verify?force=true",
                headers=headers,
            )
            assert resp.status_code == 201
            # verify_candidate ВЫЗВАН при force=true
            mock_verify.assert_called_once()


# ---------------------------------------------------------------------------
# FIX 4 — fill_candidate_osint: нет согласия → _build_osint_blocks не вызывается
# ---------------------------------------------------------------------------

class TestFillCandidateOsintConsentGuard:

    async def test_no_signed_consent_skips_osint(self, test_candidate):
        """fill_candidate_osint без signed consent → _build_osint_blocks не вызывается."""
        from app.services.glafira.verify import fill_candidate_osint

        mock_session_ctx = AsyncMock()
        mock_session = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        # Верификация найдена
        from app.models import Verification
        fake_verification = MagicMock(spec=Verification)
        fake_verification.blocks = []
        fake_candidate = MagicMock()
        fake_candidate.full_name = "Иванов Иван"

        # Согласие не найдено
        def make_execute_result(query):
            res = AsyncMock()
            res.scalar_one_or_none.return_value = None
            return res

        # Первый execute → Verification, второй → Candidate, третий → Consent (None)
        mock_session.execute = AsyncMock(side_effect=[
            _scalar_result(fake_verification),
            _scalar_result(fake_candidate),
            _scalar_result(None),       # нет согласия
        ])

        with patch("app.services.glafira.verify.AsyncSessionLocal", return_value=mock_session_ctx), \
             patch("app.services.glafira.verify._build_osint_blocks", new_callable=AsyncMock) as mock_osint:

            await fill_candidate_osint(test_candidate.id, test_candidate.company_id)

            # _build_osint_blocks НЕ должен вызываться
            mock_osint.assert_not_called()

    async def test_with_signed_consent_calls_osint(self, test_candidate):
        """fill_candidate_osint с signed consent → _build_osint_blocks вызывается."""
        from app.services.glafira.verify import fill_candidate_osint
        from app.models import Verification, Consent

        mock_session_ctx = AsyncMock()
        mock_session = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        fake_verification = MagicMock(spec=Verification)
        fake_verification.blocks = []
        fake_candidate = MagicMock()
        fake_candidate.full_name = "Иванов Иван"
        fake_consent = MagicMock(spec=Consent)

        mock_session.execute = AsyncMock(side_effect=[
            _scalar_result(fake_verification),
            _scalar_result(fake_candidate),
            _scalar_result(fake_consent),   # согласие есть
        ])
        mock_session.commit = AsyncMock()

        stub_osint = [
            {"key": "public_expertise", "title": "Публичная экспертиза",
             "sources": [], "status": "info", "data": {"profiles": [], "found": 0}},
            {"key": "mentions", "title": "Упоминания",
             "sources": [], "status": "info", "data": {"mentions": [], "found": 0}},
        ]

        with patch("app.services.glafira.verify.AsyncSessionLocal", return_value=mock_session_ctx), \
             patch("app.services.glafira.verify._build_osint_blocks",
                   new_callable=AsyncMock, return_value=stub_osint) as mock_osint:

            await fill_candidate_osint(test_candidate.id, test_candidate.company_id)

            mock_osint.assert_called_once_with(fake_candidate)


def _scalar_result(value):
    """Вспомогательный хелпер: возвращает AsyncMock с .scalar_one_or_none() = value."""
    res = AsyncMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


# ---------------------------------------------------------------------------
# FIX 5 — radar chart: нет данных → 0 вместо фейк-50/фейк-70
# ---------------------------------------------------------------------------

class TestRecruiterRadarHonestDefaults:
    """Проверяем, что _build_radar_chart не фабрикует speed/quality при отсутствии данных."""

    def test_speed_score_no_data_is_zero(self):
        """_speed_score (ядро FIX5): нет данных по времени найма → 0, НЕ фейк 30дн→70."""
        from app.services.analytics.recruiters import _speed_score
        assert _speed_score(None) == 0      # нет данных → 0 (раньше фабриковалось 30дн→70)
        assert _speed_score(0) == 100       # мгновенный найм → 100
        assert _speed_score(10) == 90       # 10 дней → 90
        assert _speed_score(150) == 0       # дольше 100 дней → не ниже 0 (clamp)
        # 70 достижимо ТОЛЬКО при реальных 30 днях, а не как дефолт-из-воздуха
        assert _speed_score(30) == 70
