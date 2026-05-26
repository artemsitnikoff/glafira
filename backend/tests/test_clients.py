"""Test client endpoints"""


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