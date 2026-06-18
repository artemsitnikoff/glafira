"""Тесты входящей Telegram-синхронизации.

Telethon-слой замокан на уровне импорта сервиса:
  app.services.integrations.telegram.service.tg_client.fetch_inbound
Сама телесеть не используется.

Покрытие:
  1. sync_inbound без подключения → {"imported":0,"connected":False}, fetch не вызван.
  2. sync_inbound connected, матч по tg_user_id → 2 строки Message (direction='in', channel='telegram'),
     повтор → 0 новых (дедуп).
  3. Матч по username (tg_user_id отсутствует).
  4. Матч по phone (tg_user_id и messengers отсутствуют).
  5. _send_telegram сохраняет extra['tg_user_id'] после успешной отправки.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from cryptography.fernet import Fernet

from sqlalchemy import select

from app.services.integrations.telegram import service as tg
from app.services.settings.crypto import encrypt_text
from app.core.errors import ValidationError
from app.models import Integration, Message, Candidate

# Путь мока — на уровне import-site (service.py импортирует tg_client)
FETCH_INBOUND = "app.services.integrations.telegram.service.tg_client.fetch_inbound"
FETCH_CANDIDATE_INBOUND = "app.services.integrations.telegram.service.tg_client.fetch_candidate_inbound"
# Патч-сайт для _send_telegram (test 5): message.py импортирует tg_service
SEND_TO_CANDIDATE = "app.services.message.tg_service.send_to_candidate"


# ---------------------------------------------------------------------------
# Хелперы / фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture
def fernet_key(monkeypatch):
    monkeypatch.setattr("app.config.settings.FERNET_KEY", Fernet.generate_key().decode())


async def _make_connected_integration(db_session, company_id, fernet_key_fixture=None):
    """Создаёт Integration с state='connected' и зашифрованной сессией."""
    session_str = "fake-connected-session"
    config = {
        "state": "connected",
        "session": encrypt_text(session_str),
        "phone": "+79001234567",
        "tg_user": {"id": "1", "username": "recruiter"},
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
    }
    row = Integration(
        company_id=company_id,
        provider="telegram",
        status="connected",
        config=config,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _make_candidate(db_session, company_id, *, phone=None, messengers=None, tg_user_id=None):
    """Создаёт кандидата с нужными реквизитами Telegram."""
    extra = {}
    if tg_user_id:
        extra["tg_user_id"] = tg_user_id
    cand = Candidate(
        company_id=company_id,
        first_name="Кандидат",
        last_name="Тестовый",
        source="manual",
        phone=phone,
        messengers=messengers or [],
        extra=extra,
    )
    db_session.add(cand)
    await db_session.flush()
    await db_session.refresh(cand)
    return cand


def _inbound_msgs(peer_id: str, count: int = 2) -> list[dict]:
    """Синтетические входящие от fetch_inbound."""
    return [
        {
            "peer_id": peer_id,
            "username": None,
            "phone": None,
            "msg_id": str(100 + i),
            "text": f"Привет, это сообщение {i}",
            "date": datetime(2026, 6, 17, 12, i, 0, tzinfo=timezone.utc),
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Тест 1: интеграция не подключена
# ---------------------------------------------------------------------------

async def test_sync_inbound_not_connected(db_session, admin_user, fernet_key):
    """sync_inbound без подключённой интеграции → imported=0, connected=False."""
    fetch_mock = AsyncMock()
    with patch(FETCH_INBOUND, new=fetch_mock):
        result = await tg.sync_inbound(db_session, admin_user.company_id)

    assert result == {"imported": 0, "connected": False}
    fetch_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# Тест 2: матч по tg_user_id + дедуп
# ---------------------------------------------------------------------------

async def test_sync_inbound_by_tg_user_id(db_session, admin_user, fernet_key):
    """Матч по tg_user_id → 2 Message создаётся; повтор → 0 (дедуп)."""
    await _make_connected_integration(db_session, admin_user.company_id)
    cand = await _make_candidate(db_session, admin_user.company_id, tg_user_id="777")

    msgs = _inbound_msgs("777", count=2)

    with patch(FETCH_INBOUND, new=AsyncMock(return_value=msgs)):
        r1 = await tg.sync_inbound(db_session, admin_user.company_id)
    await db_session.flush()

    assert r1["imported"] == 2
    assert r1["connected"] is True

    # Проверяем сохранённые строки
    rows = (await db_session.execute(
        select(Message).where(
            Message.candidate_id == cand.id,
            Message.channel == "telegram",
            Message.direction == "in",
        )
    )).scalars().all()
    assert len(rows) == 2
    for row in rows:
        assert row.sender_type == "candidate"
        assert row.sender_user_id is None
        assert row.company_id == admin_user.company_id
        assert row.external_id.startswith("tg:777:")

    # Дедуп: повторный вызов с теми же данными → 0 новых
    with patch(FETCH_INBOUND, new=AsyncMock(return_value=msgs)):
        r2 = await tg.sync_inbound(db_session, admin_user.company_id)
    assert r2["imported"] == 0
    assert r2["connected"] is True


# ---------------------------------------------------------------------------
# Тест 3: матч по username
# ---------------------------------------------------------------------------

async def test_sync_inbound_by_username(db_session, admin_user, fernet_key):
    """Матч по username (нет tg_user_id) → Message сохранён."""
    await _make_connected_integration(db_session, admin_user.company_id)
    cand = await _make_candidate(
        db_session,
        admin_user.company_id,
        messengers=[{"type": "tg", "url": "https://t.me/ivan_test"}],
    )

    inbound = [
        {
            "peer_id": "888",
            "username": "ivan_test",
            "phone": None,
            "msg_id": "200",
            "text": "Добрый день",
            "date": datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc),
        }
    ]

    with patch(FETCH_INBOUND, new=AsyncMock(return_value=inbound)):
        result = await tg.sync_inbound(db_session, admin_user.company_id)

    assert result["imported"] == 1
    assert result["connected"] is True

    row = (await db_session.execute(
        select(Message).where(
            Message.candidate_id == cand.id,
            Message.channel == "telegram",
        )
    )).scalar_one()
    assert row.external_id == "tg:888:200"
    assert row.direction == "in"


# ---------------------------------------------------------------------------
# Тест 4: матч по phone
# ---------------------------------------------------------------------------

async def test_sync_inbound_by_phone(db_session, admin_user, fernet_key):
    """Матч по нормализованному телефону (нет tg_user_id и messengers) → Message сохранён."""
    await _make_connected_integration(db_session, admin_user.company_id)
    cand = await _make_candidate(
        db_session,
        admin_user.company_id,
        phone="+7 912 345 67 89",  # человекочитаемый формат из карточки
    )

    inbound = [
        {
            "peer_id": "999",
            "username": None,
            "phone": "79123456789",  # цифры без '+', как Telethon отдаёт entity.phone
            "msg_id": "300",
            "text": "Здравствуйте!",
            "date": datetime(2026, 6, 17, 9, 0, 0, tzinfo=timezone.utc),
        }
    ]

    with patch(FETCH_INBOUND, new=AsyncMock(return_value=inbound)):
        result = await tg.sync_inbound(db_session, admin_user.company_id)

    assert result["imported"] == 1

    row = (await db_session.execute(
        select(Message).where(Message.candidate_id == cand.id, Message.channel == "telegram")
    )).scalar_one()
    assert row.external_id == "tg:999:300"


# ---------------------------------------------------------------------------
# Тест 5: _send_telegram сохраняет extra['tg_user_id']
# ---------------------------------------------------------------------------

async def test_send_telegram_stores_tg_user_id(db_session, admin_user, fernet_key):
    """После успешного send_to_candidate extra['tg_user_id'] кандидата сохранён."""
    from app.services.message import _send_telegram
    from app.schemas.message import MessageCreate

    # Кандидат без tg_user_id
    cand = await _make_candidate(
        db_session,
        admin_user.company_id,
        phone="+79001112233",
    )
    assert (cand.extra or {}).get("tg_user_id") is None

    message_data = MessageCreate(channel="telegram", body="Тестовое сообщение", application_id=None)

    # Мокаем tg_service.send_to_candidate (через import-site message.py)
    send_mock = AsyncMock(return_value={"message_id": "5", "peer": "777"})
    with patch(SEND_TO_CANDIDATE, new=send_mock):
        external_id = await _send_telegram(
            db_session, admin_user.company_id, cand, message_data, None
        )

    assert external_id == "5"
    assert cand.extra["tg_user_id"] == "777"
    send_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Тест 6: company_id изоляция (кандидат другой компании не матчится)
# ---------------------------------------------------------------------------

async def test_sync_inbound_candidate_scoped_direct_resolve(db_session, admin_user, fernet_key):
    """Синк по candidate_id: прямой резолв диалога БЕЗ заранее сохранённого tg_user_id
    (кандидат только с телефоном) → сообщения импортируются + tg_user_id бэкфиллится."""
    await _make_connected_integration(db_session, admin_user.company_id)
    cand = await _make_candidate(
        db_session, admin_user.company_id, phone="+7 900 555 11 22",
    )
    assert (cand.extra or {}).get("tg_user_id") is None

    direct = {
        "peer_id": "654321",
        "messages": [
            {"msg_id": "10", "text": "Да, мне интересно", "date": datetime(2026, 6, 17, 13, 0, 0, tzinfo=timezone.utc)},
            {"msg_id": "11", "text": "Когда собеседование?", "date": datetime(2026, 6, 17, 13, 1, 0, tzinfo=timezone.utc)},
        ],
    }
    with patch(FETCH_CANDIDATE_INBOUND, new=AsyncMock(return_value=direct)):
        r = await tg.sync_inbound(db_session, admin_user.company_id, candidate_id=cand.id)

    assert r == {"imported": 2, "connected": True}
    # tg_user_id бэкфилл
    await db_session.refresh(cand)
    assert cand.extra["tg_user_id"] == "654321"
    rows = (await db_session.execute(
        select(Message).where(Message.candidate_id == cand.id, Message.direction == "in")
    )).scalars().all()
    assert len(rows) == 2
    assert {row.external_id for row in rows} == {"tg:654321:10", "tg:654321:11"}

    # Повтор → дедуп, 0 новых
    with patch(FETCH_CANDIDATE_INBOUND, new=AsyncMock(return_value=direct)):
        r2 = await tg.sync_inbound(db_session, admin_user.company_id, candidate_id=cand.id)
    assert r2["imported"] == 0


async def test_sync_inbound_candidate_no_contacts_noop(db_session, admin_user, fernet_key):
    """Синк по candidate_id без username и телефона → 0, fetch_candidate_inbound не зовётся."""
    await _make_connected_integration(db_session, admin_user.company_id)
    cand = await _make_candidate(db_session, admin_user.company_id)  # ни phone, ни messengers
    fetch_mock = AsyncMock()
    with patch(FETCH_CANDIDATE_INBOUND, new=fetch_mock):
        r = await tg.sync_inbound(db_session, admin_user.company_id, candidate_id=cand.id)
    assert r == {"imported": 0, "connected": True}
    fetch_mock.assert_not_awaited()


async def test_sync_inbound_company_isolation(db_session, admin_user, fernet_key):
    """Кандидат из другой компании не должен матчиться."""
    from app.models import Company

    # Создаём вторую компанию и её кандидата
    other_company = Company(id=uuid4(), name="Other Company")
    db_session.add(other_company)
    await db_session.flush()

    # Кандидат другой компании с тем же tg_user_id
    other_cand = Candidate(
        company_id=other_company.id,
        first_name="Чужой",
        last_name="Кандидат",
        source="manual",
        extra={"tg_user_id": "42"},
        messengers=[],
    )
    db_session.add(other_cand)
    await db_session.flush()

    # Интеграция и кандидат нашей компании
    await _make_connected_integration(db_session, admin_user.company_id)
    our_cand = await _make_candidate(
        db_session, admin_user.company_id, tg_user_id="42"
    )

    inbound = [
        {
            "peer_id": "42",
            "username": None,
            "phone": None,
            "msg_id": "500",
            "text": "Привет",
            "date": datetime(2026, 6, 17, 8, 0, 0, tzinfo=timezone.utc),
        }
    ]

    with patch(FETCH_INBOUND, new=AsyncMock(return_value=inbound)):
        result = await tg.sync_inbound(db_session, admin_user.company_id)

    assert result["imported"] == 1

    # Сообщение привязано к нашему кандидату, не к чужому
    msg = (await db_session.execute(
        select(Message).where(Message.channel == "telegram", Message.company_id == admin_user.company_id)
    )).scalar_one()
    assert msg.candidate_id == our_cand.id

    # Для другой компании — нет сообщений
    other_msgs = (await db_session.execute(
        select(Message).where(Message.company_id == other_company.id)
    )).scalars().all()
    assert len(other_msgs) == 0


# ---------------------------------------------------------------------------
# Тест 9: company-wide sync с кандидатом только через messengers (без phone/tg_user_id)
# Регрессия: Candidate.messengers != "[]" (JSONB <> varchar) давало
# UndefinedFunctionError на Postgres — проверяем, что фильтр-запрос не падает.
# ---------------------------------------------------------------------------

async def test_sync_inbound_messengers_only_no_sql_error(db_session, admin_user, fernet_key):
    """Company-wide sync на кандидате только с messengers (нет phone/tg_user_id).
    Запрос должен пройти без ошибки оператора JSONB <> varchar."""
    await _make_connected_integration(db_session, admin_user.company_id)
    cand = await _make_candidate(
        db_session,
        admin_user.company_id,
        messengers=[{"type": "tg", "url": "https://t.me/only_messenger_user"}],
    )

    inbound = [
        {
            "peer_id": "111",
            "username": "only_messenger_user",
            "phone": None,
            "msg_id": "700",
            "text": "Сообщение через messengers",
            "date": datetime(2026, 6, 18, 11, 0, 0, tzinfo=timezone.utc),
        }
    ]

    # Убеждаемся: без phone/tg_user_id кандидат всё равно попадает в выборку через messengers
    with patch(FETCH_INBOUND, new=AsyncMock(return_value=inbound)):
        result = await tg.sync_inbound(db_session, admin_user.company_id)

    assert result["connected"] is True
    assert result["imported"] == 1

    row = (await db_session.execute(
        select(Message).where(Message.candidate_id == cand.id, Message.channel == "telegram")
    )).scalar_one()
    assert row.external_id == "tg:111:700"
