import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Tag, Candidate, Application


class TestCandidatesFilters:
    """Test multi-value filters for candidates list"""

    async def test_multi_source_filter(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test source filter with multiple values (comma-separated)"""
        # Create candidates with different sources
        candidate1 = Candidate(
            company_id=admin_user.company_id,
            last_name="Иванов",
            first_name="Иван",
            source="hh"
        )
        candidate2 = Candidate(
            company_id=admin_user.company_id,
            last_name="Петров",
            first_name="Пётр",
            source="avito"
        )
        candidate3 = Candidate(
            company_id=admin_user.company_id,
            last_name="Сидоров",
            first_name="Сидор",
            source="manual"
        )

        db_session.add_all([candidate1, candidate2, candidate3])
        await db_session.commit()

        # Test multi-source filter
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"source": "hh,avito"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        # Extract names for verification
        names = {item["full_name"] for item in data["items"]}
        assert "Иванов Иван" in names
        assert "Петров Пётр" in names
        assert "Сидоров Сидор" not in names

        # Test single source (backward compatibility)
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"source": "manual"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["full_name"] == "Сидоров Сидор"

    async def test_multi_vacancy_filter(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test vacancy_id filter with multiple values"""
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate
        from datetime import datetime, timezone

        # Create vacancies
        vacancy1_data = VacancyCreate(name="Vacancy 1", funnel_template="default", team=[admin_user.id])
        vacancy1 = await create_vacancy(db_session, vacancy1_data, admin_user.company_id, admin_user.id)

        vacancy2_data = VacancyCreate(name="Vacancy 2", funnel_template="default", team=[admin_user.id])
        vacancy2 = await create_vacancy(db_session, vacancy2_data, admin_user.company_id, admin_user.id)

        vacancy3_data = VacancyCreate(name="Vacancy 3", funnel_template="default", team=[admin_user.id])
        vacancy3 = await create_vacancy(db_session, vacancy3_data, admin_user.company_id, admin_user.id)

        # Create candidates
        candidate1 = Candidate(
            company_id=admin_user.company_id,
            last_name="Кандидат",
            first_name="Первый",
            source="manual"
        )
        candidate2 = Candidate(
            company_id=admin_user.company_id,
            last_name="Кандидат",
            first_name="Второй",
            source="manual"
        )
        candidate3 = Candidate(
            company_id=admin_user.company_id,
            last_name="Кандидат",
            first_name="Третий",
            source="manual"
        )

        db_session.add_all([candidate1, candidate2, candidate3])
        await db_session.flush()

        # Create applications
        now = datetime.now(timezone.utc)
        app1 = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate1.id,
            vacancy_id=vacancy1.id,
            stage="added",
            created_at=now
        )
        app2 = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate2.id,
            vacancy_id=vacancy2.id,
            stage="interview",
            created_at=now
        )
        app3 = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate3.id,
            vacancy_id=vacancy3.id,
            stage="offer",
            created_at=now
        )

        db_session.add_all([app1, app2, app3])
        await db_session.commit()

        # Test multi-vacancy filter
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"vacancy_id": f"{vacancy1.id},{vacancy2.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        # Should include candidates 1 and 2
        names = {item["full_name"] for item in data["items"]}
        assert "Кандидат Первый" in names
        assert "Кандидат Второй" in names
        assert "Кандидат Третий" not in names

        # Test single vacancy (backward compatibility)
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"vacancy_id": str(vacancy3.id)}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["full_name"] == "Кандидат Третий"

    async def test_multi_stage_filter_with_pool(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test stage filter with multiple values including 'pool' special value"""
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate
        from datetime import datetime, timezone

        # Create vacancy
        vacancy_data = VacancyCreate(name="Test Vacancy", funnel_template="default", team=[admin_user.id])
        vacancy = await create_vacancy(db_session, vacancy_data, admin_user.company_id, admin_user.id)

        # Create candidates
        candidate_in_pool = Candidate(  # No applications - should be in "pool"
            company_id=admin_user.company_id,
            last_name="В",
            first_name="Базе",
            source="manual"
        )
        candidate_added = Candidate(
            company_id=admin_user.company_id,
            last_name="Добавлен",
            first_name="Стадия",
            source="manual"
        )
        candidate_interview = Candidate(
            company_id=admin_user.company_id,
            last_name="Собеседование",
            first_name="Стадия",
            source="manual"
        )
        candidate_rejected = Candidate(
            company_id=admin_user.company_id,
            last_name="Отклонён",
            first_name="Стадия",
            source="manual"
        )

        db_session.add_all([candidate_in_pool, candidate_added, candidate_interview, candidate_rejected])
        await db_session.flush()

        # Create applications (pool candidate has no applications)
        now = datetime.now(timezone.utc)
        app_added = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate_added.id,
            vacancy_id=vacancy.id,
            stage="added",
            created_at=now
        )
        app_interview = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate_interview.id,
            vacancy_id=vacancy.id,
            stage="interview",
            created_at=now
        )
        app_rejected = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate_rejected.id,
            vacancy_id=vacancy.id,
            stage="rejected",
            created_at=now
        )

        db_session.add_all([app_added, app_interview, app_rejected])
        await db_session.commit()

        # Test pool filter - should include only candidate without applications
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"stage": "pool"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["full_name"] == "В Базе"

        # Test multi-stage filter (real stages)
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"stage": "added,interview"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        names = {item["full_name"] for item in data["items"]}
        assert "Добавлен Стадия" in names
        assert "Собеседование Стадия" in names
        assert "В Базе" not in names
        assert "Отклонён Стадия" not in names

        # Test combining pool with real stages
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"stage": "pool,added"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        names = {item["full_name"] for item in data["items"]}
        assert "В Базе" in names          # From pool
        assert "Добавлен Стадия" in names  # From added stage
        assert "Собеседование Стадия" not in names
        assert "Отклонён Стадия" not in names

        # Test single stage (backward compatibility)
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"stage": "rejected"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["full_name"] == "Отклонён Стадия"

    async def test_multi_tags_filter(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test tags filter with multiple values"""
        from app.models import CandidateTag

        # Create tags
        tag1 = Tag(name="Python", company_id=admin_user.company_id)
        tag2 = Tag(name="React", company_id=admin_user.company_id)
        tag3 = Tag(name="Senior", company_id=admin_user.company_id)

        db_session.add_all([tag1, tag2, tag3])
        await db_session.flush()

        # Create candidates
        candidate1 = Candidate(
            company_id=admin_user.company_id,
            last_name="Питонист",
            first_name="Иван",
            source="manual"
        )
        candidate2 = Candidate(
            company_id=admin_user.company_id,
            last_name="Реактер",
            first_name="Пётр",
            source="manual"
        )
        candidate3 = Candidate(
            company_id=admin_user.company_id,
            last_name="Сениор",
            first_name="Алексей",
            source="manual"
        )
        candidate4 = Candidate(  # No tags
            company_id=admin_user.company_id,
            last_name="Без",
            first_name="Тегов",
            source="manual"
        )

        db_session.add_all([candidate1, candidate2, candidate3, candidate4])
        await db_session.flush()

        # Create candidate-tag relations
        db_session.add_all([
            CandidateTag(candidate_id=candidate1.id, tag_id=tag1.id),  # Python
            CandidateTag(candidate_id=candidate2.id, tag_id=tag2.id),  # React
            CandidateTag(candidate_id=candidate3.id, tag_id=tag3.id),  # Senior
        ])
        await db_session.commit()

        # Test multi-tags filter
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"tags": f"{tag1.id},{tag2.id}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        names = {item["full_name"] for item in data["items"]}
        assert "Питонист Иван" in names
        assert "Реактер Пётр" in names
        assert "Сениор Алексей" not in names
        assert "Без Тегов" not in names

        # Test single tag (backward compatibility)
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"tags": str(tag3.id)}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["full_name"] == "Сениор Алексей"

    async def test_invalid_uuids_in_filters(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test that invalid UUIDs in vacancy_id and tags don't cause 422 errors"""
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate
        from app.models import CandidateTag
        from datetime import datetime, timezone

        # Create valid data
        vacancy_data = VacancyCreate(name="Test Vacancy", funnel_template="default", team=[admin_user.id])
        vacancy = await create_vacancy(db_session, vacancy_data, admin_user.company_id, admin_user.id)

        tag = Tag(name="TestTag", company_id=admin_user.company_id)
        db_session.add(tag)
        await db_session.flush()

        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name="Тестовый",
            first_name="Кандидат",
            source="manual"
        )
        db_session.add(candidate)
        await db_session.flush()

        # Create application and tag relation
        app = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate.id,
            vacancy_id=vacancy.id,
            stage="added",
            created_at=datetime.now(timezone.utc)
        )
        candidate_tag = CandidateTag(candidate_id=candidate.id, tag_id=tag.id)
        db_session.add_all([app, candidate_tag])
        await db_session.commit()

        # Test invalid UUIDs in vacancy_id - should not cause 422
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"vacancy_id": "invalid,also-invalid"}
        )

        assert response.status_code == 200  # Not 422
        data = response.json()
        assert data["total"] == 0  # No matches for invalid UUIDs

        # Test mixed valid/invalid UUIDs in vacancy_id
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"vacancy_id": f"invalid,{vacancy.id},also-invalid"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1  # Should find the one with valid UUID
        assert data["items"][0]["full_name"] == "Тестовый Кандидат"

        # Test invalid UUIDs in tags
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"tags": "not-a-uuid,another-invalid"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

        # Test mixed valid/invalid UUIDs in tags
        response = await async_client.get(
            "/api/v1/candidates",
            headers=auth_headers,
            params={"tags": f"invalid,{tag.id},also-invalid"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["full_name"] == "Тестовый Кандидат"

    async def test_backward_compatibility_single_values(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test that single values (without commas) still work as before"""
        from app.services.vacancy import create_vacancy
        from app.schemas.vacancy import VacancyCreate
        from app.models import CandidateTag
        from datetime import datetime, timezone

        # Setup test data
        vacancy_data = VacancyCreate(name="Single Test", funnel_template="default", team=[admin_user.id])
        vacancy = await create_vacancy(db_session, vacancy_data, admin_user.company_id, admin_user.id)

        tag = Tag(name="SingleTag", company_id=admin_user.company_id)
        db_session.add(tag)
        await db_session.flush()

        candidate = Candidate(
            company_id=admin_user.company_id,
            last_name="Единственный",
            first_name="Кандидат",
            source="hh"
        )
        db_session.add(candidate)
        await db_session.flush()

        app = Application(
            company_id=admin_user.company_id,
            candidate_id=candidate.id,
            vacancy_id=vacancy.id,
            stage="interview",
            created_at=datetime.now(timezone.utc)
        )
        candidate_tag = CandidateTag(candidate_id=candidate.id, tag_id=tag.id)
        db_session.add_all([app, candidate_tag])
        await db_session.commit()

        # Test all single-value filters still work
        for param, value in [
            ("source", "hh"),
            ("vacancy_id", str(vacancy.id)),
            ("stage", "interview"),
            ("tags", str(tag.id)),
        ]:
            response = await async_client.get(
                "/api/v1/candidates",
                headers=auth_headers,
                params={param: value}
            )

            assert response.status_code == 200, f"Failed for {param}={value}"
            data = response.json()
            assert data["total"] == 1, f"Expected 1 result for {param}={value}"
            assert data["items"][0]["full_name"] == "Единственный Кандидат"