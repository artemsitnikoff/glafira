"""Tests for funnel table sorting + selected_at on manual candidate creation."""

import pytest
from httpx import AsyncClient


async def _create_vacancy(client: AsyncClient, hdr: dict, admin_user, default_client: str) -> str:
    r = await client.post(
        "/api/v1/vacancies", headers=hdr,
        json={"name": "VacSort", "team": [str(admin_user.id)], "funnel_template": "default",
              "client_id": default_client},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _add_candidate(client: AsyncClient, hdr: dict, vacancy_id: str, last_name: str) -> None:
    r = await client.post(
        "/api/v1/candidates", headers=hdr,
        json={"last_name": last_name, "first_name": "Тест", "source": "manual", "vacancy_id": vacancy_id},
    )
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_manual_candidate_has_selected_at(async_client: AsyncClient, admin_token: str, admin_user, default_client: str):
    """Вручную созданный кандидат, привязанный к вакансии, получает «Дату отбора» (selected_at)."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    vid = await _create_vacancy(async_client, hdr, admin_user, default_client)
    await _add_candidate(async_client, hdr, vid, "Яковлев")

    apps = await async_client.get(f"/api/v1/vacancies/{vid}/applications", headers=hdr)
    assert apps.status_code == 200
    items = apps.json()["items"]
    assert len(items) >= 1
    assert items[0]["selected_at"] is not None  # «Дата отбора» проставлена


@pytest.mark.asyncio
async def test_sort_full_name_lexicographic(async_client: AsyncClient, admin_token: str, admin_user, default_client: str):
    """sort=full_name&order=asc — лексикографический порядок по фамилии."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    vid = await _create_vacancy(async_client, hdr, admin_user, default_client)
    for ln in ("Яковлев", "Абрамов", "Миронов"):
        await _add_candidate(async_client, hdr, vid, ln)

    r = await async_client.get(
        f"/api/v1/vacancies/{vid}/applications?sort=full_name&order=asc", headers=hdr
    )
    assert r.status_code == 200
    names = [i["full_name"] for i in r.json()["items"]]
    assert names == sorted(names)  # А-Я

    r2 = await async_client.get(
        f"/api/v1/vacancies/{vid}/applications?sort=full_name&order=desc", headers=hdr
    )
    names2 = [i["full_name"] for i in r2.json()["items"]]
    assert names2 == sorted(names2, reverse=True)  # Я-А


@pytest.mark.asyncio
async def test_sort_by_stage_runs(async_client: AsyncClient, admin_token: str, admin_user, default_client: str):
    """sort=stage не падает (выполняет join VacancyStage по порядку воронки) и возвращает 200."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    vid = await _create_vacancy(async_client, hdr, admin_user, default_client)
    await _add_candidate(async_client, hdr, vid, "Иванов")
    await _add_candidate(async_client, hdr, vid, "Петров")

    r = await async_client.get(
        f"/api/v1/vacancies/{vid}/applications?sort=stage&order=asc", headers=hdr
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
