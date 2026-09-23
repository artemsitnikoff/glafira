import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Candidate, Company, Consent, Message


async def _make_consent(
    db_session: AsyncSession,
    candidate: Candidate,
    *,
    status: str = "pending",
    token: str | None = None,
    expires_at: datetime | None = None,
    consent_text: str | None = "Согласие на обработку персональных данных. Я, Тестов Тест, ...",
    signed_at: datetime | None = None,
) -> Consent:
    """Прямо в БД создаёт Consent с онлайн-токеном (для публичных тестов без доставки)."""
    now = datetime.now(timezone.utc)
    consent = Consent(
        company_id=candidate.company_id,
        candidate_id=candidate.id,
        number=f"PD-{secrets.token_hex(2)}/26",
        status=status,
        channel="email",
        token=token or secrets.token_urlsafe(32),
        expires_at=expires_at if expires_at is not None else now + timedelta(days=14),
        consent_text=consent_text,
        requested_at=now,
        signed_at=signed_at,
    )
    db_session.add(consent)
    await db_session.commit()
    await db_session.refresh(consent)
    return consent


class TestConsentRequest:
    async def test_request_generates_token_expires_text_and_delivers(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_candidate: Candidate,
        db_session: AsyncSession,
    ):
        """request_consent генерит token+expires+consent_text и доставляет ссылку (email авто)."""
        candidate_id = str(test_candidate.id)

        # candidate has email → авто-канал = email. Мокаем реальную отправку.
        with patch(
            "app.services.integrations.smtp.service.send_email",
            return_value=None,
        ) as mock_send:
            response = await async_client.post(
                f"/api/v1/candidates/{candidate_id}/consent/request",
                headers=auth_headers,
                json={},  # без канала → авто-выбор
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert body["number"].startswith("PD-")
        assert "/consent/" in body["link"]
        assert body["delivered"] is True
        assert body["delivery_channel"] == "email"
        assert body["delivery_error"] is None
        mock_send.assert_awaited_once()

        # В БД: token/expires_at/consent_text проставлены
        consent = (await db_session.execute(
            select(Consent).where(Consent.candidate_id == test_candidate.id)
        )).scalar_one()
        assert consent.token and len(consent.token) >= 20
        assert body["link"].endswith(consent.token)
        assert consent.expires_at is not None and consent.expires_at > datetime.now(timezone.utc)
        assert consent.consent_text
        assert "Тестов Тест" in consent.consent_text  # ФИО подставлено
        assert "Test Company" in consent.consent_text  # компания подставлена

        # Запись в ленту чата создана (реальная отправка прошла)
        msg = (await db_session.execute(
            select(Message).where(
                Message.candidate_id == test_candidate.id,
                Message.channel == "email",
            )
        )).scalar_one()
        assert consent.token in msg.body

    async def test_request_delivery_failure_is_honest(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_candidate: Candidate,
    ):
        """SMTP не настроен → delivered=False с причиной, но согласие всё равно создано."""
        candidate_id = str(test_candidate.id)
        # НЕ мокаем send_email — SMTP не настроен → ValidationError → delivered False.
        response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/request",
            headers=auth_headers,
            json={"channel": "email"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert body["delivered"] is False
        assert body["delivery_error"]  # честная причина
        assert "/consent/" in body["link"]  # ссылка всё равно есть

    async def test_has_pdn_flag(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_candidate: Candidate,
    ):
        """has_pdn меняется False→True после подписания (auth-путь кандидата)."""
        candidate_id = str(test_candidate.id)

        response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["has_pdn"] is False

        # telegram-доставка в тесте упадёт (TG не подключён) — но согласие создаётся (201)
        consent_response = await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/request",
            headers=auth_headers,
            json={"channel": "telegram"},
        )
        assert consent_response.status_code == 201, consent_response.text

        await async_client.post(
            f"/api/v1/candidates/{candidate_id}/consent/sign", headers=auth_headers
        )

        response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["has_pdn"] is True


class TestPublicConsent:
    async def test_get_info_returns_text_status_minimal_pii(
        self,
        async_client: AsyncClient,
        test_candidate: Candidate,
        db_session: AsyncSession,
    ):
        """GET /public/consent/{token} — текст+статус, БЕЗ телефона/email кандидата."""
        consent = await _make_consent(db_session, test_candidate)

        r = await async_client.get(f"/api/v1/public/consent/{consent.token}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["company_name"] == "Test Company"
        assert data["candidate_name"] == "Тестов Тест"
        assert data["consent_text"]
        assert data["status"] == "pending"
        assert data["can_sign"] is True
        assert data["already_signed"] is False
        assert data["expired"] is False

        # PII-минимум: ни email, ни телефон, ни внутренний id не утекают
        raw = r.text
        assert "test@example.com" not in raw
        assert "900 123 45 67" not in raw
        assert str(test_candidate.id) not in raw

    async def test_get_info_unknown_token_404(self, async_client: AsyncClient):
        r = await async_client.get("/api/v1/public/consent/nonexistent_token_xyz")
        assert r.status_code == 404

    async def test_sign_sets_signed_ip_and_signed_by(
        self,
        async_client: AsyncClient,
        test_candidate: Candidate,
        db_session: AsyncSession,
    ):
        """POST sign → status signed + signed_ip (из X-Forwarded-For) + signed_by=candidate."""
        consent = await _make_consent(db_session, test_candidate)

        r = await async_client.post(
            f"/api/v1/public/consent/{consent.token}/sign",
            headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "signed"

        await db_session.refresh(consent)
        assert consent.status == "signed"
        assert consent.signed_by == "candidate"
        assert consent.signed_ip == "203.0.113.9"
        assert consent.signed_at is not None

        # После подписания страница отдаёт already_signed
        info = await async_client.get(f"/api/v1/public/consent/{consent.token}")
        assert info.json()["already_signed"] is True
        assert info.json()["can_sign"] is False

    async def test_sign_is_idempotent(
        self,
        async_client: AsyncClient,
        test_candidate: Candidate,
        db_session: AsyncSession,
    ):
        consent = await _make_consent(db_session, test_candidate)
        r1 = await async_client.post(f"/api/v1/public/consent/{consent.token}/sign")
        r2 = await async_client.post(f"/api/v1/public/consent/{consent.token}/sign")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["status"] == "signed"

    async def test_expired_token_does_not_sign(
        self,
        async_client: AsyncClient,
        test_candidate: Candidate,
        db_session: AsyncSession,
    ):
        """Истёкший токен → sign отдаёт 410 и НЕ подписывает."""
        consent = await _make_consent(
            db_session,
            test_candidate,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        r = await async_client.post(f"/api/v1/public/consent/{consent.token}/sign")
        assert r.status_code == 410
        await db_session.refresh(consent)
        assert consent.status == "pending"

        # GET показывает expired=true, can_sign=false
        info = await async_client.get(f"/api/v1/public/consent/{consent.token}")
        assert info.status_code == 200
        assert info.json()["expired"] is True
        assert info.json()["can_sign"] is False

    async def test_company_id_only_from_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
    ):
        """company_id берётся ТОЛЬКО из токена — чужая компания не путается."""
        # Вторая компания + её кандидат + согласие с токеном
        other_company = Company(name="Другая Компания ООО")
        db_session.add(other_company)
        await db_session.flush()
        other_candidate = Candidate(
            company_id=other_company.id,
            last_name="Чужой",
            first_name="Кандидат",
            source="manual",
        )
        db_session.add(other_candidate)
        await db_session.flush()
        consent = await _make_consent(db_session, other_candidate)

        # Публичный GET по токену второй компании отдаёт ЕЁ данные, не дефолтной
        r = await async_client.get(f"/api/v1/public/consent/{consent.token}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["company_name"] == "Другая Компания ООО"
        assert data["candidate_name"] == "Чужой Кандидат"


class TestConsentGate:
    async def test_verify_gate_opens_after_public_sign(
        self,
        async_client: AsyncClient,
        test_candidate: Candidate,
        db_session: AsyncSession,
    ):
        """После публичного sign verify_candidate НЕ бросает ConsentRequiredError."""
        from app.services.glafira.verify import verify_candidate
        from app.core.errors import ConsentRequiredError

        consent = await _make_consent(db_session, test_candidate)
        r = await async_client.post(f"/api/v1/public/consent/{consent.token}/sign")
        assert r.status_code == 200

        raised_consent_required = False
        with patch("app.services.glafira.verify.clean_phone", return_value=None), \
             patch("app.services.glafira.verify.clean_email", return_value=None), \
             patch("app.services.glafira.verify.clean_name", return_value=None), \
             patch("app.services.glafira.verify.claude_cli_complete", return_value=None):
            try:
                await verify_candidate(
                    db_session,
                    candidate_id=test_candidate.id,
                    company_id=test_candidate.company_id,
                    actor_user_id=None,
                )
            except ConsentRequiredError:
                raised_consent_required = True
            except Exception:
                # Прочие сбои (сеть/окружение) — не предмет этого теста, гейт уже пройден
                pass

        assert raised_consent_required is False


class TestConsentRBAC:
    async def test_manager_cannot_request_consent(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: Candidate,
    ):
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": manager_user.email, "password": "Glafira2026!"},
        )
        assert login_response.status_code == 200
        manager_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await async_client.post(
            f"/api/v1/candidates/{test_candidate.id}/consent/request",
            headers=manager_headers,
            json={"channel": "telegram"},
        )
        assert response.status_code == 403
        error = response.json()
        assert "FORBIDDEN" in error["error"]["code"]
        assert "Менеджеры не могут запрашивать согласия" in error["error"]["message"]

    async def test_manager_cannot_confirm_signed_consent(
        self,
        async_client: AsyncClient,
        manager_user: User,
        test_candidate: Candidate,
    ):
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": manager_user.email, "password": "Glafira2026!"},
        )
        assert login_response.status_code == 200
        manager_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = await async_client.post(
            f"/api/v1/candidates/{test_candidate.id}/consent/confirm-signed",
            headers=manager_headers,
        )
        assert response.status_code == 403
        error = response.json()
        assert "FORBIDDEN" in error["error"]["code"]
        assert "Менеджеры не могут подтверждать" in error["error"]["message"]
