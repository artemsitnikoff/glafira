import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.security import get_password_hash
from app.database import get_db
from app.main import app
from app.models import Base, Company, User, Candidate, Consent, Vacancy
from datetime import datetime, timezone

# Тестовая БД — ОТДЕЛЬНАЯ от прод (conftest делает drop_all/create_all!).
# Приоритет: env TEST_DATABASE_URL → деривация из реального DATABASE_URL (хост `db`,
# прод-креды) с заменой имени БД на «<prod>_test». Хардкод localhost больше не нужен —
# из-за него тесты не шли в контейнере (Postgres там на хосте `db`, не на localhost).
_env_test_url = os.getenv("TEST_DATABASE_URL")
if _env_test_url:
    TEST_DATABASE_URL = _env_test_url
else:
    _base_url = make_url(settings.DATABASE_URL)
    _test_url = _base_url.set(database=(_base_url.database or "glafira") + "_test")
    # render_as_string(hide_password=False): str(URL) маскирует пароль как '***' →
    # иначе asyncpg получит '***' и упадёт InvalidPasswordError.
    TEST_DATABASE_URL = _test_url.render_as_string(hide_password=False)


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        # pgvector нужен для модели candidate_embeddings (Vector(384)) — иначе create_all
        # упадёт на DDL `vector(384)`. Требует образ pgvector/pgvector:pg16 (как на проде).
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.connect() as connection:
        trans = await connection.begin()
        Session = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        session = Session()
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    company = Company(id=uuid.UUID(settings.DEFAULT_COMPANY_ID), name="Test Company")
    db_session.add(company)
    await db_session.flush()

    user = User(
        company_id=company.id,
        email="anna.sedova@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Анна Седова",
        role="admin",
        position="Старший рекрутёр",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession, admin_user: User) -> User:
    """Менеджер для тестов RBAC (общий в conftest; локальный в test_rbac.py имеет приоритет
    в своих тестах). Отдельный email во избежание коллизии."""
    user = User(
        company_id=admin_user.company_id,
        email="manager.shared@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Менеджер Общий",
        role="manager",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_company(db_session: AsyncSession, admin_user: User) -> Company:
    """Компания тест-окружения (создаётся фикстурой admin_user)."""
    return await db_session.get(Company, admin_user.company_id)


@pytest_asyncio.fixture
async def test_vacancy(db_session: AsyncSession, admin_user: User) -> Vacancy:
    """Одна активная вакансия компании (без hh_vacancy_id — для тестов Умного подбора)."""
    vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Python-разработчик",
        city="Москва",
        salary_from=150000,
        salary_to=250000,
        status="active",
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession, admin_user: User) -> User:
    user = User(
        company_id=admin_user.company_id,
        email="regular@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Обычный Пользователь",
        role="recruiter",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession, admin_user: User) -> User:
    user = User(
        company_id=admin_user.company_id,
        email="inactive@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Неактивный Пользователь",
        role="recruiter",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, admin_user: User) -> dict[str, str]:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_candidate(db_session: AsyncSession, admin_user: User) -> Candidate:
    """Create test candidate"""
    candidate = Candidate(
        company_id=admin_user.company_id,
        last_name="Тестов",
        first_name="Тест",
        source="manual",
        phone="+7 900 123 45 67",
        email="test@example.com",
        city="Москва"
    )
    db_session.add(candidate)
    await db_session.commit()
    await db_session.refresh(candidate)
    return candidate


@pytest_asyncio.fixture
async def signed_consent(db_session: AsyncSession, test_candidate: Candidate) -> Consent:
    """Create signed consent for test candidate"""
    now = datetime.now(timezone.utc)
    consent = Consent(
        company_id=test_candidate.company_id,
        candidate_id=test_candidate.id,
        number="PD-TEST/26",
        status="signed",
        channel="telegram",
        requested_at=now,
        signed_at=now
    )
    db_session.add(consent)
    await db_session.commit()
    await db_session.refresh(consent)
    return consent


@pytest_asyncio.fixture
async def admin_token(async_client: AsyncClient, admin_user: User) -> str:
    """Токен авторизации админа для тестов"""
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Glafira2026!"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest_asyncio.fixture
def default_company_id(admin_user: User) -> str:
    """ID компании тест-админа как строка"""
    return str(admin_user.company_id)


@pytest_asyncio.fixture
async def second_company(db_session: AsyncSession, admin_user: User) -> Company:
    """Вторая компания (для тестов изоляции per-company ключей и т.п.)."""
    company = Company(id=uuid.uuid4(), name="Second Test Company")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    return company


@pytest_asyncio.fixture
async def other_company(db_session: AsyncSession, admin_user: User) -> Company:
    """Ещё одна компания (alias-семантика для тестов изоляции, отдельная запись)."""
    company = Company(id=uuid.uuid4(), name="Other Test Company")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    return company


@pytest_asyncio.fixture
async def admin_headers(auth_headers: dict[str, str]) -> dict[str, str]:
    """Алиас auth_headers (часть тестов ждёт имя admin_headers)."""
    return auth_headers


@pytest_asyncio.fixture
async def manager_headers(async_client: AsyncClient, manager_user: User) -> dict[str, str]:
    """Заголовки авторизации менеджера (для RBAC-тестов)."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": manager_user.email, "password": "Glafira2026!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# === Per-company OpenRouter ключ: дефолт для тестов =========================
# LLM-функции теперь резолвят ключ компании через get_company_openrouter_key
# ДО вызова call_json. Большинство тестов мокают call_json и НЕ задают ключ —
# без дефолта они бы падали на OpenRouterNotConfiguredError. Эта autouse-фикстура
# подменяет резолвер во ВСЕХ сервис-модулях на фиктивный ключ. Тесты, проверяющие
# сам резолв/эндпоинт ключа, помечают себя @pytest.mark.real_openrouter_key и
# получают настоящее поведение.
_OPENROUTER_KEY_SITES = (
    "app.services.glafira.scoring.get_company_openrouter_key",
    "app.services.smart_search.get_company_openrouter_key",
    "app.services.base_search.get_company_openrouter_key",
    "app.services.glafira.screening.get_company_openrouter_key",
    "app.services.glafira.auto_qa.get_company_openrouter_key",
    "app.services.glafira.resume_gen.get_company_openrouter_key",
    "app.services.glafira.employee_summary.get_company_openrouter_key",
    "app.services.glafira.resume_parse.get_company_openrouter_key",
    "app.api.v1.candidates.get_company_openrouter_key",
    # source-модуль покрывает локальные импорты (pulse/plan.py) — резолв в рантайме
    "app.services.settings.glafira.get_company_openrouter_key",
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_openrouter_key: тест проверяет реальный резолв ключа компании (без авто-дефолта conftest)",
    )
    config.addinivalue_line(
        "markers",
        "billing_gate: тест проверяет реальный billing-гейт (без авто-обхода conftest)",
    )


@pytest.fixture(autouse=True)
def _default_company_openrouter_key(request, monkeypatch):
    if request.node.get_closest_marker("real_openrouter_key"):
        return
    for site in _OPENROUTER_KEY_SITES:
        monkeypatch.setattr(site, AsyncMock(return_value="test-openrouter-key"), raising=False)


@pytest.fixture(autouse=True)
def _bypass_billing_gate(request, monkeypatch):
    """Billing-гейт по умолчанию ОТКЛЮЧЁН в тестах: тест-компании создаются без paid_until,
    иначе ВСЕ аутентифицированные запросы ловили бы 402 SUBSCRIPTION_EXPIRED. Тесты самого
    гейта помечают @pytest.mark.billing_gate и идут против реальной проверки."""
    if request.node.get_closest_marker("billing_gate"):
        return
    monkeypatch.setattr("app.deps.company_subscription_active", lambda company: True, raising=True)
