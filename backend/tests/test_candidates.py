import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class TestCandidates:
    async def test_create_candidate_validation(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str]
    ):
        """Test 422 validation error without required fields"""
        # Missing source
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Иванов",
                "first_name": "Иван"
            }
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

        # Missing last_name
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "first_name": "Иван",
                "source": "manual"
            }
        )

        assert response.status_code == 422

        # Missing first_name
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Иванов",
                "source": "manual"
            }
        )

        assert response.status_code == 422

    async def test_create_candidate_with_vacancy_id(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test creating candidate with vacancy_id creates application in 'added' stage"""
        from app.models import Vacancy
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate

        # Create vacancy directly via service to avoid router issues
        vacancy_data = VacancyCreate(
            name="Test Vacancy",
            funnel_template="default",
            team=[admin_user.id]
        )
        vacancy = await create_vacancy(
            db_session, vacancy_data, admin_user.company_id, admin_user.id
        )
        await db_session.commit()

        # Create candidate with vacancy_id
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Петров",
                "first_name": "Пётр",
                "source": "manual",
                "vacancy_id": str(vacancy.id)
            }
        )

        assert response.status_code == 201
        candidate = response.json()
        assert candidate["last_name"] == "Петров"
        assert candidate["first_name"] == "Пётр"
        assert candidate["source"] == "manual"

        candidate_id = candidate["id"]

        # Check that application was created
        apps_response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}/applications",
            headers=auth_headers
        )
        assert apps_response.status_code == 200
        applications = apps_response.json()
        assert len(applications) == 1
        assert applications[0]["stage"] == "added"
        assert applications[0]["vacancy_id"] == str(vacancy.id)

    async def test_candidate_applications_with_client_name(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test that client_name is returned in candidate applications when vacancy has client"""
        from app.models import Client, Vacancy
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate

        # Create client directly
        client = Client(
            name="Test Client",
            company_id=admin_user.company_id
        )
        db_session.add(client)
        await db_session.flush()

        # Create vacancy with client
        vacancy_data = VacancyCreate(
            name="Test Vacancy with Client",
            funnel_template="default",
            team=[admin_user.id],
            client_id=client.id
        )
        vacancy = await create_vacancy(
            db_session, vacancy_data, admin_user.company_id, admin_user.id
        )
        await db_session.commit()

        # Create candidate with vacancy_id
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Иванов",
                "first_name": "Иван",
                "source": "manual",
                "vacancy_id": str(vacancy.id)
            }
        )

        assert response.status_code == 201
        candidate_id = response.json()["id"]

        # Check application history includes client_name
        apps_response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}/applications",
            headers=auth_headers
        )
        assert apps_response.status_code == 200
        applications = apps_response.json()
        assert len(applications) == 1
        assert applications[0]["client_name"] == "Test Client"
        assert applications[0]["vacancy_name"] == "Test Vacancy with Client"

    async def test_candidate_applications_without_client_name(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test that client_name is null when vacancy has no client"""
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate

        # Create vacancy without client
        vacancy_data = VacancyCreate(
            name="Test Vacancy without Client",
            funnel_template="default",
            team=[admin_user.id]
        )
        vacancy = await create_vacancy(
            db_session, vacancy_data, admin_user.company_id, admin_user.id
        )
        await db_session.commit()

        # Create candidate with vacancy_id
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Петров",
                "first_name": "Пётр",
                "source": "manual",
                "vacancy_id": str(vacancy.id)
            }
        )

        assert response.status_code == 201
        candidate_id = response.json()["id"]

        # Check application history has null client_name
        apps_response = await async_client.get(
            f"/api/v1/candidates/{candidate_id}/applications",
            headers=auth_headers
        )
        assert apps_response.status_code == 200
        applications = apps_response.json()
        assert len(applications) == 1
        assert applications[0]["client_name"] is None
        assert applications[0]["vacancy_name"] == "Test Vacancy without Client"

    async def test_create_candidate_with_comment_and_add_type(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str]
    ):
        """Test creating candidate with comment and add_type saves to extra"""
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Тестов",
                "first_name": "Тест",
                "source": "manual",
                "comment": "Отличный кандидат",
                "add_type": "import"
            }
        )

        assert response.status_code == 201
        candidate = response.json()
        assert candidate["last_name"] == "Тестов"
        assert candidate["first_name"] == "Тест"
        assert candidate["source"] == "manual"

        # Check extra field contains comment and add_type
        assert candidate["extra"] is not None
        assert candidate["extra"]["comment"] == "Отличный кандидат"
        assert candidate["extra"]["add_type"] == "import"

    async def test_create_candidate_with_messengers(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str]
    ):
        """Test creating candidate with messengers"""
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Мессенджеров",
                "first_name": "Тест",
                "source": "manual",
                "messengers": [
                    {"type": "tg", "url": "https://t.me/testuser"},
                    {"type": "linkedin", "url": "https://linkedin.com/in/testuser"}
                ]
            }
        )

        assert response.status_code == 201
        candidate = response.json()
        assert candidate["last_name"] == "Мессенджеров"
        assert candidate["first_name"] == "Тест"
        assert candidate["source"] == "manual"

        # Check messengers field
        assert len(candidate["messengers"]) == 2
        assert candidate["messengers"][0]["type"] == "tg"
        assert candidate["messengers"][0]["url"] == "https://t.me/testuser"
        assert candidate["messengers"][1]["type"] == "linkedin"
        assert candidate["messengers"][1]["url"] == "https://linkedin.com/in/testuser"

    async def test_create_candidate_without_optional_fields(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str]
    ):
        """Test creating candidate without new optional fields works as before"""
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Простой",
                "first_name": "Кандидат",
                "source": "manual"
            }
        )

        assert response.status_code == 201
        candidate = response.json()
        assert candidate["last_name"] == "Простой"
        assert candidate["first_name"] == "Кандидат"
        assert candidate["source"] == "manual"

        # Check defaults
        assert candidate["extra"] == {}
        assert candidate["messengers"] == []

    async def test_create_candidate_with_empty_comment(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str]
    ):
        """Test creating candidate with empty comment doesn't clutter extra"""
        response = await async_client.post(
            "/api/v1/candidates",
            headers=auth_headers,
            json={
                "last_name": "Пустой",
                "first_name": "Комментарий",
                "source": "manual",
                "comment": "",
                "add_type": "manual"  # default value
            }
        )

        assert response.status_code == 201
        candidate = response.json()

        # Check that empty comment is not stored and default add_type is not stored
        assert candidate["extra"] == {}

# ===== Редактирование кандидата из карточки: source + messengers =====

async def test_update_candidate_source_and_messengers(
    async_client: AsyncClient, auth_headers: dict, test_candidate, db_session: AsyncSession
):
    """PATCH /candidates/{id} обновляет source и messengers (новые поля для формы правки)."""
    r = await async_client.patch(
        f"/api/v1/candidates/{test_candidate.id}",
        headers=auth_headers,
        json={
            "source": "hh",
            "city": "Казань",
            "messengers": [{"type": "tg", "url": "https://t.me/foo"}],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source"] == "hh"
    assert data["city"] == "Казань"
    assert data["messengers"] == [{"type": "tg", "url": "https://t.me/foo"}]


async def test_update_candidate_messengers_omitted_preserved(
    async_client: AsyncClient, auth_headers: dict, test_candidate, db_session: AsyncSession
):
    """messengers НЕ передан → существующие сохраняются (None = не трогать)."""
    # Сначала проставим мессенджер
    await async_client.patch(
        f"/api/v1/candidates/{test_candidate.id}",
        headers=auth_headers,
        json={"messengers": [{"type": "wa", "url": "https://wa.me/79990001122"}]},
    )
    # Патч без messengers — не должен их затереть
    r = await async_client.patch(
        f"/api/v1/candidates/{test_candidate.id}",
        headers=auth_headers,
        json={"phone": "+7 999 000 11 22"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["phone"] == "+7 999 000 11 22"
    assert data["messengers"] == [{"type": "wa", "url": "https://wa.me/79990001122"}]

    # Пустой список — очистка
    r2 = await async_client.patch(
        f"/api/v1/candidates/{test_candidate.id}",
        headers=auth_headers,
        json={"messengers": []},
    )
    assert r2.status_code == 200
    assert r2.json()["messengers"] == []


async def test_update_candidate_source_linkedin(
    async_client: AsyncClient, auth_headers: dict, test_candidate, db_session: AsyncSession
):
    """source='linkedin' принимается (Literal + CHECK после миграции e1f2a3b4c5d6)."""
    r = await async_client.patch(
        f"/api/v1/candidates/{test_candidate.id}",
        headers=auth_headers,
        json={"source": "linkedin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "linkedin"


async def test_update_candidate_invalid_source_422(
    async_client: AsyncClient, auth_headers: dict, test_candidate, db_session: AsyncSession
):
    """Невалидный source → 422 от Pydantic (Literal), не 500."""
    r = await async_client.patch(
        f"/api/v1/candidates/{test_candidate.id}",
        headers=auth_headers,
        json={"source": "facebook"},
    )
    assert r.status_code == 422, r.text


async def test_candidate_source_url_create_update_get(
    async_client: AsyncClient, auth_headers: dict, admin_user, db_session: AsyncSession,
):
    """source_url: сохраняется при создании, отдаётся в GET, правится через PATCH."""
    # Create с ссылкой на резюме
    created = await async_client.post(
        "/api/v1/candidates",
        headers=auth_headers,
        json={
            "last_name": "Ссылкин", "first_name": "Тест", "source": "hh",
            "source_url": "https://hh.ru/resume/abc123",
        },
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["source_url"] == "https://hh.ru/resume/abc123"

    # GET отдаёт source_url
    got = await async_client.get(f"/api/v1/candidates/{cid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["source_url"] == "https://hh.ru/resume/abc123"

    # PATCH меняет ссылку
    patched = await async_client.patch(
        f"/api/v1/candidates/{cid}",
        headers=auth_headers,
        json={"source_url": "https://hh.ru/resume/xyz789"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["source_url"] == "https://hh.ru/resume/xyz789"

    # Пустая строка → очистка (NULL)
    cleared = await async_client.patch(
        f"/api/v1/candidates/{cid}",
        headers=auth_headers,
        json={"source_url": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["source_url"] is None


# ===== Кандидат без привязки к вакансии + назначение позже (фикс логики) =====

async def test_create_candidate_without_vacancy_then_assign(
    async_client: AsyncClient, auth_headers: dict, admin_user, db_session: AsyncSession,
):
    """Кандидат создаётся БЕЗ вакансии (в базу), затем привязывается через assign."""
    from app.models import Vacancy, Client

    # Создаём кандидата без vacancy_id → должен попасть «в базу», без application
    created = await async_client.post(
        "/api/v1/candidates",
        headers=auth_headers,
        json={"last_name": "Базовый", "first_name": "Кандидат", "source": "manual"},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]

    apps = await async_client.get(f"/api/v1/candidates/{cid}/applications", headers=auth_headers)
    assert apps.status_code == 200
    assert apps.json() == []  # ни одной вакансии

    # Готовим вакансию для назначения
    client = Client(company_id=admin_user.company_id, name="Клиент Назн")
    db_session.add(client)
    await db_session.flush()
    vac = Vacancy(company_id=admin_user.company_id, client_id=client.id, name="Назн-вакансия", status="active")
    db_session.add(vac)
    await db_session.commit()

    # Назначаем кандидата на вакансию (этап added)
    assigned = await async_client.post(
        f"/api/v1/candidates/{cid}/applications",
        headers=auth_headers,
        json={"vacancy_id": str(vac.id), "stage": "added"},
    )
    assert assigned.status_code == 201, assigned.text

    apps2 = await async_client.get(f"/api/v1/candidates/{cid}/applications", headers=auth_headers)
    assert len(apps2.json()) == 1

    # Повторное назначение на ту же вакансию → 409
    again = await async_client.post(
        f"/api/v1/candidates/{cid}/applications",
        headers=auth_headers,
        json={"vacancy_id": str(vac.id), "stage": "added"},
    )
    assert again.status_code == 409


async def test_assign_resolves_stage_to_funnel_when_added_absent(
    async_client: AsyncClient, auth_headers: dict, admin_user, test_candidate, db_session: AsyncSession,
):
    """Назначение на вакансию без этапа 'added' (массовая воронка) → этап резолвится
    в первый непустой этап воронки, а не падает/не создаёт «призрачный» этап."""
    from app.models import Vacancy, Client, VacancyStage

    client = Client(company_id=admin_user.company_id, name="Клиент Масс")
    db_session.add(client)
    await db_session.flush()
    vac = Vacancy(company_id=admin_user.company_id, client_id=client.id, name="Масс-вакансия", status="active")
    db_session.add(vac)
    await db_session.flush()
    # Воронка БЕЗ 'added' (как шаблон «массовый»)
    for i, key in enumerate(["response", "selected", "interview", "hired", "rejected"]):
        db_session.add(VacancyStage(
            company_id=admin_user.company_id, vacancy_id=vac.id,
            stage_key=key, label=key, order_index=i,
        ))
    await db_session.commit()

    # Просим 'added' — его в воронке нет → должен резолвиться в 'response' (первый непустой)
    resp = await async_client.post(
        f"/api/v1/candidates/{test_candidate.id}/applications",
        headers=auth_headers,
        json={"vacancy_id": str(vac.id), "stage": "added"},
    )
    assert resp.status_code == 201, resp.text

    apps = await async_client.get(
        f"/api/v1/candidates/{test_candidate.id}/applications", headers=auth_headers
    )
    assert len(apps.json()) == 1
    assert apps.json()[0]["stage"] == "response"  # зарезолвлен, не 'added'
