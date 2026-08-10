"""Тесты модуля «Чаты» (фаза 2 — агрегаты поверх единой ленты сообщений).

Дискриминирующие проверки:
  - ЕДИНЫЙ ИСТОЧНИК: отправка через существующий POST /candidates/{id}/messages
    видна и в той же ленте GET .../messages, и в агрегате /chats/dialogs — второго
    эндпоинта ленты/отправки для попапа нет.
  - Непрочитанные ПЕР-ЮЗЕР: A прочитал → у A 0, у B по-прежнему 1 (раздельный
    ReadState). Не тавтология: сравниваем ДВУХ разных юзеров одной компании.
  - hh-тред привязан к отклику (application_id), telegram — один диалог на человека.
  - meta честно: hh в available_channels ТОЛЬКО при hh_chat_id.
  - hh/sync переиспользует poll_chat_messages: импорт + дедуп по external_id.
  - hiring_manager → 403 (роутер под _deny_hm).
  - company-изоляция: чужие диалоги/unread/мета не видны.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models import Application, Candidate, Message, MessageRead, User, Vacancy


async def _login(async_client: AsyncClient, email: str, password: str = "Glafira2026!") -> dict[str, str]:
    resp = await async_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _msg(
    company_id,
    candidate_id,
    *,
    direction: str,
    channel: str = "telegram",
    body: str = "текст",
    sent_at: datetime | None = None,
    application_id=None,
    external_id: str | None = None,
    sender_type: str | None = None,
) -> Message:
    return Message(
        company_id=company_id,
        candidate_id=candidate_id,
        application_id=application_id,
        channel=channel,
        direction=direction,
        sender_type=sender_type or ("candidate" if direction == "in" else "recruiter"),
        body=body,
        sent_at=sent_at or datetime.now(timezone.utc),
        external_id=external_id,
    )


def _find(dialogs: list[dict], candidate_id) -> dict | None:
    return next((d for d in dialogs if d["candidate_id"] == str(candidate_id)), None)


# ── Единый источник ──────────────────────────────────────────────────────────


async def test_single_source_send_visible_in_list_and_dialogs(
    async_client, auth_headers, test_candidate
):
    """Отправка (существующий POST) видна в ТОЙ ЖЕ ленте (GET) и в агрегате диалогов.

    «Попап» и «вкладка» = один эндпоинт ленты; /chats только агрегирует.
    """
    cid = str(test_candidate.id)

    r = await async_client.post(
        f"/api/v1/candidates/{cid}/messages",
        headers=auth_headers,
        json={"channel": "sms", "body": "из попапа"},
    )
    assert r.status_code == 201, r.text

    lst = await async_client.get(
        f"/api/v1/candidates/{cid}/messages", headers=auth_headers
    )
    assert lst.status_code == 200
    assert "из попапа" in [m["body"] for m in lst.json()["items"]]

    # тот же датасет виден в агрегате диалогов
    dlg = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers)
    assert dlg.status_code == 200
    d = _find(dlg.json(), cid)
    assert d is not None and d["preview"] == "из попапа"


# ── Непрочитанные пер-юзер ───────────────────────────────────────────────────


async def test_unread_is_per_user(
    async_client, auth_headers, regular_user, db_session, test_candidate
):
    """Входящее → у A и B unread=1; A читает → A=0, B по-прежнему 1 (ReadState раздельный)."""
    cid = test_candidate.id
    db_session.add(_msg(test_candidate.company_id, cid, direction="in", body="Здравствуйте"))
    await db_session.flush()

    b_headers = await _login(async_client, regular_user.email)

    da = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers)
    assert _find(da.json(), cid)["unread_count"] == 1
    dbf = await async_client.get("/api/v1/chats/dialogs", headers=b_headers)
    assert _find(dbf.json(), cid)["unread_count"] == 1

    rr = await async_client.post(
        f"/api/v1/candidates/{cid}/messages/read", headers=auth_headers
    )
    assert rr.status_code == 200
    assert rr.json() == {"ok": True, "unread": 0}

    da2 = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers)
    assert _find(da2.json(), cid)["unread_count"] == 0

    # у B ничего не сдвинулось — отметка прочтения индивидуальна
    dbf2 = await async_client.get("/api/v1/chats/dialogs", headers=b_headers)
    assert _find(dbf2.json(), cid)["unread_count"] == 1


async def test_unread_total_sum_and_per_user(
    async_client, auth_headers, regular_user, db_session, test_candidate
):
    """unread-total = сумма непрочитанных по диалогам, пер-юзер."""
    c1 = test_candidate
    c2 = Candidate(company_id=c1.company_id, last_name="Второй", first_name="Кандидат", source="manual")
    db_session.add(c2)
    await db_session.flush()
    db_session.add(_msg(c1.company_id, c1.id, direction="in", body="1"))
    db_session.add(_msg(c1.company_id, c2.id, direction="in", body="2"))
    await db_session.flush()

    b_headers = await _login(async_client, regular_user.email)

    ta = await async_client.get("/api/v1/chats/unread-total", headers=auth_headers)
    assert ta.status_code == 200 and ta.json()["total"] == 2

    await async_client.post(f"/api/v1/candidates/{c1.id}/messages/read", headers=auth_headers)
    ta2 = await async_client.get("/api/v1/chats/unread-total", headers=auth_headers)
    assert ta2.json()["total"] == 1

    tb = await async_client.get("/api/v1/chats/unread-total", headers=b_headers)
    assert tb.json()["total"] == 2  # B не читал ничего


# ── hh-тред vs telegram-диалог ───────────────────────────────────────────────


async def test_hh_threads_not_mixed(async_client, auth_headers, db_session, test_candidate):
    """Два отклика hh (разные вакансии, разные hh_chat_id) → ?application_id разделяет треды."""
    c = test_candidate
    v1 = Vacancy(company_id=c.company_id, name="Backend", status="active")
    v2 = Vacancy(company_id=c.company_id, name="Frontend", status="active")
    db_session.add_all([v1, v2])
    await db_session.flush()
    a1 = Application(company_id=c.company_id, candidate_id=c.id, vacancy_id=v1.id, stage="response", hh_chat_id="chat1")
    a2 = Application(company_id=c.company_id, candidate_id=c.id, vacancy_id=v2.id, stage="response", hh_chat_id="chat2")
    db_session.add_all([a1, a2])
    await db_session.flush()
    db_session.add(_msg(c.company_id, c.id, direction="in", channel="hh", body="Отклик Backend", application_id=a1.id, external_id="m1"))
    db_session.add(_msg(c.company_id, c.id, direction="in", channel="hh", body="Отклик Frontend", application_id=a2.id, external_id="m2"))
    await db_session.flush()

    r1 = await async_client.get(
        f"/api/v1/candidates/{c.id}/messages", headers=auth_headers,
        params={"application_id": str(a1.id)},
    )
    items1 = r1.json()["items"]
    assert len(items1) == 1
    assert items1[0]["body"] == "Отклик Backend"
    assert items1[0]["vacancy_id"] == str(v1.id)
    assert "Backend" in items1[0]["application_context"]

    r2 = await async_client.get(
        f"/api/v1/candidates/{c.id}/messages", headers=auth_headers,
        params={"application_id": str(a2.id)},
    )
    items2 = r2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["vacancy_id"] == str(v2.id)

    r_all = await async_client.get(f"/api/v1/candidates/{c.id}/messages", headers=auth_headers)
    assert r_all.json()["total"] == 2  # без фильтра — оба треда в общей ленте


async def test_telegram_one_dialog_per_person(async_client, auth_headers, db_session, test_candidate):
    """Telegram (application_id=None) → ОДИН диалог на человека, а не per-vacancy."""
    c = test_candidate
    db_session.add(_msg(c.company_id, c.id, direction="out", channel="telegram", body="Первое",
                        sent_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    db_session.add(_msg(c.company_id, c.id, direction="in", channel="telegram", body="Ответ"))
    await db_session.flush()

    dlg = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers)
    mine = [d for d in dlg.json() if d["candidate_id"] == str(c.id)]
    assert len(mine) == 1
    assert mine[0]["channel"] == "telegram"
    assert mine[0]["last_sender_type"] == "candidate"  # контекст от ПОСЛЕДНЕГО сообщения
    assert mine[0]["last_inbound_at"] is not None


# ── meta каналов ─────────────────────────────────────────────────────────────


async def test_meta_hh_only_when_chat_id(async_client, auth_headers, db_session, test_candidate):
    """hh_available/available_channels честны: hh — ТОЛЬКО при Application.hh_chat_id."""
    c = test_candidate  # есть phone, preferred_channel default 'telegram'

    m0 = await async_client.get(f"/api/v1/chats/candidate/{c.id}/meta", headers=auth_headers)
    assert m0.status_code == 200
    j0 = m0.json()
    assert j0["hh_available"] is False
    assert "hh" not in j0["available_channels"]
    assert j0["telegram_available"] is True
    assert "telegram" in j0["available_channels"]
    assert j0["default_channel"] == "telegram"

    v = Vacancy(company_id=c.company_id, name="V", status="active")
    db_session.add(v)
    await db_session.flush()
    a = Application(company_id=c.company_id, candidate_id=c.id, vacancy_id=v.id, stage="response", hh_chat_id="chatX")
    db_session.add(a)
    await db_session.flush()

    m1 = await async_client.get(f"/api/v1/chats/candidate/{c.id}/meta", headers=auth_headers)
    j1 = m1.json()
    assert j1["hh_available"] is True
    assert "hh" in j1["available_channels"]


async def test_meta_no_contact_telegram_unavailable(async_client, auth_headers, db_session, test_company):
    """Нет телефона/username/tg_user_id → telegram НЕ в available, default_channel None."""
    c = Candidate(company_id=test_company.id, last_name="Без", first_name="Контакта",
                  source="manual", phone=None, messengers=[])
    db_session.add(c)
    await db_session.flush()

    m = await async_client.get(f"/api/v1/chats/candidate/{c.id}/meta", headers=auth_headers)
    assert m.status_code == 200
    j = m.json()
    assert j["telegram_available"] is False
    assert j["available_channels"] == []
    assert j["default_channel"] is None


async def test_meta_404_for_unknown_candidate(async_client, auth_headers):
    r = await async_client.get(f"/api/v1/chats/candidate/{uuid.uuid4()}/meta", headers=auth_headers)
    assert r.status_code == 404


# ── hh on-demand sync (переиспользует poll_chat_messages) ─────────────────────


async def test_hh_sync_imports_then_dedups(async_client, auth_headers, db_session, test_candidate):
    """hh/sync тянет входящее через poll_chat_messages; повторный вызов дедупит по external_id."""
    c = test_candidate
    v = Vacancy(company_id=c.company_id, name="V", status="active")
    db_session.add(v)
    await db_session.flush()
    a = Application(company_id=c.company_id, candidate_id=c.id, vacancy_id=v.id, stage="response", hh_chat_id="chat_777")
    db_session.add(a)
    await db_session.flush()

    mock_messages = {
        "items": [
            {
                "id": "hh_1",
                "type": "SIMPLE",
                "creation_time": "2024-01-15T10:00:00+0300",
                "sender_display_info": {"role": "APPLICANT"},
                "payload": {"text": "Здравствуйте"},
            }
        ]
    }
    with patch("app.services.chats.get_valid_access_token", new_callable=AsyncMock, return_value="tok"), \
         patch("app.jobs.poll_hh_messages.hh_client.get_chat_messages", new_callable=AsyncMock, return_value=mock_messages):
        r1 = await async_client.post(f"/api/v1/candidates/{c.id}/messages/hh/sync", headers=auth_headers)
        assert r1.status_code == 200 and r1.json()["imported"] == 1

        r2 = await async_client.post(f"/api/v1/candidates/{c.id}/messages/hh/sync", headers=auth_headers)
        assert r2.json()["imported"] == 0  # дедуп по external_id

    # импортированное входящее видно в ЕДИНОЙ ленте
    lst = await async_client.get(f"/api/v1/candidates/{c.id}/messages", headers=auth_headers)
    assert any(m["body"] == "Здравствуйте" for m in lst.json()["items"])


async def test_hh_sync_no_chat_returns_zero(async_client, auth_headers, test_candidate):
    """Кандидат без hh_chat_id → {imported:0} (не ошибка, hh не дёргается)."""
    r = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/messages/hh/sync", headers=auth_headers
    )
    assert r.status_code == 200 and r.json()["imported"] == 0


# ── Честная ошибка hh без диалога ────────────────────────────────────────────


async def test_send_hh_without_dialog_is_honest_error(async_client, auth_headers, test_candidate):
    """Отправка hh кандидату без negotiation → 400 (не тихий провал), ничего не сохранено."""
    with patch("app.services.message.get_valid_access_token", new_callable=AsyncMock, return_value="tok"):
        r = await async_client.post(
            f"/api/v1/candidates/{test_candidate.id}/messages",
            headers=auth_headers,
            json={"channel": "hh", "body": "Привет"},
        )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "hh недоступен" in err["message"]

    lst = await async_client.get(f"/api/v1/candidates/{test_candidate.id}/messages", headers=auth_headers)
    assert all(m["channel"] != "hh" for m in lst.json()["items"])


# ── RBAC / изоляция ──────────────────────────────────────────────────────────


async def test_hiring_manager_forbidden(async_client, db_session, admin_user):
    """hiring_manager → 403 на агрегатах чатов (роутер под _deny_hm)."""
    hm = User(
        company_id=admin_user.company_id,
        email="hm.chats@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Нанимающий Менеджер",
        role="hiring_manager",
        is_active=True,
    )
    db_session.add(hm)
    await db_session.commit()

    h = await _login(async_client, "hm.chats@example.com")
    for path in ("/api/v1/chats/dialogs", "/api/v1/chats/unread-total"):
        r = await async_client.get(path, headers=h)
        assert r.status_code == 403, f"{path}: {r.status_code}"


async def test_company_isolation(async_client, auth_headers, db_session, test_candidate, other_company):
    """Чужая компания: её диалоги/unread/мета не видны; unread-total считает только своё."""
    foreign = Candidate(company_id=other_company.id, last_name="Чужой", first_name="Контакт", source="manual")
    db_session.add(foreign)
    await db_session.flush()
    db_session.add(_msg(other_company.id, foreign.id, direction="in", body="секрет чужой компании"))
    # наше входящее — чтобы проверить, что total считает ровно 1 (наш), а не 2
    db_session.add(_msg(test_candidate.company_id, test_candidate.id, direction="in", body="наш"))
    await db_session.flush()

    dlg = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers)
    ids = [d["candidate_id"] for d in dlg.json()]
    assert str(foreign.id) not in ids
    assert str(test_candidate.id) in ids

    total = await async_client.get("/api/v1/chats/unread-total", headers=auth_headers)
    assert total.json()["total"] == 1  # только наш кандидат, чужой не посчитан

    # мета/read чужого кандидата → 404 (company-scoped, не «нет доступа»-намёк)
    m = await async_client.get(f"/api/v1/chats/candidate/{foreign.id}/meta", headers=auth_headers)
    assert m.status_code == 404
    rr = await async_client.post(f"/api/v1/candidates/{foreign.id}/messages/read", headers=auth_headers)
    assert rr.status_code == 404


# ── Поиск ────────────────────────────────────────────────────────────────────


async def test_dialogs_search_by_name_and_vacancy(async_client, auth_headers, db_session, test_candidate):
    """q ищет и по имени кандидата, и по названию вакансии последнего сообщения."""
    c1 = test_candidate  # «Тестов Тест»
    c2 = Candidate(company_id=c1.company_id, last_name="Петров", first_name="Пётр", source="manual")
    db_session.add(c2)
    await db_session.flush()
    v = Vacancy(company_id=c1.company_id, name="DevOps инженер", status="active")
    db_session.add(v)
    await db_session.flush()
    a = Application(company_id=c1.company_id, candidate_id=c2.id, vacancy_id=v.id, stage="response", hh_chat_id="ch")
    db_session.add(a)
    await db_session.flush()
    db_session.add(_msg(c1.company_id, c1.id, direction="out", channel="telegram", body="a"))
    db_session.add(_msg(c1.company_id, c2.id, direction="out", channel="hh", body="b", application_id=a.id))
    await db_session.flush()

    by_name = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers, params={"q": "Петров"})
    ids = [d["candidate_id"] for d in by_name.json()]
    assert str(c2.id) in ids and str(c1.id) not in ids

    by_vac = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers, params={"q": "DevOps"})
    ids2 = [d["candidate_id"] for d in by_vac.json()]
    assert str(c2.id) in ids2 and str(c1.id) not in ids2


# ── «Прочитать всё» (POST /chats/read-all) ───────────────────────────────────


async def test_read_all_marks_all_dialogs_and_is_per_user(
    async_client, auth_headers, regular_user, db_session, test_candidate
):
    """3 диалога с входящими → read-all A обнуляет ВСЕ его диалоги, у B остаётся всё.

    Дискриминирует пер-юзер: сравниваем ДВУХ разных юзеров одной компании — read-all
    юзера A не сдвигает ReadState юзера B (раздельные строки MessageRead).
    """
    c1 = test_candidate
    c2 = Candidate(company_id=c1.company_id, last_name="Второй", first_name="К", source="manual")
    c3 = Candidate(company_id=c1.company_id, last_name="Третий", first_name="К", source="manual")
    db_session.add_all([c2, c3])
    await db_session.flush()
    for c in (c1, c2, c3):
        db_session.add(_msg(c1.company_id, c.id, direction="in", body="вх"))
    await db_session.flush()

    b_headers = await _login(async_client, regular_user.email)

    ta = await async_client.get("/api/v1/chats/unread-total", headers=auth_headers)
    assert ta.json()["total"] == 3

    ra = await async_client.post("/api/v1/chats/read-all", headers=auth_headers)
    assert ra.status_code == 200, ra.text
    assert ra.json() == {"ok": True, "marked": 3}

    # у A всё прочитано
    ta2 = await async_client.get("/api/v1/chats/unread-total", headers=auth_headers)
    assert ta2.json()["total"] == 0
    dlg = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers)
    assert all(d["unread_count"] == 0 for d in dlg.json())

    # у B — по-прежнему 3 (read-all A не тронул ReadState B)
    tb = await async_client.get("/api/v1/chats/unread-total", headers=b_headers)
    assert tb.json()["total"] == 3


async def test_read_all_then_new_inbound_is_unread_again(
    async_client, auth_headers, db_session, test_candidate
):
    """read-all снимает старое, но входящее ПОЗЖЕ его отметки снова непрочитано.

    Дискриминирует: read-all пишет last_read_at = момент запроса (снимок), а не
    «прочитано навсегда». Старое (в прошлом) остаётся read, новое (в будущем от
    отметки) всплывает как unread — если бы отметка ставилась в +infinity, новое
    не появилось бы.
    """
    c = test_candidate
    db_session.add(_msg(c.company_id, c.id, direction="in", body="старое",
                        sent_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    await db_session.flush()

    ra = await async_client.post("/api/v1/chats/read-all", headers=auth_headers)
    assert ra.status_code == 200 and ra.json()["marked"] == 1
    t0 = await async_client.get("/api/v1/chats/unread-total", headers=auth_headers)
    assert t0.json()["total"] == 0

    # НОВОЕ входящее строго позже отметки read-all
    db_session.add(_msg(c.company_id, c.id, direction="in", body="новое",
                        sent_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
    await db_session.flush()

    t1 = await async_client.get("/api/v1/chats/unread-total", headers=auth_headers)
    assert t1.json()["total"] == 1
    dlg = await async_client.get("/api/v1/chats/dialogs", headers=auth_headers)
    assert _find(dlg.json(), c.id)["unread_count"] == 1


async def test_read_all_company_isolation(
    async_client, auth_headers, db_session, admin_user, test_candidate, other_company
):
    """read-all помечает ТОЛЬКО кандидатов своей компании; чужой диалог не тронут."""
    foreign = Candidate(company_id=other_company.id, last_name="Чужой", first_name="К", source="manual")
    db_session.add(foreign)
    await db_session.flush()
    db_session.add(_msg(other_company.id, foreign.id, direction="in", body="чужое"))
    db_session.add(_msg(test_candidate.company_id, test_candidate.id, direction="in", body="наше"))
    await db_session.flush()

    ra = await async_client.post("/api/v1/chats/read-all", headers=auth_headers)
    assert ra.status_code == 200
    assert ra.json()["marked"] == 1  # только наш кандидат

    # в message_reads нашего юзера есть свой кандидат и НЕТ чужого
    rows = (
        await db_session.execute(
            select(MessageRead.candidate_id).where(MessageRead.user_id == admin_user.id)
        )
    ).scalars().all()
    assert test_candidate.id in rows
    assert foreign.id not in rows


async def test_read_all_manager_scope_only_own(
    async_client, db_session, manager_user, manager_headers
):
    """Менеджер: read-all помечает только кандидатов его вакансий, не всю компанию."""
    company_id = manager_user.company_id
    c_allowed = Candidate(company_id=company_id, last_name="Свой", first_name="К", source="manual")
    c_other = Candidate(company_id=company_id, last_name="ВнеОбласти", first_name="К", source="manual")
    db_session.add_all([c_allowed, c_other])
    await db_session.flush()
    v = Vacancy(company_id=company_id, name="Вакансия менеджера", status="active",
                responsible_user_id=manager_user.id)
    db_session.add(v)
    await db_session.flush()
    db_session.add(Application(company_id=company_id, candidate_id=c_allowed.id,
                               vacancy_id=v.id, stage="response"))
    db_session.add(_msg(company_id, c_allowed.id, direction="in", body="свой"))
    db_session.add(_msg(company_id, c_other.id, direction="in", body="вне области"))
    await db_session.flush()

    # менеджер видит только свой диалог
    t0 = await async_client.get("/api/v1/chats/unread-total", headers=manager_headers)
    assert t0.json()["total"] == 1

    ra = await async_client.post("/api/v1/chats/read-all", headers=manager_headers)
    assert ra.status_code == 200
    assert ra.json()["marked"] == 1  # только кандидат из вакансии менеджера

    t1 = await async_client.get("/api/v1/chats/unread-total", headers=manager_headers)
    assert t1.json()["total"] == 0

    # ReadState создан по c_allowed, но НЕ по c_other
    rows = (
        await db_session.execute(
            select(MessageRead.candidate_id).where(MessageRead.user_id == manager_user.id)
        )
    ).scalars().all()
    assert c_allowed.id in rows
    assert c_other.id not in rows
