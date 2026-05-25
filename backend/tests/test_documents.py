import io

from httpx import AsyncClient

from app.models import Candidate


async def test_upload_then_list_then_delete_document(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_candidate: Candidate,
):
    cid = str(test_candidate.id)

    upload = await async_client.post(
        f"/api/v1/candidates/{cid}/documents",
        headers=auth_headers,
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-fake-content"), "application/pdf")},
        data={"kind": "resume"},
    )
    assert upload.status_code == 201, upload.text
    doc = upload.json()
    assert doc["filename"] == "resume.pdf"
    assert doc["file_type"] == "pdf"
    assert doc["source"] == "resume"

    listing = await async_client.get(
        f"/api/v1/candidates/{cid}/documents",
        headers=auth_headers,
    )
    assert listing.status_code == 200
    assert any(d["id"] == doc["id"] for d in listing.json())

    deleted = await async_client.delete(
        f"/api/v1/documents/{doc['id']}",
        headers=auth_headers,
    )
    assert deleted.status_code in (200, 204)


async def test_upload_rejects_unsupported_extension(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_candidate: Candidate,
):
    cid = str(test_candidate.id)
    response = await async_client.post(
        f"/api/v1/candidates/{cid}/documents",
        headers=auth_headers,
        files={"file": ("evil.exe", io.BytesIO(b"MZ\x00\x00"), "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
