"""Тесты админских действий с пользователями: список+фильтры, деактивация, удаление.

Реальные фикстуры conftest (db_session, admin_user — role=admin; regular_user — recruiter).
Без сети. asyncio_mode=auto → декораторы не нужны.
"""

import pytest

from app.models import User, Vacancy
from app.services.user import get_users_paginated, update_user, delete_user
from app.schemas.user import UserUpdate
from app.core.security import get_password_hash
from app.core.errors import ForbiddenError, ConflictError


def _user(company_id, *, email, role="recruiter", full_name="Тест Юзер", is_active=True):
    return User(
        company_id=company_id,
        email=email,
        password_hash=get_password_hash("Glafira2026!"),
        full_name=full_name,
        role=role,
        is_active=is_active,
    )


# --------------------------- список + фильтры ---------------------------

async def test_user_list_filters(db_session, admin_user, regular_user):
    cid = admin_user.company_id

    # поиск по фамилии админа (admin_user.full_name = "Анна Седова")
    r = await get_users_paginated(db_session, cid, search="Седова")
    assert len(r.items) == 1
    assert r.items[0].email == admin_user.email

    # поиск по email
    r = await get_users_paginated(db_session, cid, search="regular@")
    assert len(r.items) == 1
    assert r.items[0].email == regular_user.email

    # фильтр по роли
    r = await get_users_paginated(db_session, cid, role="admin")
    assert len(r.items) == 1 and r.items[0].role == "admin"

    # фильтр активных
    r = await get_users_paginated(db_session, cid, is_active=True)
    assert len(r.items) >= 2


# --------------------------- деактивация ---------------------------

async def test_cannot_deactivate_self(db_session, admin_user):
    with pytest.raises(ForbiddenError):
        await update_user(
            db_session, admin_user.id, UserUpdate(is_active=False),
            admin_user.company_id, admin_user.id,
        )


async def test_cannot_deactivate_last_admin(db_session, admin_user, regular_user):
    # admin_user — единственный активный админ; деактивация другим актором → конфликт
    with pytest.raises(ConflictError):
        await update_user(
            db_session, admin_user.id, UserUpdate(is_active=False),
            admin_user.company_id, regular_user.id,
        )


async def test_can_deactivate_admin_when_multiple(db_session, admin_user):
    admin2 = _user(admin_user.company_id, email="admin2@example.com", role="admin", full_name="Второй Админ")
    db_session.add(admin2)
    await db_session.flush()

    await update_user(
        db_session, admin2.id, UserUpdate(is_active=False),
        admin_user.company_id, admin_user.id,
    )
    await db_session.refresh(admin2)
    assert admin2.is_active is False


# --------------------------- удаление ---------------------------

async def test_cannot_delete_self(db_session, admin_user):
    with pytest.raises(ForbiddenError):
        await delete_user(db_session, admin_user.id, admin_user.company_id, admin_user.id)


async def test_cannot_delete_last_admin(db_session, admin_user, regular_user):
    with pytest.raises(ConflictError):
        await delete_user(db_session, admin_user.id, admin_user.company_id, regular_user.id)


async def test_delete_user_with_dependencies_blocked(db_session, admin_user, regular_user):
    # за recruiter закреплена активная вакансия → удалять нельзя (просим переназначить)
    vac = Vacancy(company_id=admin_user.company_id, name="Тест-вакансия", responsible_user_id=regular_user.id)
    db_session.add(vac)
    await db_session.flush()

    with pytest.raises(ConflictError):
        await delete_user(db_session, regular_user.id, admin_user.company_id, admin_user.id)


async def test_successful_user_deletion(db_session, admin_user):
    victim = _user(admin_user.company_id, email="victim@example.com", role="recruiter")
    db_session.add(victim)
    await db_session.flush()
    vid = victim.id

    await delete_user(db_session, vid, admin_user.company_id, admin_user.id)
    await db_session.flush()
    assert await db_session.get(User, vid) is None
