"""API эндпойнты для аналитики"""

import io
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...deps import get_current_company_id
from ...schemas.analytics import AnalyticsResponse
from ...services.analytics.common import AnalyticsFilters
from ...services.analytics.overview import build_overview
from ...services.analytics.speed import build_speed
from ...services.analytics.funnel import build_funnel
from ...services.analytics.sources import build_sources
from ...services.analytics.rejections import build_rejections
from ...services.analytics.turnover import build_turnover
from ...services.analytics.recruiters import build_recruiters
from ...services.analytics.export import build_xlsx

router = APIRouter()


def _build_filters(
    period: str = Query("month"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    vacancy_ids: list[UUID] = Query(default_factory=list),
    recruiter_ids: list[UUID] = Query(default_factory=list),
    compare: bool = Query(True),
) -> AnalyticsFilters:
    """Строит AnalyticsFilters из query параметров"""
    return AnalyticsFilters(period, date_from, date_to, vacancy_ids, recruiter_ids, compare)


@router.get("/overview", response_model=AnalyticsResponse)
async def get_overview(
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отчёт Overview"""
    return await build_overview(session, filters, company_id)


@router.get("/speed", response_model=AnalyticsResponse)
async def get_speed(
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отчёт Speed"""
    return await build_speed(session, filters, company_id)


@router.get("/funnel", response_model=AnalyticsResponse)
async def get_funnel(
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отчёт Funnel"""
    return await build_funnel(session, filters, company_id)


@router.get("/sources", response_model=AnalyticsResponse)
async def get_sources(
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отчёт Sources"""
    return await build_sources(session, filters, company_id)


@router.get("/rejections", response_model=AnalyticsResponse)
async def get_rejections(
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отчёт Rejections"""
    return await build_rejections(session, filters, company_id)


@router.get("/turnover", response_model=AnalyticsResponse)
async def get_turnover(
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отчёт Turnover"""
    return await build_turnover(session, filters, company_id)


@router.get("/recruiters", response_model=AnalyticsResponse)
async def get_recruiters(
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отчёт Recruiters"""
    return await build_recruiters(session, filters, company_id)


@router.get("/export")
async def export_report(
    report: str = Query(..., pattern="^(overview|speed|funnel|sources|rejections|turnover|recruiters)$"),
    format: str = Query("xlsx", pattern="^xlsx$"),
    filters: AnalyticsFilters = Depends(_build_filters),
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Экспорт отчёта в XLSX"""
    # Роутинг к нужному сервису
    builders = {
        "overview": build_overview,
        "speed": build_speed,
        "funnel": build_funnel,
        "sources": build_sources,
        "rejections": build_rejections,
        "turnover": build_turnover,
        "recruiters": build_recruiters,
    }

    response = await builders[report](session, filters, company_id)
    data = build_xlsx(report, response)

    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="analytics_{report}.xlsx"'},
    )