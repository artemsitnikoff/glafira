"""
Тесты защиты от брутфорса пароля (account lockout через БД).

Покрывают:
- N неудачных попыток подряд → на N+1 аккаунт залочен (429 ACCOUNT_LOCKED)
- Верный пароль во время лока НЕ пускает
- Верный пароль ДО порога сбрасывает счётчик
- После истечения окна (locked_until в прошлом) → пускает и сбрасывает
- Неизвестный email не плодит lockout-строк
- Успешный вход не гейтится биллинг-гейтом (paid_until не выставлен → bypass в тестах)
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User


# ---------------------------------------------------------------------------
# Вспомогательная функция
# ---------------------------------------------------------------------------

async def _try_login(client: AsyncClient, email: str, password: str) -> int:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp.status_code


async def _login_resp(client: AsyncClient, email: str, password: str):
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


# ---------------------------------------------------------------------------
# Тест 1: N неудачных попыток → на N+1 аккаунт залочен (429)
# ---------------------------------------------------------------------------

async def test_lockout_after_max_attempts(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """После LOGIN_MAX_ATTEMPTS неверных паролей следующий запрос → 429."""
    max_attempts = settings.LOGIN_MAX_ATTEMPTS

    for i in range(max_attempts):
        code = await _try_login(async_client, admin_user.email, "wrong_password")
        # Каждая попытка до порога → 401 INVALID_CREDENTIALS
        assert code == 401, f"Попытка {i+1}: ожидали 401, получили {code}"

    # (N+1)-я попытка — аккаунт уже залочен
    resp = await _login_resp(async_client, admin_user.email, "wrong_password")
    assert resp.status_code == 429, f"Ожидали 429 на {max_attempts+1}-й попытке, получили {resp.status_code}"
    body = resp.json()
    assert body["error"]["code"] == "ACCOUNT_LOCKED"
    assert "мин" in body["error"]["message"]  # сообщение содержит оставшееся время


# ---------------------------------------------------------------------------
# Тест 2: Верный пароль во время лока НЕ пускает
# ---------------------------------------------------------------------------

async def test_correct_password_during_lockout_is_rejected(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Залоченный аккаунт отвергает даже верный пароль (429)."""
    max_attempts = settings.LOGIN_MAX_ATTEMPTS

    # Набиваем неудачи до порога
    for _ in range(max_attempts):
        await _try_login(async_client, admin_user.email, "wrong")

    # Теперь верный пароль — должен получить 429
    resp = await _login_resp(async_client, admin_user.email, "Glafira2026!")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "ACCOUNT_LOCKED"


# ---------------------------------------------------------------------------
# Тест 3: Верный пароль ДО порога сбрасывает счётчик
# ---------------------------------------------------------------------------

async def test_successful_login_resets_counter(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Успешный вход до достижения порога сбрасывает failed_login_attempts."""
    max_attempts = settings.LOGIN_MAX_ATTEMPTS

    # Несколько неудачных попыток (меньше порога)
    partial = max_attempts - 2
    for _ in range(partial):
        await _try_login(async_client, admin_user.email, "wrong")

    # Проверяем что счётчик вырос
    await db_session.refresh(admin_user)
    assert admin_user.failed_login_attempts == partial

    # Успешный вход
    resp = await _login_resp(async_client, admin_user.email, "Glafira2026!")
    assert resp.status_code == 200, resp.text

    # Счётчик сброшен
    await db_session.refresh(admin_user)
    assert admin_user.failed_login_attempts == 0
    assert admin_user.locked_until is None


# ---------------------------------------------------------------------------
# Тест 4: После истечения окна → пускает и сбрасывает
# ---------------------------------------------------------------------------

async def test_login_after_lockout_expiry(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """После истечения locked_until успешный вход проходит и сбрасывает поля."""
    # Выставляем locked_until в прошлое напрямую (эмуляция истекшего окна)
    admin_user.failed_login_attempts = settings.LOGIN_MAX_ATTEMPTS
    admin_user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.add(admin_user)
    await db_session.commit()

    # Попытка с верным паролем — должна пройти
    resp = await _login_resp(async_client, admin_user.email, "Glafira2026!")
    assert resp.status_code == 200, f"Ожидали 200 после истечения окна, получили {resp.status_code}: {resp.text}"
    assert "access_token" in resp.json()

    # Поля сброшены
    await db_session.refresh(admin_user)
    assert admin_user.failed_login_attempts == 0
    assert admin_user.locked_until is None


# ---------------------------------------------------------------------------
# Тест 5: Неизвестный email не плодит lockout-строк (anti-enumeration)
# ---------------------------------------------------------------------------

async def test_unknown_email_does_not_create_lockout(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Попытки входа с несуществующим email не должны создавать записи lockout."""
    max_attempts = settings.LOGIN_MAX_ATTEMPTS

    for _ in range(max_attempts + 1):
        resp = await _login_resp(async_client, "nobody@unknown.example", "any_pass")
        # Всегда 401 — не 429
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # admin_user не затронут
    await db_session.refresh(admin_user)
    assert admin_user.failed_login_attempts == 0
    assert admin_user.locked_until is None


# ---------------------------------------------------------------------------
# Тест 6: 429 содержит оставшееся время в минутах
# ---------------------------------------------------------------------------

async def test_lockout_message_contains_minutes(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Сообщение об ошибке при lockout содержит время до разблокировки."""
    max_attempts = settings.LOGIN_MAX_ATTEMPTS
    for _ in range(max_attempts):
        await _try_login(async_client, admin_user.email, "wrong")

    resp = await _login_resp(async_client, admin_user.email, "wrong")
    assert resp.status_code == 429
    message = resp.json()["error"]["message"]
    # Должно содержать число минут
    assert any(char.isdigit() for char in message), f"В сообщении нет числа: {message!r}"


# ---------------------------------------------------------------------------
# Тест 7: Успешный вход после частичных неудач + один успешный → счётчик 0
#         затем снова неудачи → порог счится с 0 (не с предыдущего значения)
# ---------------------------------------------------------------------------

async def test_counter_resets_fully_after_success(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Счётчик после успешного входа сбрасывается в 0 и новые попытки считаются заново."""
    max_attempts = settings.LOGIN_MAX_ATTEMPTS
    partial = max_attempts - 1

    # Частичные неудачи
    for _ in range(partial):
        await _try_login(async_client, admin_user.email, "wrong")

    # Успешный вход — сбрасываем
    resp = await _login_resp(async_client, admin_user.email, "Glafira2026!")
    assert resp.status_code == 200

    # Снова partial неудачи — не должны блокировать (счётчик начался с 0)
    for _ in range(partial):
        code = await _try_login(async_client, admin_user.email, "wrong")
        assert code == 401, f"После сброса ожидали 401, получили {code}"

    # partial < max_attempts → аккаунт НЕ залочен, верный пароль проходит
    resp2 = await _login_resp(async_client, admin_user.email, "Glafira2026!")
    assert resp2.status_code == 200
