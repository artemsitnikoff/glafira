"""Тесты отмены/переноса встречи кандидатом (POST /public/schedule/{token}/cancel).

Модель фичи: отдельного «переноса» нет — отмена освобождает слот (booked→active),
после чего кандидат выбирает время заново существующим POST /book. Ограничения:
не позднее чем за 24ч до начала, максимум 2 переноса (interview_links.reschedule_count).

Б24-клиент и почта всегда замоканы — тесты не ходят в сеть.

⚠️ Дедлайн НЕ требует заморозки времени: проверка относительная (slot_from - now < 24ч),
поэтому слоты задаём смещением от текущего момента — результат детерминирован при любом
времени прогона.
"""

import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select as sa_select

from app.models import (
    Application, AuditLog, Event, Integration, InterviewLink, Vacancy, VacancyTeam
)

WEBHOOK = "https://demo.bitrix24.ru/rest/1/abc123/"
TZ_MSK = "Europe/Moscow"


# ──────────────────────────────────────────────────────────────────────────────
# Фикстуры
# ──────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def vacancy_with_team(db_session, admin_user) -> Vacancy:
    v = Vacancy(
        company_id=admin_user.company_id,
        name="Тестовая вакансия",
        status="active",
        responsible_user_id=admin_user.id,
    )
    db_session.add(v)
    await db_session.flush()

    db_session.add(VacancyTeam(
        company_id=admin_user.company_id,
        vacancy_id=v.id,
        user_id=admin_user.id,
        is_responsible=True,
    ))
    await db_session.flush()
    return v


@pytest_asyncio.fixture
async def application(db_session, admin_user, vacancy_with_team, test_candidate) -> Application:
    app = Application(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        vacancy_id=vacancy_with_team.id,
        stage="interview",
    )
    db_session.add(app)
    await db_session.flush()
    return app


@pytest_asyncio.fixture
async def b24_integration(db_session, admin_user) -> Integration:
    from app.services.settings.crypto import encrypt_text

    row = Integration(
        company_id=admin_user.company_id,
        provider="bitrix24",
        status="connected",
        config={
            "webhook_url": encrypt_text(WEBHOOK),
            "portal": "demo.bitrix24.ru",
            "tz": TZ_MSK,
            "lead_hours": 0,
        },
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def booked_link(db_session, admin_user, application) -> InterviewLink:
    """Забронированная ссылка со слотом ЗАВЕДОМО дальше дедлайна (через 3 дня)."""
    slot_from = datetime.now(timezone.utc) + timedelta(days=3)
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="booked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        slot_from=slot_from,
        slot_to=slot_from + timedelta(hours=1),
        b24_event_id="99",
        booked_at=datetime.now(timezone.utc),
        reschedule_count=0,
    )
    db_session.add(link)
    await db_session.flush()
    return link


def _cancel_url(token: str) -> str:
    return f"/api/v1/public/schedule/{token}/cancel"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Happy path
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_success_releases_slot(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """Отмена: 200, ссылка → active, слот/событие обнулены, счётчик +1, событие Б24 удалено."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock) as mock_delete,
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        resp = await async_client.post(_cancel_url(booked_link.token))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "active"
    assert data["reschedules_left"] == 1

    # Событие Б24 удалено с тем же id и owner=b24_user_id рекрутёра
    mock_delete.assert_awaited_once()
    assert mock_delete.await_args.kwargs["event_id"] == "99"
    assert mock_delete.await_args.kwargs["owner_id"] == 42

    # ⚠️ expire_on_commit=False → без refresh получим stale-инстанс из identity-map
    await db_session.refresh(booked_link)
    assert booked_link.status == "active"
    assert booked_link.slot_from is None
    assert booked_link.slot_to is None
    assert booked_link.b24_event_id is None
    assert booked_link.reschedule_count == 1


@pytest.mark.asyncio
async def test_cancel_writes_event_and_audit(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """Инвариант §2.2: отмена пишет Event(type='interview') и audit interview_cancelled."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock),
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        resp = await async_client.post(_cancel_url(booked_link.token))
    assert resp.status_code == 200, resp.text

    events = (await db_session.execute(
        sa_select(Event).where(
            Event.company_id == admin_user.company_id,
            Event.type == "interview",
        )
    )).scalars().all()
    assert any("отменил встречу" in (e.text or "") for e in events), \
        "Должен быть Event об отмене встречи"

    audits = (await db_session.execute(
        sa_select(AuditLog).where(
            AuditLog.company_id == admin_user.company_id,
            AuditLog.action == "interview_cancelled",
        )
    )).scalars().all()
    assert len(audits) == 1, "Должна быть ровно одна запись audit_log об отмене"
    after = (audits[0].changes or {}).get("after", {})
    assert after["b24_event_deleted"] is True
    assert after["reschedule_count"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# 2. 409 — статус не 'booked'
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_not_booked_returns_409(
    async_client, db_session, admin_user, application
):
    """Отмена незабронированной (active) ссылки → 409 NOT_BOOKED."""
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add(link)
    await db_session.flush()

    resp = await async_client.post(_cancel_url(link.token))
    assert resp.status_code == 409
    assert "NOT_BOOKED" in resp.text


@pytest.mark.asyncio
async def test_cancel_unknown_token_404(async_client):
    """Несуществующий токен → 404 без деталей."""
    resp = await async_client.post(_cancel_url("nonexistent_token_xyz"))
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 3. 409 — дедлайн (менее 24ч до встречи)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_past_deadline_returns_409(
    async_client, db_session, admin_user, vacancy_with_team, application, b24_integration
):
    """Встреча через час → 409 CHANGE_DEADLINE_PASSED, ничего не меняется."""
    slot_from = datetime.now(timezone.utc) + timedelta(hours=1)
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="booked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        slot_from=slot_from,
        slot_to=slot_from + timedelta(hours=1),
        b24_event_id="77",
        reschedule_count=0,
    )
    db_session.add(link)
    await db_session.flush()

    with patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
               new_callable=AsyncMock) as mock_delete:
        resp = await async_client.post(_cancel_url(link.token))

    assert resp.status_code == 409
    assert "CHANGE_DEADLINE_PASSED" in resp.text
    mock_delete.assert_not_awaited()

    await db_session.refresh(link)
    assert link.status == "booked", "Отклонённая отмена не должна менять статус"
    assert link.reschedule_count == 0


# ──────────────────────────────────────────────────────────────────────────────
# 4. 409 — лимит переносов
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_reschedule_limit_returns_409(
    async_client, db_session, admin_user, vacancy_with_team, application, b24_integration
):
    """reschedule_count=2 → 409 RESCHEDULE_LIMIT даже если до встречи далеко."""
    slot_from = datetime.now(timezone.utc) + timedelta(days=5)
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="booked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        slot_from=slot_from,
        slot_to=slot_from + timedelta(hours=1),
        b24_event_id="88",
        reschedule_count=2,
    )
    db_session.add(link)
    await db_session.flush()

    resp = await async_client.post(_cancel_url(link.token))
    assert resp.status_code == 409
    assert "RESCHEDULE_LIMIT" in resp.text

    await db_session.refresh(link)
    assert link.status == "booked"
    assert link.reschedule_count == 2


# ──────────────────────────────────────────────────────────────────────────────
# 5. Гонка двойного клика
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_double_click_second_returns_409(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """Второй вызов cancel по тому же токену → 409, счётчик увеличен ОДИН раз."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock) as mock_delete,
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        first = await async_client.post(_cancel_url(booked_link.token))
        second = await async_client.post(_cancel_url(booked_link.token))

    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert "NOT_BOOKED" in second.text
    # Событие Б24 удаляется ровно один раз — иначе Б24 получил бы двойное удаление
    assert mock_delete.await_count == 1

    await db_session.refresh(booked_link)
    assert booked_link.reschedule_count == 1, "Счётчик не должен инкрементиться дважды"


# ──────────────────────────────────────────────────────────────────────────────
# 6. FAIL-SOFT: Б24 недоступен
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_b24_failure_is_fail_soft(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """Б24 упал → отмена ВСЁ РАВНО проходит, но факт фиксируется честно в audit."""
    from app.core.errors import AppError

    admin_user.b24_user_id = 42
    await db_session.flush()

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock,
              side_effect=AppError(code="B24_TIMEOUT", message="Таймаут", status_code=400)),
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        resp = await async_client.post(_cancel_url(booked_link.token))

    # Отмена НЕ откатывается: кандидат уже освободил слот
    assert resp.status_code == 200, resp.text
    await db_session.refresh(booked_link)
    assert booked_link.status == "active"
    assert booked_link.reschedule_count == 1

    # Но неудача удаления записана честно (§0: молча глотать нельзя)
    audits = (await db_session.execute(
        sa_select(AuditLog).where(AuditLog.action == "interview_cancelled")
    )).scalars().all()
    assert len(audits) == 1
    after = (audits[0].changes or {}).get("after", {})
    assert after["b24_event_deleted"] is False
    assert after["b24_delete_error"]

    # И рекрутёр предупреждён в ленте
    events = (await db_session.execute(
        sa_select(Event).where(Event.type == "interview")
    )).scalars().all()
    assert any("удалить не удалось" in (e.text or "") for e in events)


# ──────────────────────────────────────────────────────────────────────────────
# 7. ICS отмены: METHOD:CANCEL + тот же UID
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_sends_ics_cancel_with_same_uid(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """Кандидату уходит ICS с METHOD:CANCEL, STATUS:CANCELLED и ТЕМ ЖЕ UID.

    Совпадение UID принципиально: почтовый клиент снимает уже добавленную встречу,
    а не создаёт вторую. SEQUENCE обязан вырасти, иначе CANCEL игнорируется.
    """
    admin_user.b24_user_id = 42
    await db_session.flush()
    token = booked_link.token

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock),
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock) as mock_send,
    ):
        resp = await async_client.post(_cancel_url(token))
    assert resp.status_code == 200, resp.text

    # Письмо кандидату — первое из отправленных (второе рекрутёру)
    cand_call = next(
        c for c in mock_send.await_args_list
        if c.kwargs.get("to") == "test@example.com"
    )
    ics = cand_call.kwargs["ics"]
    assert ics, "К письму об отмене должен прикладываться ICS"
    assert "METHOD:CANCEL" in ics
    assert "STATUS:CANCELLED" in ics
    assert f"UID:{token}@glafira" in ics, "UID обязан совпадать с исходным приглашением"
    assert "SEQUENCE:1" in ics, "SEQUENCE должен вырасти до нового reschedule_count"

    # И письмо рекрутёру тоже ушло
    assert any(
        c.kwargs.get("to") == admin_user.email for c in mock_send.await_args_list
    ), "Ответственный рекрутёр должен быть уведомлён"


# ──────────────────────────────────────────────────────────────────────────────
# 8. После отмены цикл записи работает заново
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slots_available_again_after_cancel(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """После отмены GET /slots снова отдаёт слоты (до отмены — 410, ссылка booked)."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    # До отмены: ссылка booked → /slots закрыт
    resp_before = await async_client.get(
        f"/api/v1/public/schedule/{booked_link.token}/slots"
    )
    assert resp_before.status_code == 410

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock),
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        assert (await async_client.post(_cancel_url(booked_link.token))).status_code == 200

    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        return_value={"42": []},
    ):
        resp_after = await async_client.get(
            f"/api/v1/public/schedule/{booked_link.token}/slots"
        )

    assert resp_after.status_code == 200, resp_after.text
    assert isinstance(resp_after.json()["slots"], list)


@pytest.mark.asyncio
async def test_rebook_after_cancel_succeeds(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """После отмены кандидат бронирует новое время тем же POST /book (перенос = cancel+book)."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock),
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        assert (await async_client.post(_cancel_url(booked_link.token))).status_code == 200

    new_from = datetime(2026, 8, 11, 9, 0, 0, tzinfo=timezone.utc)  # 12:00 МСК, вт
    new_to = new_from + timedelta(hours=1)

    with (
        patch("app.api.v1.public_schedule.b24_client.get_accessibility",
              new_callable=AsyncMock, return_value={"42": []}),
        patch("app.api.v1.public_schedule.b24_client.add_calendar_event",
              new_callable=AsyncMock, return_value="123"),
        patch("app.api.v1.public_schedule.b24_client.create_videoconference",
              new_callable=AsyncMock, return_value=None),
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            f"/api/v1/public/schedule/{booked_link.token}/book",
            json={"slot_from": new_from.isoformat(), "slot_to": new_to.isoformat()},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "booked"

    await db_session.refresh(booked_link)
    assert booked_link.status == "booked"
    assert booked_link.b24_event_id == "123"
    # Счётчик переносов переживает повторную бронь — иначе лимит можно было бы обнулять
    assert booked_link.reschedule_count == 1


# ──────────────────────────────────────────────────────────────────────────────
# 9. Контракт GET /schedule/{token} для фронта
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_info_exposes_change_fields(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, booked_link
):
    """GET info отдаёт can_change/reschedules_left/change_blocked_reason (контракт фронта)."""
    resp = await async_client.get(f"/api/v1/public/schedule/{booked_link.token}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "booked"
    assert data["reschedule_count"] == 0
    assert data["reschedules_left"] == 2
    assert data["can_change"] is True
    assert data["change_blocked_reason"] is None
    # Публичный роут не раскрывает контакты кандидата
    assert "test@example.com" not in resp.text
    assert "candidate_id" not in data


@pytest.mark.asyncio
async def test_info_blocked_reason_deadline(
    async_client, db_session, admin_user, vacancy_with_team, application, b24_integration
):
    """Встреча через час → can_change=false, причина 'deadline'."""
    slot_from = datetime.now(timezone.utc) + timedelta(hours=1)
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="booked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        slot_from=slot_from,
        slot_to=slot_from + timedelta(hours=1),
        reschedule_count=0,
    )
    db_session.add(link)
    await db_session.flush()

    resp = await async_client.get(f"/api/v1/public/schedule/{link.token}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["can_change"] is False
    assert data["change_blocked_reason"] == "deadline"


@pytest.mark.asyncio
async def test_info_blocked_reason_limit_wins_over_deadline(
    async_client, db_session, admin_user, vacancy_with_team, application, b24_integration
):
    """Лимит проверяется ПЕРВЫМ: при исчерпанном лимите причина 'limit', не 'deadline'."""
    slot_from = datetime.now(timezone.utc) + timedelta(hours=1)  # дедлайн тоже нарушен
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="booked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        slot_from=slot_from,
        slot_to=slot_from + timedelta(hours=1),
        reschedule_count=2,
    )
    db_session.add(link)
    await db_session.flush()

    resp = await async_client.get(f"/api/v1/public/schedule/{link.token}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["change_blocked_reason"] == "limit"
    assert data["reschedules_left"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# 10. Продление срока ссылки при отмене
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_extends_soon_expiring_link(
    async_client, db_session, admin_user, vacancy_with_team, application, b24_integration
):
    """Ссылка протухает через 2 дня → при отмене продлевается, иначе перезапись невозможна."""
    slot_from = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="booked",
        expires_at=soon,
        slot_from=slot_from,
        slot_to=slot_from + timedelta(hours=1),
        b24_event_id="55",
        reschedule_count=0,
    )
    db_session.add(link)
    await db_session.flush()

    with (
        patch("app.api.v1.public_schedule.b24_client.delete_calendar_event",
              new_callable=AsyncMock),
        patch("app.api.v1.public_schedule.send_email", new_callable=AsyncMock),
    ):
        resp = await async_client.post(_cancel_url(link.token))
    assert resp.status_code == 200, resp.text

    await db_session.refresh(link)
    assert link.expires_at > soon + timedelta(days=5), \
        "Ссылка должна быть продлена, иначе отмена — ловушка"
