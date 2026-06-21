"""API эндпойнты для главной страницы"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from uuid import UUID

from ...deps import get_current_user, get_current_company_id
from ...database import get_db
from ...schemas.home import HomeKpi, AttentionItem, EventOut, PulseSummary, SourceItem, HomeDialogOut
from ...services.home.kpi import compute_home_kpi
from ...services.home.attention import compute_attention
from ...services.home.events import list_recent_events
from ...services.home.pulse_summary import compute_pulse_summary
from ...services.home.sources import top_sources
from ...services.home.dialogs import list_recent_dialogs

router = APIRouter()


@router.get("/kpi", response_model=HomeKpi)
async def get_kpi(
    period: str = Query(default="month", description="Период: week, month, quarter, year, all"),
    extended: bool = Query(default=False, description="Включить расширенные метрики"),
    session=Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user=Depends(get_current_user)
):
    """Получить KPI для главной страницы"""
    return await compute_home_kpi(session, company_id, period, extended)


@router.get("/attention", response_model=list[AttentionItem])
async def get_attention(
    session=Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user=Depends(get_current_user)
):
    """Получить список вакансий, требующих внимания"""
    return await compute_attention(session, company_id)


@router.get("/events", response_model=list[EventOut])
async def get_events(
    limit: int = Query(default=30, ge=1, le=100, description="Количество событий"),
    candidate_id: UUID | None = Query(default=None, description="Фильтр по кандидату"),
    session=Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user=Depends(get_current_user)
):
    """Получить ленту событий"""
    manager_user_id = current_user.id if current_user.role == "manager" else None
    events = await list_recent_events(session, company_id, limit, candidate_id, manager_user_id=manager_user_id)

    # JSONResponse keeps Cache-Control for the 15s polling loop; response_model on
    # the decorator is needed so openapi-typescript can generate EventOut for the frontend.
    return JSONResponse(
        content=[event.model_dump(mode='json') for event in events],
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/pulse-summary", response_model=PulseSummary)
async def get_pulse_summary(
    period: str = Query(default="month", description="Период: week, month, quarter, year, all"),
    session=Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user=Depends(get_current_user)
):
    """Получить сводку пульса"""
    return await compute_pulse_summary(session, company_id, period)


@router.get("/sources", response_model=list[SourceItem])
async def get_sources(
    period: str = Query(default="month", description="Период: week, month, quarter, year, all"),
    session=Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user=Depends(get_current_user)
):
    """Получить топ источников кандидатов"""
    return await top_sources(session, company_id, period)


@router.get("/dialogs", response_model=list[HomeDialogOut])
async def get_dialogs(
    session=Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user=Depends(get_current_user)
):
    """Получить последние диалоги (чаты) на главной"""
    manager_user_id = current_user.id if current_user.role == "manager" else None
    return await list_recent_dialogs(session, company_id, manager_user_id=manager_user_id)