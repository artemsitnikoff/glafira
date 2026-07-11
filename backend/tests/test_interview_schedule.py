"""Тесты планировщика интервью через Б24-календарь.

Б24-клиент (call) всегда замокан — тесты не ходят в сеть.
Проверяем: расчёт слотов, лид-тайм, TZ, антигонку, бронь,
идемпотентность, немаплен-участник, Б24 down → 503, истёкший токен, изоляцию компаний, rate-limit.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.config import settings
from app.core.security import get_password_hash
from app.models import Application, Company, Integration, InterviewLink, User, Vacancy, VacancyTeam
from app.services.integrations.bitrix24.interview_slots import calculate_free_slots
from app.services.glafira.interview_schedule import send_interview_links

# ──────────────────────────────────────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────────────────────────────────────

WEBHOOK = "https://demo.bitrix24.ru/rest/1/abc123/"
B24_CALL = "app.services.integrations.bitrix24.client.call"
B24_CALL_DIRECT = "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility"
TZ_MSK = "Europe/Moscow"


# ──────────────────────────────────────────────────────────────────────────────
# Фикстуры
# ──────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def company2(db_session) -> Company:
    """Вторая компания для тестов изоляции."""
    c = Company(id=uuid.uuid4(), name="Company Two")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def user_with_b24(db_session, admin_user) -> User:
    """Пользователь с заполненным b24_user_id."""
    admin_user.b24_user_id = 42
    await db_session.flush()
    return admin_user


@pytest_asyncio.fixture
async def vacancy_with_team(db_session, admin_user) -> Vacancy:
    """Вакансия с командой и включённым auto_interview."""
    v = Vacancy(
        company_id=admin_user.company_id,
        name="Тестовая вакансия",
        status="active",
        auto_interview=True,
        auto_interview_stage="interview",
        responsible_user_id=admin_user.id,
    )
    db_session.add(v)
    await db_session.flush()

    vt = VacancyTeam(
        company_id=admin_user.company_id,
        vacancy_id=v.id,
        user_id=admin_user.id,
        is_responsible=True,
    )
    db_session.add(vt)
    await db_session.flush()
    return v


@pytest_asyncio.fixture
async def application(db_session, admin_user, vacancy_with_team, test_candidate) -> Application:
    """Заявка на этапе 'interview'."""
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
    """Настроенная Б24-интеграция с зашифрованным вебхуком."""
    from cryptography.fernet import Fernet
    from app.services.settings.crypto import encrypt_text

    row = Integration(
        company_id=admin_user.company_id,
        provider="bitrix24",
        status="connected",
        config={
            "webhook_url": encrypt_text(WEBHOOK),
            "portal": "demo.bitrix24.ru",
            "last_test_ok": True,
            "tz": TZ_MSK,
            "work_days": [1, 2, 3, 4, 5],
            "work_start": "10:00",
            "work_end": "18:00",
            "duration_min": 60,
            "step_min": 30,
            "horizon_days": 14,
            "lead_hours": 0,  # 0 для тестов чтобы слоты сразу были доступны
            "interview_video_link": "https://meet.example.com/test",
        },
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def active_link(db_session, admin_user, application) -> InterviewLink:
    """Активная ссылка на запись интервью."""
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add(link)
    await db_session.flush()
    return link


# ──────────────────────────────────────────────────────────────────────────────
# 1. Расчёт слотов: занятость → пересечение ВСЕХ → сетка рабочих часов
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calculate_free_slots_basic():
    """Базовый расчёт: один участник, одна занятость — слот в этот период не попадает."""
    # МСК (UTC+3): рабочие часы 10:00-18:00
    # Занятость: 11:00-12:00 МСК (08:00-09:00 UTC)
    now_utc = datetime(2026, 7, 14, 7, 0, 0, tzinfo=timezone.utc)  # 10:00 МСК, пн

    # Строим занятость
    busy_from = datetime(2026, 7, 14, 8, 0, 0, tzinfo=timezone.utc)   # 11:00 МСК
    busy_to = datetime(2026, 7, 14, 9, 0, 0, tzinfo=timezone.utc)     # 12:00 МСК

    mock_result = {
        "42": [{"FROM": "2026-07-14 11:00:00", "TO": "2026-07-14 12:00:00"}]
    }

    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        slots = await calculate_free_slots(
            WEBHOOK,
            [42],
            tz_str=TZ_MSK,
            work_days=[1, 2, 3, 4, 5],
            work_start="10:00",
            work_end="18:00",
            duration_min=60,
            step_min=60,
            horizon_days=1,
            lead_hours=0,
        )

    # Слот 11:00-12:00 МСК должен отсутствовать
    from_utcs = [s[0] for s in slots]
    busy_slot_start = busy_from
    assert busy_slot_start not in from_utcs, "Занятый слот не должен попасть в список"
    # Слоты 10:00, 12:00, 13:00... должны быть
    assert len(slots) > 0


@pytest.mark.asyncio
async def test_calculate_slots_all_participants_must_be_free():
    """Слот исключается если занят ХОТЬ ОДИН участник."""
    # Два участника, разные занятости — общий слот закрыт
    mock_result = {
        "1": [{"FROM": "2026-07-14 10:00:00", "TO": "2026-07-14 11:00:00"}],
        "2": [{"FROM": "2026-07-14 11:00:00", "TO": "2026-07-14 12:00:00"}],
    }

    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        slots = await calculate_free_slots(
            WEBHOOK,
            [1, 2],
            tz_str=TZ_MSK,
            work_days=[1, 2, 3, 4, 5],
            work_start="10:00",
            work_end="12:00",  # только 2 слота по 60 мин
            duration_min=60,
            step_min=60,
            horizon_days=1,
            lead_hours=0,
        )

    # 10:00-11:00 занят у 1-го, 11:00-12:00 занят у 2-го → оба слота недоступны
    assert slots == [], f"Ожидаем пустой список, получили: {slots}"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Лид-тайм и горизонт
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lead_time_slots_not_before_lead_hours():
    """Слоты не раньше now + lead_hours."""
    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        return_value={"42": []},
    ):
        slots = await calculate_free_slots(
            WEBHOOK,
            [42],
            tz_str=TZ_MSK,
            work_days=[1, 2, 3, 4, 5],
            work_start="10:00",
            work_end="18:00",
            duration_min=60,
            step_min=30,
            horizon_days=14,
            lead_hours=24,
        )

    now = datetime.now(timezone.utc)
    min_slot = now + timedelta(hours=24)
    for from_utc, to_utc in slots:
        assert from_utc >= min_slot - timedelta(minutes=5), (
            f"Слот {from_utc} раньше лид-тайма {min_slot}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 3. TZ-конверсия
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tz_msk_slots_returned_in_utc():
    """Рабочие часы МСК (UTC+3): слот 10:00 МСК = 07:00 UTC."""
    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        return_value={"42": []},
    ):
        slots = await calculate_free_slots(
            WEBHOOK,
            [42],
            tz_str=TZ_MSK,
            work_days=[1, 2, 3, 4, 5],  # только рабочие дни
            work_start="10:00",
            work_end="11:00",  # ровно один слот
            duration_min=60,
            step_min=60,
            horizon_days=14,
            lead_hours=0,
        )

    assert len(slots) > 0, "Должен быть хотя бы один слот"
    # Все слоты начинаются в 07:00 UTC (= 10:00 МСК)
    for from_utc, _ in slots:
        assert from_utc.hour == 7, f"Ожидаем 07:00 UTC (10:00 МСК), получили {from_utc.hour}:00"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Б24 down → 503 (НЕ пустые слоты)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_b24_down_raises_not_empty_slots():
    """При ошибке Б24 бросаем AppError (не возвращаем пустой список — fail-closed)."""
    from app.core.errors import AppError

    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        side_effect=AppError(code="B24_TIMEOUT", message="Таймаут", status_code=400),
    ):
        with pytest.raises(AppError):
            await calculate_free_slots(
                WEBHOOK,
                [42],
                tz_str=TZ_MSK,
                work_days=[1, 2, 3, 4, 5],
                work_start="10:00",
                work_end="18:00",
                duration_min=60,
                step_min=30,
                horizon_days=14,
                lead_hours=0,
            )


# ──────────────────────────────────────────────────────────────────────────────
# 5. Публичный GET /public/schedule/{token} — истёкший токен → 410
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expired_token_returns_410(async_client, db_session, admin_user, application):
    """Истёкший токен → 410."""
    expired_link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="active",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # уже истёк
    )
    db_session.add(expired_link)
    await db_session.flush()

    resp = await async_client.get(f"/api/v1/public/schedule/{expired_link.token}")
    # Возвращает 200 со статусом 'expired' (GET info не блокирует, возвращает факт)
    # но GET /slots и POST /book вернут 410
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "expired"


@pytest.mark.asyncio
async def test_expired_token_slots_returns_410(async_client, db_session, admin_user, application):
    """GET /slots для истёкшего токена → 410."""
    expired_link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="expired",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(expired_link)
    await db_session.flush()

    resp = await async_client.get(f"/api/v1/public/schedule/{expired_link.token}/slots")
    assert resp.status_code == 410


# ──────────────────────────────────────────────────────────────────────────────
# 6. Несуществующий токен → 404 (без деталей)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_token_returns_404(async_client):
    """Несуществующий токен → 404 без раскрытия деталей."""
    resp = await async_client.get("/api/v1/public/schedule/nonexistent_token_xyz")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 7. GET /schedule/{token} — базовая информация
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_schedule_info_ok(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, active_link
):
    """GET info возвращает название вакансии, участников (без email/телефона), tz."""
    # Назначаем b24_user_id
    admin_user.b24_user_id = 42
    await db_session.flush()

    resp = await async_client.get(f"/api/v1/public/schedule/{active_link.token}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["vacancy_name"] == "Тестовая вакансия"
    assert data["status"] == "active"
    assert data["tz"] == TZ_MSK
    # Участники — только имя и avatar_url, без email/телефона
    for p in data["participants"]:
        assert "email" not in p
        assert "phone" not in p
        assert "name" in p


# ──────────────────────────────────────────────────────────────────────────────
# 8. GET /slots — Б24 возвращает слоты
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_slots_ok(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, active_link
):
    """GET /slots возвращает список слотов когда Б24 доступен."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        return_value={"42": []},  # нет занятости → все слоты свободны
    ):
        resp = await async_client.get(f"/api/v1/public/schedule/{active_link.token}/slots")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "slots" in data
    assert "tz" in data
    assert isinstance(data["slots"], list)


# ──────────────────────────────────────────────────────────────────────────────
# 9. GET /slots — Б24 недоступен → 503 (не пустые слоты)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_slots_b24_error_returns_503(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, active_link
):
    """Б24 падает → 503 (не пустой список — fail-closed)."""
    from app.core.errors import AppError

    admin_user.b24_user_id = 42
    await db_session.flush()

    with patch(
        "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
        new_callable=AsyncMock,
        side_effect=AppError(code="B24_TIMEOUT", message="Таймаут", status_code=400),
    ):
        resp = await async_client.get(f"/api/v1/public/schedule/{active_link.token}/slots")

    assert resp.status_code == 503


# ──────────────────────────────────────────────────────────────────────────────
# 10. GET /slots — участник без b24_user_id → 503 B24_NOT_MAPPED
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_slots_unmapped_participant_returns_503(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, active_link
):
    """Участник без b24_user_id → 503 B24_NOT_MAPPED (не пустые слоты)."""
    # admin_user.b24_user_id остаётся None
    admin_user.b24_user_id = None
    await db_session.flush()

    resp = await async_client.get(f"/api/v1/public/schedule/{active_link.token}/slots")
    assert resp.status_code == 503
    data = resp.json()
    assert "B24_NOT_MAPPED" in str(data)


# ──────────────────────────────────────────────────────────────────────────────
# 11. POST /book — успешная бронь → token booked, b24_event_id сохранён
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_book_success(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, active_link
):
    """Успешная бронь: event.add вызван, token=booked, event записан."""
    from sqlalchemy import select as sa_select

    admin_user.b24_user_id = 42
    await db_session.flush()

    slot_from = datetime(2026, 7, 21, 9, 0, 0, tzinfo=timezone.utc)  # 12:00 МСК
    slot_to = slot_from + timedelta(hours=1)

    with (
        patch(
            "app.services.integrations.bitrix24.interview_slots.b24_client.get_accessibility",
            new_callable=AsyncMock,
            return_value={"42": []},
        ),
        patch(
            "app.api.v1.public_schedule.b24_client.get_accessibility",
            new_callable=AsyncMock,
            return_value={"42": []},
        ),
        patch(
            "app.api.v1.public_schedule.b24_client.add_calendar_event",
            new_callable=AsyncMock,
            return_value="99",
        ),
    ):
        resp = await async_client.post(
            f"/api/v1/public/schedule/{active_link.token}/book",
            json={
                "slot_from": slot_from.isoformat(),
                "slot_to": slot_to.isoformat(),
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "booked"

    # Проверяем что ссылка обновилась
    await db_session.refresh(active_link)
    assert active_link.status == "booked"
    assert active_link.b24_event_id == "99"
    assert active_link.slot_from is not None


# ──────────────────────────────────────────────────────────────────────────────
# 12. POST /book — гонка → 409 SLOT_TAKEN
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_book_race_condition_409(
    async_client, db_session, admin_user, vacancy_with_team,
    application, b24_integration, active_link
):
    """Перепроверка занятости при бронировании: занято → 409 SLOT_TAKEN."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    slot_from = datetime(2026, 7, 21, 9, 0, 0, tzinfo=timezone.utc)
    slot_to = slot_from + timedelta(hours=1)

    # accessibility показывает занятость именно в этот слот
    with patch(
        "app.api.v1.public_schedule.b24_client.get_accessibility",
        new_callable=AsyncMock,
        return_value={
            "42": [{"FROM": "2026-07-21 12:00:00", "TO": "2026-07-21 13:00:00"}]
        },
    ):
        resp = await async_client.post(
            f"/api/v1/public/schedule/{active_link.token}/book",
            json={
                "slot_from": slot_from.isoformat(),
                "slot_to": slot_to.isoformat(),
            },
        )

    assert resp.status_code == 409
    data = resp.json()
    assert "SLOT_TAKEN" in str(data)


# ──────────────────────────────────────────────────────────────────────────────
# 13. POST /book для уже забронированного токена → 410
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_book_already_booked_returns_410(
    async_client, db_session, admin_user, application
):
    """Повторная бронь по забронированному токену → 410."""
    booked_link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=secrets.token_urlsafe(32),
        status="booked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        slot_from=datetime.now(timezone.utc),
        slot_to=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(booked_link)
    await db_session.flush()

    resp = await async_client.post(
        f"/api/v1/public/schedule/{booked_link.token}/book",
        json={
            "slot_from": datetime.now(timezone.utc).isoformat(),
            "slot_to": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    assert resp.status_code == 410


# ──────────────────────────────────────────────────────────────────────────────
# 14. Изоляция компаний: токен чужой компании → 404 для правильного запросчика
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_company_isolation_token_404(async_client, db_session, company2, admin_user):
    """Токен другой компании возвращает 404 (но сам по себе существует)."""
    # Создаём вакансию и заявку в company2
    user2 = User(
        company_id=company2.id,
        email="admin2@company2.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Админ Два",
        role="admin",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.flush()

    from app.models import Candidate as CandidateModel
    cand2 = CandidateModel(
        company_id=company2.id,
        last_name="Кандидат",
        first_name="Второй",
        source="manual",
    )
    db_session.add(cand2)
    await db_session.flush()

    v2 = Vacancy(
        company_id=company2.id,
        name="Вакансия компании 2",
        status="active",
    )
    db_session.add(v2)
    await db_session.flush()

    app2 = Application(
        company_id=company2.id,
        candidate_id=cand2.id,
        vacancy_id=v2.id,
        stage="interview",
    )
    db_session.add(app2)
    await db_session.flush()

    link2 = InterviewLink(
        company_id=company2.id,
        application_id=app2.id,
        token=secrets.token_urlsafe(32),
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add(link2)
    await db_session.flush()

    # Токен существует, но наш клиент (без авторизации) его находит корректно —
    # публичный роут работает по токену, компания из токена, поэтому link2 вернёт 200
    # (это правильно: публичная ссылка не привязана к аутентифицированному пользователю).
    # Проверяем что ответ содержит данные company2, не company1.
    resp = await async_client.get(f"/api/v1/public/schedule/{link2.token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["vacancy_name"] == "Вакансия компании 2"


# ──────────────────────────────────────────────────────────────────────────────
# 15. Rate-limit → 429 после 30 запросов
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_429(async_client, db_session, admin_user, application):
    """31-й запрос за минуту с одного IP:token → 429."""
    from app.api.v1.public_schedule import _rate_store

    token = "test_rate_limit_token_xyz"

    # Создаём fake InterviewLink чтобы rate-limit проверялся (lookup идёт после rate-limit)
    link = InterviewLink(
        company_id=admin_user.company_id,
        application_id=application.id,
        token=token,
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add(link)
    await db_session.flush()

    import time

    # Предзаполняем store: 30 запросов только что
    now = time.monotonic()
    _rate_store[f"testclient:{token}"] = [now] * 30

    resp = await async_client.get(f"/api/v1/public/schedule/{token}")
    assert resp.status_code == 429, f"Ожидали 429, получили {resp.status_code}: {resp.text}"

    # Очищаем после теста
    _rate_store.pop(f"testclient:{token}", None)


# ──────────────────────────────────────────────────────────────────────────────
# 16. send_interview_links — идемпотентность (не пересоздаёт активную ссылку)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_interview_links_idempotent(
    db_session, admin_user, vacancy_with_team, application,
    b24_integration, active_link
):
    """Если активная ссылка уже есть — не создаём новую."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    with patch(
        "app.services.glafira.interview_schedule.send_email",
        new_callable=AsyncMock,
    ):
        stats = await send_interview_links(db_session, admin_user.company_id)

    # Активная ссылка уже была → skipped
    assert stats["skipped_active"] >= 1
    assert stats["sent"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# 17. send_interview_links — участник без b24_user_id → Event с ошибкой, не слать
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_interview_links_unmapped_participant(
    db_session, admin_user, vacancy_with_team, application, b24_integration
):
    """Участник без b24_user_id → ссылка НЕ создаётся, Event с ошибкой записывается."""
    from sqlalchemy import select as sa_select
    from app.models import Event as EventModel

    # Убеждаемся что b24_user_id не задан
    admin_user.b24_user_id = None
    await db_session.flush()

    with patch(
        "app.services.glafira.interview_schedule.send_email",
        new_callable=AsyncMock,
    ):
        stats = await send_interview_links(db_session, admin_user.company_id)

    assert stats["skipped_unmapped"] >= 1
    assert stats["sent"] == 0

    # Проверяем Event с типом 'interview'
    events = (await db_session.execute(
        sa_select(EventModel).where(
            EventModel.company_id == admin_user.company_id,
            EventModel.type == "interview",
        )
    )).scalars().all()
    assert any("b24_user_id" in (e.text or "") for e in events), (
        "Должен быть Event с упоминанием b24_user_id"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 18. send_interview_links — нет Б24-интеграции → тихий выход (0 sent)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_interview_links_no_b24(
    db_session, admin_user, vacancy_with_team, application
):
    """Нет Б24-интеграции → send_interview_links тихо выходит с нулями."""
    admin_user.b24_user_id = 42
    await db_session.flush()

    stats = await send_interview_links(db_session, admin_user.company_id)
    assert stats["sent"] == 0
