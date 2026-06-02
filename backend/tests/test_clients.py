"""Test client endpoints"""

from sqlalchemy import select

from app.models import Client, Vacancy


async def test_list_clients_returns_empty_when_no_seed(async_client, auth_headers):
    """Test that empty list is returned when no clients exist"""
    r = await async_client.get("/api/v1/clients", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


async def test_create_and_list_client(async_client, auth_headers):
    """Test creating a client and listing it"""
    # Create client
    create_data = {"name": "Тест-клиент", "contact_person": "Иван Иванов"}
    create = await async_client.post("/api/v1/clients", headers=auth_headers, json=create_data)
    assert create.status_code == 201

    created_client = create.json()
    assert created_client["name"] == "Тест-клиент"
    assert created_client["contact_person"] == "Иван Иванов"
    assert "id" in created_client
    cid = created_client["id"]

    # List clients and check our client is there
    listing = await async_client.get("/api/v1/clients", headers=auth_headers)
    assert listing.status_code == 200
    clients = listing.json()
    assert any(c["id"] == cid for c in clients)

    # Find our client in the list and verify fields
    our_client = next(c for c in clients if c["id"] == cid)
    assert our_client["name"] == "Тест-клиент"
    assert our_client["contact_person"] == "Иван Иванов"


async def _create_client(async_client, auth_headers, name="Заказчик", contact="Контакт"):
    r = await async_client.post(
        "/api/v1/clients", headers=auth_headers,
        json={"name": name, "contact_person": contact},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_patch_client_updates_fields(async_client, auth_headers, db_session):
    cid = await _create_client(async_client, auth_headers, name="Старое имя", contact="Старый")

    r = await async_client.patch(
        f"/api/v1/clients/{cid}", headers=auth_headers,
        json={"name": "Новое имя", "contact_person": "Новый контакт"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Новое имя"
    assert body["contact_person"] == "Новый контакт"

    # Verify persisted in DB
    row = (await db_session.execute(
        select(Client).where(Client.id == cid)
    )).scalar_one()
    assert row.name == "Новое имя"
    assert row.contact_person == "Новый контакт"


async def test_patch_client_partial_keeps_other_field(async_client, auth_headers, db_session):
    cid = await _create_client(async_client, auth_headers, name="Имя", contact="Контакт")

    # Update only name
    r = await async_client.patch(
        f"/api/v1/clients/{cid}", headers=auth_headers,
        json={"name": "Только имя"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Только имя"
    assert r.json()["contact_person"] == "Контакт"


async def test_patch_unknown_client_returns_404(async_client, auth_headers):
    missing = "00000000-0000-0000-0000-0000000000ff"
    r = await async_client.patch(
        f"/api/v1/clients/{missing}", headers=auth_headers,
        json={"name": "x"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


async def test_delete_client_without_vacancies(async_client, auth_headers, db_session):
    cid = await _create_client(async_client, auth_headers, name="К удалению")

    r = await async_client.delete(f"/api/v1/clients/{cid}", headers=auth_headers)
    assert r.status_code == 204

    # Gone from DB
    row = (await db_session.execute(
        select(Client).where(Client.id == cid)
    )).scalar_one_or_none()
    assert row is None


async def test_delete_client_with_vacancies_conflict(async_client, auth_headers, db_session, admin_user):
    cid = await _create_client(async_client, auth_headers, name="С вакансией")

    # Attach a vacancy to this client
    vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Тест-вакансия",
        client_id=cid,
    )
    db_session.add(vacancy)
    await db_session.commit()

    r = await async_client.delete(f"/api/v1/clients/{cid}", headers=auth_headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"
    assert "вакансий" in r.json()["error"]["message"]

    # Client still present
    row = (await db_session.execute(
        select(Client).where(Client.id == cid)
    )).scalar_one_or_none()
    assert row is not None


async def test_delete_client_with_archived_vacancy_conflict(async_client, auth_headers, db_session, admin_user):
    cid = await _create_client(async_client, auth_headers, name="С архивной вакансией")

    # Archived vacancy must still block deletion
    vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Архивная вакансия",
        client_id=cid,
        status="archived",
    )
    db_session.add(vacancy)
    await db_session.commit()

    r = await async_client.delete(f"/api/v1/clients/{cid}", headers=auth_headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


async def test_delete_unknown_client_returns_404(async_client, auth_headers):
    missing = "00000000-0000-0000-0000-0000000000fe"
    r = await async_client.delete(f"/api/v1/clients/{missing}", headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"