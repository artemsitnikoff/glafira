"""Tests for medium-level fixes from code review"""

import pytest
import uuid
from uuid import UUID

from datetime import datetime, timezone, date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import User, Company, Candidate, Vacancy, VacancyStage, Application, Event, Employee
from app.services.user import create_user
from app.services.candidate import assign_candidate_to_vacancy
from app.schemas.user import UserCreate
from app.core.security import get_password_hash
from app.core.errors import ConflictError, ValidationError


@pytest.fixture
async def second_company_user(db_session: AsyncSession) -> User:
    """Create user from different company for isolation tests"""
    company2 = Company(id=uuid.uuid4(), name="Other Company")
    db_session.add(company2)
    await db_session.flush()

    user2 = User(
        company_id=company2.id,
        email="other@company.com",
        password_hash=get_password_hash("Test123!"),
        full_name="Other User",
        role="admin",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.commit()
    await db_session.refresh(user2)
    return user2


@pytest.fixture
async def test_vacancy(db_session: AsyncSession, admin_user: User) -> Vacancy:
    """Create test vacancy"""
    vacancy = Vacancy(
        company_id=admin_user.company_id,
        name="Test Vacancy",
        city="Москва",
        positions_count=1,
        employment_type="full_time",
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest.fixture
async def vacancy_with_custom_stage(db_session: AsyncSession, test_vacancy: Vacancy, admin_user: User) -> tuple[Vacancy, VacancyStage]:
    """Create vacancy with custom stage"""
    custom_stage = VacancyStage(
        company_id=admin_user.company_id,
        vacancy_id=test_vacancy.id,
        stage_key="custom_test",
        label="Custom Test Stage",
        order_index=5,
        is_terminal=False,
    )
    db_session.add(custom_stage)
    await db_session.commit()
    await db_session.refresh(custom_stage)
    return test_vacancy, custom_stage


class TestCreateUserEmailUniqueness:
    """Test fix #7: create_user should check email uniqueness before creation"""

    async def test_create_user_success(self, db_session: AsyncSession, admin_user: User):
        """Valid user creation should work"""
        user_data = UserCreate(
            email="new@example.com",
            full_name="New User",
            role="recruiter",
            position="Recruiter"
        )

        user, temp_password = await create_user(
            session=db_session,
            user_data=user_data,
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id
        )

        assert user.email == "new@example.com"
        assert user.full_name == "New User"
        assert user.role == "recruiter"
        assert user.position == "Recruiter"
        assert user.company_id == admin_user.company_id
        assert temp_password is not None
        assert len(temp_password) > 0

    async def test_create_user_duplicate_email_conflict(self, db_session: AsyncSession, admin_user: User):
        """Creating user with existing email should raise ConflictError"""
        # Try to create user with admin's email
        user_data = UserCreate(
            email=admin_user.email,  # This email already exists
            full_name="Duplicate User",
            role="recruiter",
            position="Test"
        )

        with pytest.raises(ConflictError) as exc_info:
            await create_user(
                session=db_session,
                user_data=user_data,
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id
            )

        assert "Пользователь с таким email уже существует" in str(exc_info.value)

    async def test_create_user_duplicate_email_cross_company(self, db_session: AsyncSession, admin_user: User, second_company_user: User):
        """Email uniqueness is global across companies"""
        user_data = UserCreate(
            email=admin_user.email,  # Email from first company
            full_name="Cross Company User",
            role="admin",
            position="Manager"
        )

        # Try to create in second company with email from first company
        with pytest.raises(ConflictError) as exc_info:
            await create_user(
                session=db_session,
                user_data=user_data,
                company_id=second_company_user.company_id,
                actor_user_id=second_company_user.id
            )

        assert "Пользователь с таким email уже существует" in str(exc_info.value)


class TestAssignCandidateCustomStages:
    """Test fix #8: assign_candidate_to_vacancy should accept custom stages"""

    async def test_assign_to_system_stage_success(self, db_session: AsyncSession, test_candidate: Candidate, test_vacancy: Vacancy, admin_user: User):
        """Assigning to system stage should work"""
        await assign_candidate_to_vacancy(
            session=db_session,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="selected",  # System stage
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id
        )

        # Should complete without error
        await db_session.commit()

    async def test_assign_to_custom_stage_success(self, db_session: AsyncSession, test_candidate: Candidate, vacancy_with_custom_stage: tuple[Vacancy, VacancyStage], admin_user: User):
        """Assigning to custom stage should work"""
        test_vacancy, custom_stage = vacancy_with_custom_stage

        await assign_candidate_to_vacancy(
            session=db_session,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage=custom_stage.stage_key,  # Custom stage
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id
        )

        # Should complete without error
        await db_session.commit()

    async def test_assign_to_nonexistent_stage_error(self, db_session: AsyncSession, test_candidate: Candidate, test_vacancy: Vacancy, admin_user: User):
        """Assigning to non-existent stage should raise ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            await assign_candidate_to_vacancy(
                session=db_session,
                candidate_id=test_candidate.id,
                vacancy_id=test_vacancy.id,
                stage="nonexistent_stage",  # Neither system nor custom stage
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id
            )

        assert "Неверная стадия: nonexistent_stage" in str(exc_info.value)

    async def test_assign_to_other_vacancy_custom_stage_error(self, db_session: AsyncSession, test_candidate: Candidate, test_vacancy: Vacancy, vacancy_with_custom_stage: tuple[Vacancy, VacancyStage], admin_user: User):
        """Custom stage of another vacancy should not be accepted"""
        other_vacancy, custom_stage = vacancy_with_custom_stage

        # Try to assign to test_vacancy using custom stage from other_vacancy
        with pytest.raises(ValidationError) as exc_info:
            await assign_candidate_to_vacancy(
                session=db_session,
                candidate_id=test_candidate.id,
                vacancy_id=test_vacancy.id,  # Different vacancy
                stage=custom_stage.stage_key,  # Custom stage from other vacancy
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id
            )

        assert f"Неверная стадия: {custom_stage.stage_key}" in str(exc_info.value)

class TestAssignCreatesEvent:
    """#10: assign_candidate_to_vacancy creates an Event for the activity feed"""

    async def test_assign_creates_new_event(
        self, db_session: AsyncSession, admin_user: User, test_candidate: Candidate, test_vacancy: Vacancy
    ):
        await assign_candidate_to_vacancy(
            session=db_session,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="selected",
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id,
        )

        result = await db_session.execute(
            select(Event).where(
                Event.candidate_id == test_candidate.id,
                Event.type == "new",
            )
        )
        event = result.scalar_one_or_none()
        assert event is not None
        assert event.vacancy_id == test_vacancy.id
        assert event.actor_type == "human"
        assert test_vacancy.name in event.text


class TestEmployeeApplicationIdUnique:
    """#17: UNIQUE on Employee.application_id prevents double-hire from one application"""

    async def test_duplicate_application_id_raises(
        self, db_session: AsyncSession, admin_user: User, test_candidate: Candidate, test_vacancy: Vacancy
    ):
        application = Application(
            company_id=admin_user.company_id,
            candidate_id=test_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="hired",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(application)
        await db_session.flush()

        emp1 = Employee(
            company_id=admin_user.company_id,
            candidate_id=test_candidate.id,
            application_id=application.id,
            full_name="Emp One",
            start_date=date.today(),
        )
        db_session.add(emp1)
        await db_session.flush()

        emp2 = Employee(
            company_id=admin_user.company_id,
            candidate_id=test_candidate.id,
            application_id=application.id,  # SAME application_id → UNIQUE violation
            full_name="Emp Two",
            start_date=date.today(),
        )
        db_session.add(emp2)
        with pytest.raises(IntegrityError):
            await db_session.flush()
