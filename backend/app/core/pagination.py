from fastapi import Query
from dataclasses import dataclass
from typing import Generic, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from math import ceil

from ..schemas.base import Paginated

T = TypeVar('T')


@dataclass
class PageParams:
    page: int = Query(1, ge=1)
    page_size: int = Query(24, ge=1, le=100)
    sort: str | None = Query(None)
    order: str = Query("desc", pattern="^(asc|desc)$")


async def apply_pagination(
    session: AsyncSession,
    query,
    page_params: PageParams,
    schema_cls: type[T]
) -> Paginated[T]:
    """Apply pagination to SQLAlchemy query"""
    # Count total
    count_query = select(func.count()).select_from(query.alias())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Apply limit/offset
    offset = (page_params.page - 1) * page_params.page_size
    items_query = query.limit(page_params.page_size).offset(offset)

    result = await session.execute(items_query)
    items = result.fetchall()

    # Convert to Pydantic schemas
    items_data = [schema_cls.model_validate(item) for item in items]

    pages = ceil(total / page_params.page_size) if total > 0 else 1

    return Paginated[T](
        items=items_data,
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
        pages=pages
    )