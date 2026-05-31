"""Tests for funnel applications filters (source multi-select, city ILIKE)."""

import pytest
from httpx import AsyncClient


async def _vacancy(client: AsyncClient, hdr: dict, admin_user) -> str:
    r = await client.post(
        "/api/v1/vacancies", headers=hdr,
        json={"name": "VacFilter", "team": [str(admin_user.id)], "funnel_template": "default"},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _add(client: AsyncClient, hdr: dict, vid: str, last_name: str, source: str, city: str) -> None:
    r = await client.post(
        "/api/v1/candidates", headers=hdr,
        json={"last_name": last_name, "first_name": "Т", "source": source, "city": city, "vacancy_id": vid},
    )
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_filter_by_source_multi(async_client: AsyncClient, admin_token: str, admin_user):
    """source=hh&source=avito возвращает кандидатов обоих источников (in_), а одиночный — только свой."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    vid = await _vacancy(async_client, hdr, admin_user)
    await _add(async_client, hdr, vid, "Адамов", "hh", "Москва")
    await _add(async_client, hdr, vid, "Борисов", "avito", "Казань")
    await _add(async_client, hdr, vid, "Власов", "manual", "Москва")

    both = await async_client.get(
        f"/api/v1/vacancies/{vid}/applications?source=hh&source=avito", headers=hdr
    )
    assert both.status_code == 200
    assert both.json()["total"] == 2  # hh + avito

    one = await async_client.get(f"/api/v1/vacancies/{vid}/applications?source=hh", headers=hdr)
    assert one.json()["total"] == 1


@pytest.mark.asyncio
async def test_filter_by_city_ilike(async_client: AsyncClient, admin_token: str, admin_user):
    """city — регистронезависимая подстрока (ILIKE)."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    vid = await _vacancy(async_client, hdr, admin_user)
    await _add(async_client, hdr, vid, "Адамов", "hh", "Москва")
    await _add(async_client, hdr, vid, "Борисов", "avito", "Казань")
    await _add(async_client, hdr, vid, "Власов", "manual", "Москва")

    r = await async_client.get(f"/api/v1/vacancies/{vid}/applications?city=моСК", headers=hdr)
    assert r.status_code == 200
    assert r.json()["total"] == 2  # «Москва» x2, регистронезависимо
    cities = {i["city"] for i in r.json()["items"]}
    assert cities == {"Москва"}
