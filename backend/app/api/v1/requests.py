"""API модуля «Заявки на подбор».

Роутер подключён БЕЗ forbid_hiring_manager (router.py) — нанимающий менеджер сюда
ХОДИТ, но видит/меняет только СВОИ заявки (скоуп в сервисе). Управление воронкой и
настройками — admin.

⚠️ Статические роуты объявлены ДО динамического /{request_id}, иначе он их перехватит.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...deps import get_current_user, get_current_company_id
from ...core.permissions import require_admin, require_recruiter_or_admin
from ...core.errors import ForbiddenError
from ...models import User
from ...schemas.hiring_request import (
    HiringRequestCreate, HiringRequestDetail, HiringRequestListResponse,
    RequestMoveRequest, RequestRejectRequest, RequestCloseRequest,
    RequestCommentCreate, RequestSidebarCounts,
    RequestStageOut, RequestStageCreate, RequestStageUpdate, RequestStageReorder,
    RequestSettingsOut, RequestSettingsUpdate, RequestFormLinkOut,
)
from ...services import hiring_request as svc

router = APIRouter()


def _forbid_manager_write(user: User) -> None:
    """Управление воронкой/настройками — admin; hiring_manager сюда не дойдёт (router-гард)."""
    if user.role not in ("admin", "recruiter"):
        raise ForbiddenError("Недостаточно прав")


# ── Списки/счётчики (статические) ────────────────────────────────────────────
@router.get("", response_model=HiringRequestListResponse)
async def list_requests(
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    items, total = await svc.list_requests(
        session, company_id=company_id, user=current_user,
        status=status, query=query, limit=limit, offset=offset,
    )
    return {"items": items, "total": total}


@router.get("/sidebar", response_model=RequestSidebarCounts)
async def requests_sidebar(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    return await svc.sidebar_counts(session, company_id, current_user)


@router.get("/stages", response_model=list[RequestStageOut])
async def request_stages(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Полная воронка заявок (фиксированные + кастомные) — для рендера чипов/полосы."""
    return await svc.get_stage_flow(session, company_id)


# ── Настройки воронки заявок (admin) ─────────────────────────────────────────
@router.post("/funnel-stages", response_model=list[RequestStageOut], dependencies=[Depends(require_admin)])
async def create_stage(
    body: RequestStageCreate,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    await svc.add_stage(session, company_id, body.label, body.description)
    await session.commit()
    return await svc.get_stage_flow(session, company_id)


@router.patch("/funnel-stages/{stage_key}", response_model=list[RequestStageOut], dependencies=[Depends(require_admin)])
async def patch_stage(
    stage_key: str,
    body: RequestStageUpdate,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    await svc.update_stage(session, company_id, stage_key, body.label, body.description)
    await session.commit()
    return await svc.get_stage_flow(session, company_id)


@router.delete("/funnel-stages/{stage_key}", response_model=list[RequestStageOut], dependencies=[Depends(require_admin)])
async def remove_stage(
    stage_key: str,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    await svc.delete_stage(session, company_id, stage_key)
    await session.commit()
    return await svc.get_stage_flow(session, company_id)


@router.put("/funnel-stages/reorder", response_model=list[RequestStageOut], dependencies=[Depends(require_admin)])
async def reorder_stages(
    body: RequestStageReorder,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    await svc.reorder_stages(session, company_id, body.stage_keys)
    await session.commit()
    return await svc.get_stage_flow(session, company_id)


@router.get("/settings", response_model=RequestSettingsOut)
async def get_settings(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    _forbid_manager_write(current_user)  # admin+recruiter read
    st = await svc.get_or_create_settings(session, company_id)
    await session.commit()
    return RequestSettingsOut(
        autoclose_on=st.autoclose_on, question_moves_to_work=st.question_moves_to_work,
        notify_manager_on_stage=st.notify_manager_on_stage, form_enabled=st.form_enabled,
    )


@router.patch("/settings", response_model=RequestSettingsOut, dependencies=[Depends(require_admin)])
async def patch_settings(
    body: RequestSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    st = await svc.get_or_create_settings(session, company_id)
    for field in ("autoclose_on", "question_moves_to_work", "notify_manager_on_stage", "form_enabled"):
        val = getattr(body, field)
        if val is not None:
            setattr(st, field, val)
    await session.commit()
    return RequestSettingsOut(
        autoclose_on=st.autoclose_on, question_moves_to_work=st.question_moves_to_work,
        notify_manager_on_stage=st.notify_manager_on_stage, form_enabled=st.form_enabled,
    )


@router.get("/form-link", response_model=RequestFormLinkOut, dependencies=[Depends(require_recruiter_or_admin)])
async def get_form_link(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    st = await svc.get_or_create_settings(session, company_id)
    await session.commit()
    url = svc.form_url(st.form_token) if st.form_enabled else None
    return RequestFormLinkOut(url=url, enabled=st.form_enabled)


@router.post("/form-link/rotate", response_model=RequestFormLinkOut, dependencies=[Depends(require_admin)])
async def rotate_form_link(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """Сгенерировать/ротировать токен формы. Старая ссылка мгновенно перестаёт работать."""
    token = await svc.rotate_form_token(session, company_id)
    await session.commit()
    return RequestFormLinkOut(url=svc.form_url(token), enabled=True)


# ── Создание заявки ───────────────────────────────────────────────────────────
@router.post("", response_model=HiringRequestDetail, status_code=201)
async def create_request(
    body: HiringRequestCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    # Не-персонал (hiring_manager/manager) подаёт от своего имени (via=cabinet), чтобы
    # видеть свою заявку в author-scoped списке; recruiter/admin вносит со слов (via=manual).
    if current_user.role not in ("admin", "recruiter"):
        req = await svc.create_request(
            session, company_id=company_id, user=current_user, data=body, via="cabinet",
        )
    else:
        req = await svc.create_request(
            session, company_id=company_id, user=current_user, data=body, via="manual",
            author_name=body.author_name, author_role=body.author_role,
            author_contact=body.author_contact,
        )
    await session.commit()
    req = await svc.get_request_or_raise(session, company_id, req.id)
    return await svc.build_detail(session, company_id, req)


# ── Деталь + мутации (динамические) ──────────────────────────────────────────
@router.get("/{request_id}", response_model=HiringRequestDetail)
async def get_request(
    request_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    req = await svc.get_request_or_raise(session, company_id, request_id)
    svc.assert_request_access(req, current_user)
    return await svc.build_detail(session, company_id, req)


@router.patch("/{request_id}/move", response_model=HiringRequestDetail)
async def move_request(
    request_id: UUID,
    body: RequestMoveRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    req = await svc.get_request_or_raise(session, company_id, request_id)
    svc.assert_request_access(req, current_user)
    await svc.move_request(session, company_id=company_id, user=current_user, req=req, target=body.target)
    await session.commit()
    req = await svc.get_request_or_raise(session, company_id, request_id)
    return await svc.build_detail(session, company_id, req)


@router.post("/{request_id}/reject", response_model=HiringRequestDetail)
async def reject_request(
    request_id: UUID,
    body: RequestRejectRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    req = await svc.get_request_or_raise(session, company_id, request_id)
    svc.assert_request_access(req, current_user)
    await svc.reject_request(session, company_id=company_id, user=current_user, req=req, reason=body.reason)
    await session.commit()
    req = await svc.get_request_or_raise(session, company_id, request_id)
    return await svc.build_detail(session, company_id, req)


@router.post("/{request_id}/restore", response_model=HiringRequestDetail)
async def restore_request(
    request_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    req = await svc.get_request_or_raise(session, company_id, request_id)
    svc.assert_request_access(req, current_user)
    await svc.restore_request(session, company_id=company_id, user=current_user, req=req)
    await session.commit()
    req = await svc.get_request_or_raise(session, company_id, request_id)
    return await svc.build_detail(session, company_id, req)


@router.post("/{request_id}/close", response_model=HiringRequestDetail)
async def close_request(
    request_id: UUID,
    body: RequestCloseRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    req = await svc.get_request_or_raise(session, company_id, request_id)
    svc.assert_request_access(req, current_user)
    await svc.close_request(session, company_id=company_id, user=current_user, req=req, note=body.note)
    await session.commit()
    req = await svc.get_request_or_raise(session, company_id, request_id)
    return await svc.build_detail(session, company_id, req)


@router.post("/{request_id}/comments", response_model=HiringRequestDetail)
async def add_comment(
    request_id: UUID,
    body: RequestCommentCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    req = await svc.get_request_or_raise(session, company_id, request_id)
    svc.assert_request_access(req, current_user)
    await svc.add_comment(session, company_id=company_id, user=current_user, req=req, body=body.body)
    await session.commit()
    req = await svc.get_request_or_raise(session, company_id, request_id)
    return await svc.build_detail(session, company_id, req)
