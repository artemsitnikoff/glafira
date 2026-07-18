"""Tests for per-vacancy reject reasons (привязка к вакансии)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import RejectReason


async def _seed_company_defaults(db_session, company_id):
    """2 дефолта компании (vacancy_id IS NULL): системная company + обычная candidate."""
    db_session.add(RejectReason(
        company_id=company_id, vacancy_id=None, side="company",
        label="Несоответствие опыта", order_index=1, is_system=True,
    ))
    db_session.add(RejectReason(
        company_id=company_id, vacancy_id=None, side="candidate",
        label="Не устроила ЗП", order_index=1, is_system=False,
    ))
    await db_session.commit()


async def _create_vacancy(async_client, admin_token, admin_user, default_client):
    response = await async_client.post(
        "/api/v1/vacancies",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Vac RR",
            "team": [str(admin_user.id)],
            "funnel_template": "default",
            "client_id": default_client,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_vacancy_copies_default_reasons(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
    admin_user,
    default_client: str,
):
    """Создание вакансии копирует дефолты компании как причины вакансии (с сохранением is_system)."""
    await _seed_company_defaults(db_session, default_company_id)
    vacancy_id = await _create_vacancy(async_client, admin_token, admin_user, default_client)

    # У вакансии появились СВОИ причины (vacancy_id = vacancy)
    result = await db_session.execute(
        select(RejectReason).where(RejectReason.vacancy_id == vacancy_id)
    )
    vac_reasons = list(result.scalars().all())
    assert len(vac_reasons) == 2
    by_label = {r.label: r for r in vac_reasons}
    assert by_label["Несоответствие опыта"].is_system is True
    assert by_label["Не устроила ЗП"].is_system is False
    # Дефолты компании не тронуты (остались с vacancy_id IS NULL)
    result = await db_session.execute(
        select(RejectReason).where(RejectReason.vacancy_id.is_(None))
    )
    assert len(list(result.scalars().all())) == 2


@pytest.mark.asyncio
async def test_get_vacancy_reasons_and_system_guard(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
    admin_user,
    default_client: str,
):
    """GET отдаёт причины вакансии; системную удалить нельзя, обычную — можно."""
    await _seed_company_defaults(db_session, default_company_id)
    vacancy_id = await _create_vacancy(async_client, admin_token, admin_user, default_client)

    resp = await async_client.get(
        f"/api/v1/vacancies/{vacancy_id}/reject-reasons",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    reasons = resp.json()
    assert len(reasons) == 2
    by_label = {r["label"]: r for r in reasons}

    # Системную причину вакансии удалить нельзя
    sys_id = by_label["Несоответствие опыта"]["id"]
    del_sys = await async_client.delete(
        f"/api/v1/vacancies/{vacancy_id}/reject-reasons/{sys_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert del_sys.status_code == 400  # бизнес-ValidationError

    # Обычную — можно (204)
    normal_id = by_label["Не устроила ЗП"]["id"]
    del_norm = await async_client.delete(
        f"/api/v1/vacancies/{vacancy_id}/reject-reasons/{normal_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert del_norm.status_code == 204


@pytest.mark.asyncio
async def test_vacancy_reason_scope_isolation(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    default_company_id: str,
    admin_user,
    default_client: str,
):
    """Через эндпоинт вакансии нельзя удалить дефолт компании (vacancy_id IS NULL)."""
    await _seed_company_defaults(db_session, default_company_id)
    vacancy_id = await _create_vacancy(async_client, admin_token, admin_user, default_client)

    # id дефолта компании (vacancy_id IS NULL, не системного)
    result = await db_session.execute(
        select(RejectReason).where(
            RejectReason.vacancy_id.is_(None),
            RejectReason.label == "Не устроила ЗП",
        )
    )
    company_default = result.scalar_one()

    # Пытаемся удалить дефолт компании через эндпоинт вакансии → не найдено в scope (404)
    resp = await async_client.delete(
        f"/api/v1/vacancies/{vacancy_id}/reject-reasons/{company_default.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404
    # Дефолт компании остался активным
    await db_session.refresh(company_default)
    assert company_default.is_active is True
