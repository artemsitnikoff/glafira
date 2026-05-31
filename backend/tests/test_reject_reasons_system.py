"""Tests for system (protected) reject reasons — гарантия непустоты."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import RejectReason


@pytest.mark.asyncio
async def test_delete_system_reason_blocked(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Системную причину отказа удалить нельзя (инвариант непустоты)."""
    reason = RejectReason(
        company_id=default_company_id,
        side="company",
        label="Несоответствие опыта",
        order_index=1,
        is_system=True,
    )
    db_session.add(reason)
    await db_session.commit()

    response = await async_client.delete(
        f"/api/v1/settings/reject-reasons/{reason.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 400  # бизнес-ValidationError
    # Причина всё ещё активна
    await db_session.refresh(reason)
    assert reason.is_active is True


@pytest.mark.asyncio
async def test_delete_non_system_reason_ok(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Обычную (не системную) причину удалить можно (soft-delete)."""
    reason = RejectReason(
        company_id=default_company_id,
        side="company",
        label="Не прошёл интервью",
        order_index=2,
        is_system=False,
    )
    db_session.add(reason)
    await db_session.commit()

    response = await async_client.delete(
        f"/api/v1/settings/reject-reasons/{reason.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    await db_session.refresh(reason)
    assert reason.is_active is False


@pytest.mark.asyncio
async def test_rename_system_reason_allowed(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Системную причину можно переименовать (запрещено только удаление)."""
    reason = RejectReason(
        company_id=default_company_id,
        side="candidate",
        label="Не вышел на связь",
        order_index=1,
        is_system=True,
    )
    db_session.add(reason)
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/settings/reject-reasons/{reason.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"label": "Не отвечает на сообщения"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Не отвечает на сообщения"
    assert data["is_system"] is True


@pytest.mark.asyncio
async def test_get_reasons_exposes_is_system(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """GET /settings/reject-reasons отдаёт флаг is_system."""
    db_session.add(RejectReason(
        company_id=default_company_id, side="company",
        label="Системная", order_index=1, is_system=True,
    ))
    db_session.add(RejectReason(
        company_id=default_company_id, side="company",
        label="Обычная", order_index=2, is_system=False,
    ))
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/settings/reject-reasons",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    by_label = {r["label"]: r for r in response.json()}
    assert by_label["Системная"]["is_system"] is True
    assert by_label["Обычная"]["is_system"] is False
