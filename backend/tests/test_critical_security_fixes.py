"""Tests for critical security fixes C3 and C4"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, User, Candidate, Vacancy, Application, VacancyStage, Message
from app.core.security import get_password_hash
from app.core.errors import NotFoundError, ValidationError
from app.schemas.message import MessageCreate
from app.schemas.application import MoveRequest
from app.services.message import send_message
from app.services.application import move_application


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
async def test_application(
    db_session: AsyncSession, admin_user: User, test_candidate: Candidate, test_vacancy: Vacancy
) -> Application:
    """Create test application"""
    application = Application(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        vacancy_id=test_vacancy.id,
        stage="added",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest.fixture
async def custom_stage(
    db_session: AsyncSession, admin_user: User, test_vacancy: Vacancy
) -> VacancyStage:
    """Create custom stage for test vacancy"""
    stage = VacancyStage(
        company_id=admin_user.company_id,
        vacancy_id=test_vacancy.id,
        stage_key="custom_stage",
        label="Custom Stage",
        order_index=10,
        is_terminal=False,
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    return stage


class TestC3SendMessageIDOR:
    """C3: send_message validates application_id ownership"""

    async def test_send_message_with_foreign_application_fails(
        self, db_session: AsyncSession, admin_user: User, test_candidate: Candidate,
        second_company_user: User
    ):
        """Test that send_message rejects application_id from different company"""
        # Create foreign company's vacancy and application
        foreign_vacancy = Vacancy(
            company_id=second_company_user.company_id,
            name="Foreign Vacancy",
            city="Москва",
            positions_count=1,
            employment_type="full_time",
        )
        db_session.add(foreign_vacancy)
        await db_session.flush()

        foreign_candidate = Candidate(
            company_id=second_company_user.company_id,
            last_name="Foreign",
            first_name="Candidate",
            source="manual",
        )
        db_session.add(foreign_candidate)
        await db_session.flush()

        foreign_application = Application(
            company_id=second_company_user.company_id,
            candidate_id=foreign_candidate.id,
            vacancy_id=foreign_vacancy.id,
            stage="added",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(foreign_application)
        await db_session.commit()

        # Try to send message with foreign application_id
        message_data = MessageCreate(
            channel="telegram",
            body="Test message",
            application_id=foreign_application.id,
        )

        with pytest.raises(NotFoundError) as exc_info:
            await send_message(
                session=db_session,
                candidate_id=test_candidate.id,
                message_data=message_data,
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id,
            )

        assert "Заявка" in str(exc_info.value)

        # Verify no message was created
        from sqlalchemy import select, func
        count_result = await db_session.execute(
            select(func.count(Message.id)).where(Message.candidate_id == test_candidate.id)
        )
        assert count_result.scalar() == 0

    async def test_send_message_with_wrong_candidate_application_fails(
        self, db_session: AsyncSession, admin_user: User, test_candidate: Candidate, test_vacancy: Vacancy
    ):
        """Test that send_message rejects application_id belonging to different candidate of same company"""
        # Create another candidate in same company
        another_candidate = Candidate(
            company_id=admin_user.company_id,
            last_name="Another",
            first_name="Candidate",
            source="manual",
        )
        db_session.add(another_candidate)
        await db_session.flush()

        # Create application for another candidate
        another_application = Application(
            company_id=admin_user.company_id,
            candidate_id=another_candidate.id,
            vacancy_id=test_vacancy.id,
            stage="added",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(another_application)
        await db_session.commit()

        # Try to send message to test_candidate with another_candidate's application
        message_data = MessageCreate(
            channel="telegram",
            body="Test message",
            application_id=another_application.id,
        )

        with pytest.raises(NotFoundError) as exc_info:
            await send_message(
                session=db_session,
                candidate_id=test_candidate.id,
                message_data=message_data,
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id,
            )

        assert "Заявка" in str(exc_info.value)

    async def test_send_message_with_own_application_succeeds(
        self, db_session: AsyncSession, admin_user: User, test_candidate: Candidate, test_application: Application
    ):
        """Test that send_message works with valid application_id"""
        message_data = MessageCreate(
            channel="telegram",
            body="Test message",
            application_id=test_application.id,
        )

        result = await send_message(
            session=db_session,
            candidate_id=test_candidate.id,
            message_data=message_data,
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id,
        )

        assert result.application_context is not None
        assert "Test Vacancy" in result.application_context
        assert result.vacancy_id == test_application.vacancy_id

    async def test_send_message_without_application_succeeds(
        self, db_session: AsyncSession, admin_user: User, test_candidate: Candidate
    ):
        """Test that send_message works without application_id"""
        message_data = MessageCreate(
            channel="telegram",
            body="Test message",
            application_id=None,
        )

        result = await send_message(
            session=db_session,
            candidate_id=test_candidate.id,
            message_data=message_data,
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id,
        )

        assert result.application_context is None
        assert result.vacancy_id is None


class TestC4MoveApplicationStageValidation:
    """C4: move_application validates to_stage is valid for vacancy"""

    async def test_move_to_existing_system_stage_succeeds(
        self, db_session: AsyncSession, admin_user: User, test_application: Application
    ):
        """Test that move to existing system stage works"""
        move_data = MoveRequest(to_stage="interview")

        result = await move_application(
            session=db_session,
            application_id=test_application.id,
            move_data=move_data,
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id,
        )

        assert result.stage == "interview"

    async def test_move_to_hired_creates_employee(
        self, db_session: AsyncSession, admin_user: User, test_application: Application
    ):
        """Test that move to 'hired' still works and creates Employee"""
        move_data = MoveRequest(to_stage="hired")

        result = await move_application(
            session=db_session,
            application_id=test_application.id,
            move_data=move_data,
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id,
        )

        assert result.stage == "hired"

        # Check that Employee was created
        from app.models import Employee
        from sqlalchemy import select
        employee_result = await db_session.execute(
            select(Employee).where(Employee.candidate_id == test_application.candidate_id)
        )
        employee = employee_result.scalar_one_or_none()
        assert employee is not None

    async def test_move_to_custom_stage_succeeds(
        self, db_session: AsyncSession, admin_user: User, test_application: Application, custom_stage: VacancyStage
    ):
        """Test that move to custom stage of this vacancy works"""
        move_data = MoveRequest(to_stage="custom_stage")

        result = await move_application(
            session=db_session,
            application_id=test_application.id,
            move_data=move_data,
            company_id=admin_user.company_id,
            actor_user_id=admin_user.id,
        )

        assert result.stage == "custom_stage"

    async def test_move_to_invalid_stage_fails(
        self, db_session: AsyncSession, admin_user: User, test_application: Application
    ):
        """Test that move to invalid stage (typo) fails"""
        move_data = MoveRequest(to_stage="interviewx")  # typo

        with pytest.raises(ValidationError) as exc_info:
            await move_application(
                session=db_session,
                application_id=test_application.id,
                move_data=move_data,
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id,
            )

        assert "Неверный этап: interviewx" in str(exc_info.value)

        # Verify application stage was not changed
        await db_session.refresh(test_application)
        assert test_application.stage == "added"  # original stage

    async def test_move_to_foreign_custom_stage_fails(
        self, db_session: AsyncSession, admin_user: User, test_application: Application, second_company_user: User
    ):
        """Test that move to custom stage of different vacancy fails"""
        # Create foreign vacancy with custom stage
        foreign_vacancy = Vacancy(
            company_id=admin_user.company_id,  # same company but different vacancy
            name="Foreign Vacancy",
            city="Москва",
            positions_count=1,
            employment_type="full_time",
        )
        db_session.add(foreign_vacancy)
        await db_session.flush()

        foreign_stage = VacancyStage(
            company_id=admin_user.company_id,
            vacancy_id=foreign_vacancy.id,
            stage_key="foreign_custom",
            label="Foreign Custom",
            order_index=10,
            is_terminal=False,
        )
        db_session.add(foreign_stage)
        await db_session.commit()

        # Try to move to foreign custom stage
        move_data = MoveRequest(to_stage="foreign_custom")

        with pytest.raises(ValidationError) as exc_info:
            await move_application(
                session=db_session,
                application_id=test_application.id,
                move_data=move_data,
                company_id=admin_user.company_id,
                actor_user_id=admin_user.id,
            )

        assert "Неверный этап: foreign_custom" in str(exc_info.value)