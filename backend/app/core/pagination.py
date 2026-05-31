from fastapi import Query
from dataclasses import dataclass


@dataclass
class PageParams:
    page: int = Query(1, ge=1)
    page_size: int = Query(24, ge=1, le=100)
    sort: str | None = Query(None)
    order: str = Query("desc", pattern="^(asc|desc)$")


