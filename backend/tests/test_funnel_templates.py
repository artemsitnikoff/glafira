"""Tests for configurable funnel templates (пресеты воронок)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_template_seeds_stages(async_client: AsyncClient, admin_token: str):
    """Создание шаблона наполняет его базовыми этапами (9 из core STAGES)."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    resp = await async_client.post("/api/v1/settings/funnel-templates", headers=hdr, json={"name": "Мой шаблон"})
    assert resp.status_code == 201
    template_id = resp.json()["id"]
    assert resp.json()["name"] == "Мой шаблон"

    # в списке появился
    lst = await async_client.get("/api/v1/settings/funnel-templates", headers=hdr)
    assert any(t["id"] == template_id for t in lst.json())

    # этапы наполнены
    stages = await async_client.get(f"/api/v1/settings/funnel-templates/{template_id}/stages", headers=hdr)
    assert stages.status_code == 200
    keys = [s["stage_key"] for s in stages.json()]
    assert keys == ["response", "added", "selected", "recruiter", "interview", "manager", "offer", "hired", "rejected"]
    assert all("color" in s for s in stages.json())


@pytest.mark.asyncio
async def test_template_stage_protected_guard(async_client: AsyncClient, admin_token: str):
    """Защищённый этап шаблона удалить нельзя, обычный — можно."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    tid = (await async_client.post("/api/v1/settings/funnel-templates", headers=hdr, json={"name": "T"})).json()["id"]

    del_protected = await async_client.delete(f"/api/v1/settings/funnel-templates/{tid}/stages/hired", headers=hdr)
    assert del_protected.status_code == 400  # бизнес-ValidationError

    del_normal = await async_client.delete(f"/api/v1/settings/funnel-templates/{tid}/stages/selected", headers=hdr)
    assert del_normal.status_code == 200


@pytest.mark.asyncio
async def test_delete_template_cascades(async_client: AsyncClient, admin_token: str):
    """Удаление шаблона удаляет его этапы (каскад) — stages потом 404."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    tid = (await async_client.post("/api/v1/settings/funnel-templates", headers=hdr, json={"name": "T2"})).json()["id"]

    delete = await async_client.delete(f"/api/v1/settings/funnel-templates/{tid}", headers=hdr)
    assert delete.status_code == 200

    stages = await async_client.get(f"/api/v1/settings/funnel-templates/{tid}/stages", headers=hdr)
    assert stages.status_code == 404  # шаблон не найден


@pytest.mark.asyncio
async def test_rename_template(async_client: AsyncClient, admin_token: str):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    tid = (await async_client.post("/api/v1/settings/funnel-templates", headers=hdr, json={"name": "Old"})).json()["id"]
    resp = await async_client.patch(f"/api/v1/settings/funnel-templates/{tid}", headers=hdr, json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"
