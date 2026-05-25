"""Схемы для Analytics домена"""

from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field


class TableColumn(BaseModel):
    key: str
    label: str
    type: Literal["text", "mono", "delta", "badge"] = "text"
    sortable: bool = True


class TableData(BaseModel):
    title: str
    columns: list[TableColumn]
    rows: list[dict]


class ChartData(BaseModel):
    type: str  # line|bar|hbar|funnel|boxplot|heatmap|pie|scatter|radar|survival|cohort|stacked
    title: str
    data: dict


class KpiCard(BaseModel):
    key: str
    value: float | None = None
    unit: str | None = None
    delta: float | None = None
    delta_dir: str = "flat"
    caption: str | None = None


class AnalyticsResponse(BaseModel):
    report: str
    period: str
    kpis: list[KpiCard] | None = None
    charts: list[ChartData] = Field(default_factory=list)
    tables: list[TableData] = Field(default_factory=list)