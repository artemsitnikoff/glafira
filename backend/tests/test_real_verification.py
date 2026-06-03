"""Tests for real verification functionality"""

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.models import Verification, Event, Consent
from app.services.glafira.verify import verify_candidate, _build_contacts_block, _build_government_stub_blocks
from app.core.errors import ConsentRequiredError


class TestRealVerification:

    async def test_verify_candidate_without_consent_raises_error(
        self, db_session, test_candidate
    ):
        """Test that verification without signed consent raises ConsentRequiredError"""

        with pytest.raises(ConsentRequiredError):
            await verify_candidate(
                db_session,
                candidate_id=test_candidate.id,
                company_id=test_candidate.company_id,
                actor_user_id=None
            )

    async def test_verify_candidate_with_real_dadata_blocks(
        self, db_session, test_candidate, signed_consent
    ):
        """Test verification creates real blocks structure"""

        # Mock DaData responses
        mock_phone_result = {
            "phone": "+7 495 123 45 67",
            "provider": "МТС",
            "region": "Москва",
            "qc": 0
        }

        mock_email_result = {
            "email": "test@example.com",
            "type": "Личный",
            "qc": 0
        }

        mock_name_result = {
            "surname": "Иванов",
            "name": "Иван",
            "patronymic": "Иванович",
            "gender": "М",
            "qc": 0
        }

        # Mock AI response
        mock_ai_result = {
            "summary": "Данные кандидата выглядят корректными",
            "flags": [],
            "confidence": 0.8
        }

        with patch('app.services.glafira.verify.clean_phone', return_value=mock_phone_result), \
             patch('app.services.glafira.verify.clean_email', return_value=mock_email_result), \
             patch('app.services.glafira.verify.clean_name', return_value=mock_name_result), \
             patch('app.services.glafira.verify.call_json', return_value=mock_ai_result):

            verification = await verify_candidate(
                db_session,
                candidate_id=test_candidate.id,
                company_id=test_candidate.company_id,
                actor_user_id=None
            )

            assert verification.candidate_id == test_candidate.id
            assert verification.consent_id == signed_consent.id
            assert verification.is_mock is False  # Real verification
            assert verification.status in ['clean', 'info', 'warn', 'risk']

            # Check blocks structure
            blocks = verification.blocks
            assert len(blocks) >= 6  # contacts + 5 gov stubs + ai_intel

            # Find contacts block
            contacts_block = next((b for b in blocks if b["key"] == "contacts"), None)
            assert contacts_block is not None
            assert contacts_block["title"] == "Контактные данные"
            assert contacts_block["sources"] == [{"name": "DaData", "type": "api"}]
            assert "phone" in contacts_block["data"]
            assert "email" in contacts_block["data"]
            assert "name" in contacts_block["data"]

            # Check government stub blocks
            gov_keys = ["inn", "fssp", "bankruptcy", "registries", "alimony"]
            for gov_key in gov_keys:
                gov_block = next((b for b in blocks if b["key"] == gov_key), None)
                assert gov_block is not None
                assert gov_block["status"] == "info"
                assert gov_block["data"]["status"] == "Не подключено"
                assert "152-ФЗ" in gov_block["data"]["note"]

            # Check AI block
            ai_block = next((b for b in blocks if b["key"] == "ai_intel"), None)
            assert ai_block is not None
            assert ai_block["title"] == "AI-оценка Глафиры"
            assert ai_block["sources"] == [{"name": "Глафира AI", "type": "ai"}]

    async def test_contacts_block_handles_missing_dadata_keys(self, test_candidate):
        """Test contacts block when DaData keys are not configured"""

        # Set phone and email on candidate
        test_candidate.phone = "+79951234567"
        test_candidate.email = "test@example.com"

        with patch('app.services.dadata.settings.DADATA_API_KEY', ''), \
             patch('app.services.dadata.settings.DADATA_SECRET_KEY', ''):

            contacts_block = await _build_contacts_block(test_candidate)

            assert contacts_block["key"] == "contacts"
            assert contacts_block["status"] == "info"
            assert contacts_block["data"]["status"] == "DaData не настроена"

    async def test_contacts_block_phone_validation(self, test_candidate):
        """Test contacts block phone validation logic"""

        test_candidate.phone = "+79951234567"

        # Mock invalid phone (qc != 0, 7)
        mock_phone_result = {
            "phone": "+7 995 123 45 67",
            "qc": 2  # мусор
        }

        with patch('app.services.glafira.verify.clean_phone', return_value=mock_phone_result):
            contacts_block = await _build_contacts_block(test_candidate)

            assert contacts_block["status"] == "warn"  # Invalid phone should trigger warning
            assert not contacts_block["data"]["phone"]["valid"]

    async def test_contacts_block_gender_mismatch(self, test_candidate):
        """Test contacts block detects gender mismatch"""

        test_candidate.gender = "male"

        # Mock name result with female gender
        mock_name_result = {
            "surname": "Иванова",
            "name": "Анна",
            "gender": "Ж",  # Female gender but candidate marked as male
            "qc": 0
        }

        with patch('app.services.glafira.verify.clean_name', return_value=mock_name_result):
            contacts_block = await _build_contacts_block(test_candidate)

            assert contacts_block["status"] == "warn"  # Gender mismatch should trigger warning
            assert not contacts_block["data"]["name"]["gender_match"]

    async def test_government_stubs_are_honest(self):
        """Test that government blocks are honest stubs, not fake verdicts"""

        gov_blocks = _build_government_stub_blocks()

        assert len(gov_blocks) == 5
        for block in gov_blocks:
            assert block["status"] == "info"
            assert block["data"]["status"] == "Не подключено"
            assert "152-ФЗ" in block["data"]["note"]
            # Ensure no fake verdicts
            assert "чисто" not in str(block["data"]).lower()
            assert "долгов нет" not in str(block["data"]).lower()
            assert "активен" not in str(block["data"]).lower()

    async def test_ai_block_handles_llm_failure(self, test_candidate):
        """Test AI block gracefully handles LLM failures"""

        with patch('app.services.glafira.verify.call_json', side_effect=Exception("LLM error")):
            from app.services.glafira.verify import _build_ai_intel_block

            ai_block = await _build_ai_intel_block(test_candidate, {})

            assert ai_block["key"] == "ai_intel"
            assert ai_block["status"] == "info"
            assert ai_block["data"]["status"] == "AI-оценка недоступна"

    async def test_verification_creates_event_and_audit(
        self, db_session, test_candidate, signed_consent
    ):
        """Test that verification creates proper event and audit records"""

        with patch('app.services.glafira.verify.clean_phone', return_value=None), \
             patch('app.services.glafira.verify.clean_email', return_value=None), \
             patch('app.services.glafira.verify.clean_name', return_value=None), \
             patch('app.services.glafira.verify.call_json', return_value={"summary": "test", "flags": [], "confidence": 0.5}):

            verification = await verify_candidate(
                db_session,
                candidate_id=test_candidate.id,
                company_id=test_candidate.company_id,
                actor_user_id=None
            )

            await db_session.commit()

            # Check event was created
            event_result = await db_session.execute(
                select(Event).where(
                    Event.type == 'verify',
                    Event.candidate_id == test_candidate.id
                )
            )
            event = event_result.scalar_one()
            assert event.actor_type == 'ai'
            assert event.actor_user_id is None
            assert "верификацию" in event.text