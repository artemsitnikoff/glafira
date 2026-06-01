"""CRUD тегов компании (управление на странице Настройки → Теги).

Назначение/снятие тега кандидату — отдельно (services/candidate.py:
add_candidate_tag / remove_candidate_tag). Здесь — только сами теги.
"""

import re
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Tag, CandidateTag
from ...core.errors import ValidationError, NotFoundError, ConflictError
from ..audit import audit

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Название тега обязательно")
    if len(name) > 80:
        raise ValidationError("Название тега — не больше 80 символов")
    return name


def _clean_color(color) -> str | None:
    color = (color or "").strip() or None
    if color and not HEX_RE.match(color):
        raise ValidationError("Цвет должен быть в формате #RRGGBB")
    return color


async def _get(session: AsyncSession, company_id: UUID, tag_id: UUID) -> Tag:
    tag = (
        await session.execute(
            select(Tag).where(Tag.id == tag_id, Tag.company_id == company_id)
        )
    ).scalar_one_or_none()
    if not tag:
        raise NotFoundError("Тег")
    return tag


async def _ensure_name_unique(
    session: AsyncSession, company_id: UUID, name: str, exclude_id: UUID | None = None
) -> None:
    stmt = select(Tag).where(
        Tag.company_id == company_id,
        func.lower(Tag.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(Tag.id != exclude_id)
    if (await session.execute(stmt)).scalar_one_or_none():
        raise ConflictError(f"Тег «{name}» уже существует")


def _to_manage(tag: Tag, usage_count: int) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
        "usage_count": usage_count,
        "created_at": tag.created_at,
    }


async def list_tags_with_counts(session: AsyncSession, company_id: UUID) -> list[dict]:
    """Все теги компании с числом кандидатов, на которых тег навешен."""
    stmt = (
        select(Tag, func.count(CandidateTag.id))
        .outerjoin(CandidateTag, CandidateTag.tag_id == Tag.id)
        .where(Tag.company_id == company_id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    rows = (await session.execute(stmt)).all()
    return [_to_manage(tag, count) for tag, count in rows]


async def get_tag_manage(session: AsyncSession, company_id: UUID, tag_id: UUID) -> dict:
    tag = await _get(session, company_id, tag_id)
    count = (
        await session.execute(
            select(func.count(CandidateTag.id)).where(CandidateTag.tag_id == tag_id)
        )
    ).scalar() or 0
    return _to_manage(tag, count)


async def create_tag(
    session: AsyncSession, company_id: UUID, user_id: UUID, *, name: str, color
) -> Tag:
    name = _clean_name(name)
    color = _clean_color(color)
    await _ensure_name_unique(session, company_id, name)

    tag = Tag(company_id=company_id, name=name, color=color)
    session.add(tag)
    await session.flush()

    await audit(
        session,
        action="create_tag",
        entity_type="tag",
        entity_id=tag.id,
        after={"name": name, "color": color},
        actor_user_id=user_id,
        company_id=company_id,
    )
    return tag


async def update_tag(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    tag_id: UUID,
    *,
    name=None,
    color=None,
) -> Tag:
    tag = await _get(session, company_id, tag_id)
    before = {"name": tag.name, "color": tag.color}

    if name is not None:
        clean = _clean_name(name)
        await _ensure_name_unique(session, company_id, clean, exclude_id=tag_id)
        tag.name = clean
    if color is not None:
        tag.color = _clean_color(color)

    await session.flush()
    await audit(
        session,
        action="update_tag",
        entity_type="tag",
        entity_id=tag.id,
        before=before,
        after={"name": tag.name, "color": tag.color},
        actor_user_id=user_id,
        company_id=company_id,
    )
    return tag


async def delete_tag(
    session: AsyncSession, company_id: UUID, user_id: UUID, tag_id: UUID
) -> None:
    tag = await _get(session, company_id, tag_id)
    name = tag.name

    # Явно снимаем тег со всех кандидатов (не полагаемся на relationship-cascade;
    # БД-уровень FK тоже CASCADE, но делаем детерминированно в рамках сессии).
    await session.execute(delete(CandidateTag).where(CandidateTag.tag_id == tag_id))
    await session.delete(tag)
    await session.flush()

    await audit(
        session,
        action="delete_tag",
        entity_type="tag",
        entity_id=tag_id,
        before={"name": name},
        actor_user_id=user_id,
        company_id=company_id,
    )
