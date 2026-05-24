import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import uuid

from app.main import app
from app.database import get_db
from app.models import Base, User, Company
from app.config import settings
from app.core.security import get_password_hash


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://glafira:glafira@localhost:5432/glafira_test"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test engine and setup database"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """Get clean database session for each test"""
    TestSessionLocal = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with TestSessionLocal() as session:
        # Create test company
        company = Company(
            id=uuid.UUID(settings.DEFAULT_COMPANY_ID),
            name="Test Company"
        )
        session.add(company)

        # Create test user (Anna Sedova)
        test_user = User(
            company_id=uuid.UUID(settings.DEFAULT_COMPANY_ID),
            email="anna.sedova@example.com",
            password_hash=get_password_hash("Glafira2026!"),
            full_name="Анна Седова",
            role="admin",
            position="Руководитель отдела подбора",
            timezone="Europe/Moscow"
        )
        session.add(test_user)

        await session.commit()

        yield session

        # Rollback transaction to clean data
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(test_engine, db_session):
    """Get async HTTP client with test database override"""
    TestSessionLocal = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with TestSessionLocal() as session:
            yield session

    # Override get_db dependency
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    # Clear overrides
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    """Get authorization headers for Anna Sedova"""
    # Login to get token
    response = await async_client.post("/api/v1/auth/login", json={
        "email": "anna.sedova@example.com",
        "password": "Glafira2026!"
    })

    assert response.status_code == 200
    token_data = response.json()
    access_token = token_data["access_token"]

    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def admin_user(db_session):
    """Get the admin user created in db_session fixture"""
    from app.models import User
    from sqlalchemy import select

    result = await db_session.execute(
        select(User).where(User.email == "anna.sedova@example.com")
    )
    return result.scalar_one()