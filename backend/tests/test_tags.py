"""Тесты CRUD тегов (Настройки → Теги) + каскад при удалении."""

import uuid

import pytest

from app.services.settings import tags as tags_svc
from app.core.errors import ValidationError, NotFoundError, ConflictError
from app.models import Candidate, CandidateTag, Tag
from sqlalchemy import select, func


async def _candidate(db_session, company_id, name="Иван"):
    c = Candidate(company_id=company_id, first_name=name, last_name="Тест", source="hh")
    db_session.add(c)
    await db_session.flush()
    return c


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_tag(db_session, admin_user):
    tag = await tags_svc.create_tag(
        db_session, admin_user.company_id, admin_user.id, name="  Python  ", color="#2A8AF0"
    )
    assert tag.name == "Python"  # trimmed
    assert tag.color == "#2A8AF0"


@pytest.mark.asyncio
async def test_create_tag_validation(db_session, admin_user):
    with pytest.raises(ValidationError):
        await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="  ", color=None)
    with pytest.raises(ValidationError):
        await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="X", color="red")


@pytest.mark.asyncio
async def test_create_tag_duplicate_name_case_insensitive(db_session, admin_user):
    await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="Senior", color=None)
    with pytest.raises(ConflictError):
        await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="senior", color=None)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_tag_rename_and_color(db_session, admin_user):
    tag = await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="Old", color=None)
    updated = await tags_svc.update_tag(
        db_session, admin_user.company_id, admin_user.id, tag.id, name="New", color="#10B981"
    )
    assert updated.name == "New"
    assert updated.color == "#10B981"


@pytest.mark.asyncio
async def test_update_tag_duplicate_name_conflict(db_session, admin_user):
    await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="A", color=None)
    b = await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="B", color=None)
    with pytest.raises(ConflictError):
        await tags_svc.update_tag(db_session, admin_user.company_id, admin_user.id, b.id, name="a")


@pytest.mark.asyncio
async def test_update_tag_not_found(db_session, admin_user):
    with pytest.raises(NotFoundError):
        await tags_svc.update_tag(
            db_session, admin_user.company_id, admin_user.id, uuid.uuid4(), name="X"
        )


# ---------------------------------------------------------------------------
# list with counts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tags_with_counts(db_session, admin_user):
    t1 = await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="Used", color=None)
    await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="Unused", color=None)

    cand = await _candidate(db_session, admin_user.company_id)
    db_session.add(CandidateTag(candidate_id=cand.id, tag_id=t1.id, company_id=admin_user.company_id))
    await db_session.flush()

    rows = await tags_svc.list_tags_with_counts(db_session, admin_user.company_id)
    by_name = {r["name"]: r for r in rows}
    assert by_name["Used"]["usage_count"] == 1
    assert by_name["Unused"]["usage_count"] == 0
    # отсортировано по имени
    assert [r["name"] for r in rows] == ["Unused", "Used"]


# ---------------------------------------------------------------------------
# delete — каскадом снимает с кандидатов
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_tag_cascades_candidate_tags(db_session, admin_user):
    tag = await tags_svc.create_tag(db_session, admin_user.company_id, admin_user.id, name="ToDelete", color=None)
    cand = await _candidate(db_session, admin_user.company_id)
    db_session.add(CandidateTag(candidate_id=cand.id, tag_id=tag.id, company_id=admin_user.company_id))
    await db_session.flush()

    await tags_svc.delete_tag(db_session, admin_user.company_id, admin_user.id, tag.id)

    # тег удалён
    with pytest.raises(NotFoundError):
        await tags_svc.get_tag_manage(db_session, admin_user.company_id, tag.id)
    # связи сняты
    remaining = (
        await db_session.execute(
            select(func.count(CandidateTag.id)).where(CandidateTag.tag_id == tag.id)
        )
    ).scalar()
    assert remaining == 0
