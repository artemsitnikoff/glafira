"""Tests for reject reasons reorder functionality"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import RejectReason


@pytest.mark.asyncio
async def test_reorder_reject_reasons(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test PUT /settings/reject-reasons/reorder changes order"""
    # Create reject reasons
    reasons = [
        RejectReason(company_id=default_company_id, side="company", label="Reason A", order_index=1),
        RejectReason(company_id=default_company_id, side="company", label="Reason B", order_index=2),
        RejectReason(company_id=default_company_id, side="company", label="Reason C", order_index=3),
    ]
    for reason in reasons:
        db_session.add(reason)
    await db_session.commit()

    # Get IDs for reordering (C, A, B)
    reason_ids = [reasons[2].id, reasons[0].id, reasons[1].id]

    # Reorder
    response = await async_client.put(
        "/api/v1/settings/reject-reasons/reorder",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "side": "company",
            "reason_ids": [str(id) for id in reason_ids]
        }
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Причины отказа переупорядочены"

    # Verify new order
    result = await db_session.execute(
        select(RejectReason)
        .where(RejectReason.side == "company")
        .order_by(RejectReason.order_index)
    )
    ordered_reasons = list(result.scalars().all())

    assert len(ordered_reasons) == 3
    assert ordered_reasons[0].label == "Reason C"
    assert ordered_reasons[0].order_index == 1
    assert ordered_reasons[1].label == "Reason A"
    assert ordered_reasons[1].order_index == 2
    assert ordered_reasons[2].label == "Reason B"
    assert ordered_reasons[2].order_index == 3


@pytest.mark.asyncio
async def test_reorder_only_affects_specified_side(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test reordering only affects the specified side"""
    # Create reasons for both sides
    company_reasons = [
        RejectReason(company_id=default_company_id, side="company", label="Company A", order_index=1),
        RejectReason(company_id=default_company_id, side="company", label="Company B", order_index=2),
    ]
    candidate_reasons = [
        RejectReason(company_id=default_company_id, side="candidate", label="Candidate A", order_index=1),
        RejectReason(company_id=default_company_id, side="candidate", label="Candidate B", order_index=2),
    ]

    for reason in company_reasons + candidate_reasons:
        db_session.add(reason)
    await db_session.commit()

    # Reorder only company reasons (B, A)
    response = await async_client.put(
        "/api/v1/settings/reject-reasons/reorder",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "side": "company",
            "reason_ids": [str(company_reasons[1].id), str(company_reasons[0].id)]
        }
    )

    assert response.status_code == 200

    # Verify company reasons reordered
    result = await db_session.execute(
        select(RejectReason)
        .where(RejectReason.side == "company")
        .order_by(RejectReason.order_index)
    )
    company_ordered = list(result.scalars().all())
    assert company_ordered[0].label == "Company B"
    assert company_ordered[1].label == "Company A"

    # Verify candidate reasons unchanged
    result = await db_session.execute(
        select(RejectReason)
        .where(RejectReason.side == "candidate")
        .order_by(RejectReason.order_index)
    )
    candidate_ordered = list(result.scalars().all())
    assert candidate_ordered[0].label == "Candidate A"
    assert candidate_ordered[0].order_index == 1
    assert candidate_ordered[1].label == "Candidate B"
    assert candidate_ordered[1].order_index == 2


@pytest.mark.asyncio
async def test_reorder_invalid_side(
    async_client: AsyncClient,
    admin_token: str,
):
    """Test reordering with invalid side fails"""
    response = await async_client.put(
        "/api/v1/settings/reject-reasons/reorder",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "side": "invalid",
            "reason_ids": ["some-id"]
        }
    )

    assert response.status_code == 422  # ValidationError


@pytest.mark.asyncio
async def test_reorder_nonexistent_reason(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
):
    """Test reordering with non-existent reason ID fails"""
    # Create one valid reason
    reason = RejectReason(
        company_id=default_company_id,
        side="company",
        label="Valid Reason",
        order_index=1
    )
    db_session.add(reason)
    await db_session.commit()

    # Try to reorder with non-existent ID
    response = await async_client.put(
        "/api/v1/settings/reject-reasons/reorder",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "side": "company",
            "reason_ids": [str(reason.id), "00000000-0000-0000-0000-000000000000"]
        }
    )

    assert response.status_code == 422  # ValidationError


@pytest.mark.asyncio
async def test_reorder_empty_list(
    async_client: AsyncClient,
    admin_token: str,
):
    """Test reordering with empty reason_ids list fails"""
    response = await async_client.put(
        "/api/v1/settings/reject-reasons/reorder",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "side": "company",
            "reason_ids": []
        }
    )

    assert response.status_code == 422  # ValidationError