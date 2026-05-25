from httpx import AsyncClient

from app.models import Candidate, User


async def test_create_comment_resolves_email_mention(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_candidate: Candidate,
    admin_user: User,
):
    cid = str(test_candidate.id)
    response = await async_client.post(
        f"/api/v1/candidates/{cid}/comments",
        headers=auth_headers,
        json={"body": f"Сильный кандидат, @{admin_user.email} посмотри"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mentions"] == [str(admin_user.id)]
    assert body["author_name"] == admin_user.full_name


async def test_comment_with_unknown_mention_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_candidate: Candidate,
):
    cid = str(test_candidate.id)
    response = await async_client.post(
        f"/api/v1/candidates/{cid}/comments",
        headers=auth_headers,
        json={"body": "Кто это вообще @nobody@example.com"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MENTION"
