import json
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings


def _json_serializer(value):
    # default=str — чтобы UUID/Decimal/datetime в любой JSONB-колонке не роняли commit
    # дефолтным json.dumps (иначе сбой записи можно «проглотить» → вечный running).
    return json.dumps(value, default=str)


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=10,  # Быстрый fail при исчерпании пула
    json_serializer=_json_serializer,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session