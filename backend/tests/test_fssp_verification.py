"""Тесты реальной проверки ФССП (исполнительные производства) через parser-api.com.

Покрывают:
  - клиент services/fssp.py (формат dob, done!=1 → None, нет ключа/ДР → None, парсинг
    записей, [] при 0 записях, сетевые/HTTP-ошибки → None);
  - блок верификации `fssp` (заглушка без ключа, «нужна дата рождения», warn+плашка при
    находках, clean при 0, honest «не удалось» при None — НЕ «чисто»);
  - интеграцию в verify_candidate (реальный блок попадает в верификацию, overall-статус).

Живые HTTP-вызовы НЕ идут — мокаем httpx / клиент. Локально не гонять (§6) — на VPS.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import fssp
from app.services.fssp import _format_dob, _normalize_record, search_enforcement
from app.services.glafira.verify import _build_fssp_block, verify_candidate


# --------------------------------------------------------------------------- #
# Хелпер: подделать httpx.AsyncClient (async ctx-manager + async .get)          #
# --------------------------------------------------------------------------- #
def _mock_async_client(*, json_data=None, raise_status=None, get_exc=None):
    """Вернуть подделку под `httpx.AsyncClient(...)`.

    json_data      — что вернёт resp.json() (dict);
    raise_status   — исключение для resp.raise_for_status() (напр. HTTPStatusError 403);
    get_exc        — исключение прямо на await client.get() (напр. TimeoutException).
    """
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.side_effect = raise_status  # None → no-op
    client = MagicMock()
    client.get = AsyncMock(side_effect=get_exc) if get_exc else AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=ctx)


# --------------------------------------------------------------------------- #
# Клиент services/fssp.py                                                       #
# --------------------------------------------------------------------------- #
class TestFsspClient:

    def test_format_dob_from_date(self):
        assert _format_dob(date(1990, 5, 3)) == "03.05.1990"

    def test_format_dob_none(self):
        assert _format_dob(None) is None

    def test_format_dob_string_passthrough(self):
        assert _format_dob("07.11.1985") == "07.11.1985"

    async def test_no_key_returns_none(self):
        """Пусто FSSP_API_KEY → None (интеграция выключена), НЕ пустой список."""
        with patch("app.services.fssp.settings.FSSP_API_KEY", ""):
            result = await search_enforcement("Иванов", "Иван", None, date(1990, 1, 1))
        assert result is None

    async def test_no_dob_returns_none(self):
        """Ключ есть, но даты рождения нет → None (провайдер без dob не ищет)."""
        with patch("app.services.fssp.settings.FSSP_API_KEY", "k"):
            result = await search_enforcement("Иванов", "Иван", None, None)
        assert result is None

    async def test_done_not_1_returns_none(self):
        """done != 1 → None (не удалось проверить, НЕ «чисто»)."""
        mock = _mock_async_client(json_data={"done": 0, "error": "limit"})
        with patch("app.services.fssp.settings.FSSP_API_KEY", "k"), \
             patch("app.services.fssp.httpx.AsyncClient", mock):
            result = await search_enforcement("Иванов", "Иван", None, date(1990, 1, 1))
        assert result is None

    async def test_success_parses_records(self):
        """done=1 + записи → список нормализованных словарей (с raw)."""
        payload = {
            "done": 1,
            "records": [
                {
                    "name": "Иванов Иван Иванович, 01.01.1990",
                    "exe_production": "12345/20/77001-ИП от 01.02.2020",
                    "subject": "Взыскание задолженности",
                    "amount": "15000",
                    "department": "ОСП по ЦАО",
                    "bailiff": "Петров П.П., +7...",
                    "ip_end": "",
                }
            ],
        }
        mock = _mock_async_client(json_data=payload)
        with patch("app.services.fssp.settings.FSSP_API_KEY", "k"), \
             patch("app.services.fssp.httpx.AsyncClient", mock):
            result = await search_enforcement("Иванов", "Иван", "Иванович", date(1990, 1, 1))
        assert isinstance(result, list) and len(result) == 1
        rec = result[0]
        assert rec["debtor"] == "Иванов Иван Иванович, 01.01.1990"
        assert rec["production"].startswith("12345/20/77001-ИП")
        assert rec["amount"] == "15000"
        assert rec["raw"] == payload["records"][0]  # исходник сохранён целиком

    async def test_zero_records_returns_empty_list(self):
        """done=1 + нет записей → [] (провайдер отработал, ИП нет). [] ≠ None."""
        mock = _mock_async_client(json_data={"done": 1, "records": []})
        with patch("app.services.fssp.settings.FSSP_API_KEY", "k"), \
             patch("app.services.fssp.httpx.AsyncClient", mock):
            result = await search_enforcement("Иванов", "Иван", None, date(1990, 1, 1))
        assert result == []

    async def test_http_status_error_returns_none(self):
        """403/400 (raise_for_status) → None."""
        err = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=MagicMock(text="access denied")
        )
        mock = _mock_async_client(json_data=None, raise_status=err)
        with patch("app.services.fssp.settings.FSSP_API_KEY", "k"), \
             patch("app.services.fssp.httpx.AsyncClient", mock):
            result = await search_enforcement("Иванов", "Иван", None, date(1990, 1, 1))
        assert result is None

    async def test_timeout_returns_none(self):
        """Сетевой таймаут → None."""
        mock = _mock_async_client(get_exc=httpx.TimeoutException("timeout"))
        with patch("app.services.fssp.settings.FSSP_API_KEY", "k"), \
             patch("app.services.fssp.httpx.AsyncClient", mock):
            result = await search_enforcement("Иванов", "Иван", None, date(1990, 1, 1))
        assert result is None

    async def test_query_params_include_key_dob_and_optional_patronymic(self):
        """dob уходит в формате дд.мм.ГГГГ; patronymic — только если задан."""
        captured = {}

        def _client_factory(*args, **kwargs):
            resp = MagicMock()
            resp.json.return_value = {"done": 1, "records": []}
            resp.raise_for_status.return_value = None

            async def _get(url, params=None):
                captured["url"] = url
                captured["params"] = params
                return resp

            client = MagicMock()
            client.get = _get
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=client)
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx

        with patch("app.services.fssp.settings.FSSP_API_KEY", "secret"), \
             patch("app.services.fssp.httpx.AsyncClient", _client_factory):
            await search_enforcement("Сидоров", "Пётр", "Иванович", date(1988, 12, 5))

        assert captured["url"].endswith("/search_fiz")
        assert captured["params"]["key"] == "secret"
        assert captured["params"]["lastName"] == "Сидоров"
        assert captured["params"]["firstName"] == "Пётр"
        assert captured["params"]["dob"] == "05.12.1988"
        assert captured["params"]["patronymic"] == "Иванович"

    def test_normalize_record_defensive_and_keeps_raw(self):
        raw = {"unknown_key": "x", "amount": 500}
        norm = _normalize_record(raw)
        assert norm["raw"] == raw
        assert norm["amount"] == "500"
        assert norm["debtor"] == ""  # неизвестный ключ ФИО → пусто, не падаем


# --------------------------------------------------------------------------- #
# Блок верификации `fssp`                                                       #
# --------------------------------------------------------------------------- #
class TestFsspVerificationBlock:

    async def test_stub_when_no_key(self, test_candidate):
        """Пусто FSSP_API_KEY → честная заглушка «Не подключено» (как раньше)."""
        with patch("app.services.glafira.verify.settings.FSSP_API_KEY", ""):
            block = await _build_fssp_block(test_candidate)
        assert block["key"] == "fssp"
        assert block["status"] == "info"
        assert block["data"]["status"] == "Не подключено"
        assert "152-ФЗ" in block["data"]["note"]
        assert "items" not in block["data"]

    async def test_needs_birth_date(self, test_candidate):
        """Ключ есть, у кандидата нет ДР → честный info «нужна дата рождения»."""
        test_candidate.birth_date = None
        with patch("app.services.glafira.verify.settings.FSSP_API_KEY", "k"):
            block = await _build_fssp_block(test_candidate)
        assert block["status"] == "info"
        assert block["data"]["status"] == "Нужна дата рождения"
        assert "дату рождения" in block["data"]["note"]

    async def test_found_matches_warn_with_disclaimer(self, test_candidate):
        """Найдены ИП → warn + список items + обязательная плашка про однофамильца."""
        test_candidate.birth_date = date(1990, 1, 1)
        items = [{"debtor": "Тестов Тест", "production": "1/20-ИП", "raw": {}}]
        with patch("app.services.glafira.verify.settings.FSSP_API_KEY", "k"), \
             patch("app.services.glafira.verify.search_enforcement",
                   new=AsyncMock(return_value=items)):
            block = await _build_fssp_block(test_candidate)
        assert block["status"] == "warn"
        assert block["data"]["found"] == 1
        assert block["data"]["items"] == items
        note = block["data"]["note"].lower()
        assert "однофамил" in note
        assert "не подтверждённая" in note

    async def test_clean_when_zero(self, test_candidate):
        """0 ИП (провайдер отработал) → clean, честный текст «не найдено»."""
        test_candidate.birth_date = date(1990, 1, 1)
        with patch("app.services.glafira.verify.settings.FSSP_API_KEY", "k"), \
             patch("app.services.glafira.verify.search_enforcement",
                   new=AsyncMock(return_value=[])):
            block = await _build_fssp_block(test_candidate)
        assert block["status"] == "clean"
        assert block["data"]["found"] == 0
        assert block["data"]["items"] == []

    async def test_couldnt_check_is_not_clean(self, test_candidate):
        """None (сбой/лимит/403) → info «не удалось проверить», НЕ «чисто» (§0)."""
        test_candidate.birth_date = date(1990, 1, 1)
        with patch("app.services.glafira.verify.settings.FSSP_API_KEY", "k"), \
             patch("app.services.glafira.verify.search_enforcement",
                   new=AsyncMock(return_value=None)):
            block = await _build_fssp_block(test_candidate)
        assert block["status"] != "clean"
        assert block["status"] == "info"
        assert block["data"]["status"] == "Не удалось проверить"
        assert "недоступна" in block["data"]["note"].lower()
        # никаких фейк-вердиктов «чисто/долгов нет»
        assert "чисто" not in str(block["data"]).lower()


# --------------------------------------------------------------------------- #
# Интеграция в verify_candidate                                                 #
# --------------------------------------------------------------------------- #
class TestFsspInVerifyCandidate:

    async def test_real_fssp_block_wired_and_overall_status(
        self, db_session, test_candidate, signed_consent
    ):
        """С ключом + ДР + находкой: блок fssp реальный, попадает в верификацию, overall=warn."""
        test_candidate.birth_date = date(1990, 1, 1)
        await db_session.commit()

        items = [{"debtor": "Тестов Тест Тест", "production": "77/22-ИП", "raw": {}}]
        with patch("app.services.glafira.verify.settings.FSSP_API_KEY", "k"), \
             patch("app.services.glafira.verify.search_enforcement",
                   new=AsyncMock(return_value=items)), \
             patch("app.services.glafira.verify.clean_phone", return_value=None), \
             patch("app.services.glafira.verify.clean_email", return_value=None), \
             patch("app.services.glafira.verify.clean_name", return_value=None), \
             patch("app.services.glafira.verify.claude_cli_complete", return_value=None):
            verification = await verify_candidate(
                db_session,
                candidate_id=test_candidate.id,
                company_id=test_candidate.company_id,
                actor_user_id=None,
            )

        fssp_block = next((b for b in verification.blocks if b["key"] == "fssp"), None)
        assert fssp_block is not None
        assert fssp_block["status"] == "warn"
        assert fssp_block["data"]["items"] == items
        # ровно один блок fssp (заглушка заменена, не задвоена)
        assert sum(1 for b in verification.blocks if b["key"] == "fssp") == 1
        assert verification.status == "warn"  # warn от ФССП поднимает overall

    async def test_no_key_keeps_fssp_stub(
        self, db_session, test_candidate, signed_consent
    ):
        """Без ключа блок fssp остаётся честной заглушкой внутри полной верификации."""
        with patch("app.services.glafira.verify.settings.FSSP_API_KEY", ""), \
             patch("app.services.glafira.verify.clean_phone", return_value=None), \
             patch("app.services.glafira.verify.clean_email", return_value=None), \
             patch("app.services.glafira.verify.clean_name", return_value=None), \
             patch("app.services.glafira.verify.claude_cli_complete", return_value=None):
            verification = await verify_candidate(
                db_session,
                candidate_id=test_candidate.id,
                company_id=test_candidate.company_id,
                actor_user_id=None,
            )

        fssp_block = next((b for b in verification.blocks if b["key"] == "fssp"), None)
        assert fssp_block is not None
        assert fssp_block["data"]["status"] == "Не подключено"
