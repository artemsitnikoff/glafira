import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError, InvalidMentionError
from ..models import Candidate, Comment, User, Event
from ..schemas.comment import CommentOut, CommentCreate
from ..services.audit import audit


# Regex for email mentions
EMAIL_REGEX = re.compile(r'@([\w.+-]+@[\w-]+\.[\w.-]+)')


def _extract_mentions(text: str) -> list[str]:
    """Extract email addresses from @mentions in text"""
    matches = EMAIL_REGEX.findall(text)
    return matches


async def _resolve_mentions(
    session: AsyncSession,
    emails: list[str],
    company_id: UUID
) -> list[UUID]:
    """Resolve email addresses to user IDs within company"""
    if not emails:
        return []

    # Find users by emails in the same company
    result = await session.execute(
        select(User.id, User.email)
        .where(
            User.email.in_(emails),
            User.company_id == company_id,
            User.is_active == True
        )
    )
    user_map = {row.email: row.id for row in result}

    # Check for invalid mentions
    invalid_mentions = []
    user_ids = []

    for email in emails:
        if email in user_map:
            user_ids.append(user_map[email])
        else:
            invalid_mentions.append({
                "field": "mentions",
                "message": f"email {email} не найден"
            })

    if invalid_mentions:
        raise InvalidMentionError(details=invalid_mentions)

    return user_ids


async def get_candidate_comments(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID,
    application_id: UUID | None = None
) -> list[CommentOut]:
    """Get comments for candidate"""
    # Verify candidate exists
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    # Build query
    filters = [Comment.candidate_id == candidate_id]
    if application_id:
        filters.append(Comment.application_id == application_id)

    from sqlalchemy import and_
    # Автор берётся одним запросом (JOIN), без отдельного SELECT на каждый комментарий (N+1).
    result = await session.execute(
        select(Comment, User.full_name, User.role)
        .join(User, Comment.author_user_id == User.id)
        .where(and_(*filters))
        .order_by(Comment.created_at.desc())
    )
    rows = result.all()

    # Convert to CommentOut
    items = []
    for comment, author_name, author_role in rows:
        items.append(CommentOut(
            id=comment.id,
            author_name=author_name,
            author_role=author_role,
            body=comment.body,
            mentions=comment.mentions or [],
            created_at=comment.created_at
        ))

    return items


async def create_comment(
    session: AsyncSession,
    candidate_id: UUID,
    comment_data: CommentCreate,
    company_id: UUID,
    actor_user_id: UUID
) -> CommentOut:
    """Create comment with @mentions parsing"""
    # Verify candidate exists
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    # Extract and resolve mentions
    mentioned_emails = _extract_mentions(comment_data.body)
    mentioned_user_ids = await _resolve_mentions(session, mentioned_emails, company_id)

    now = datetime.now(timezone.utc)
    comment = Comment(
        company_id=company_id,
        candidate_id=candidate_id,
        application_id=comment_data.application_id,
        author_user_id=actor_user_id,
        body=comment_data.body,
        mentions=[str(uid) for uid in mentioned_user_ids],
        created_at=now,
    )

    session.add(comment)

    # Audit
    await audit(
        session,
        action="create_comment",
        entity_type="comment",
        entity_id=comment.id,
        after={
            "body": comment_data.body[:100] + "..." if len(comment_data.body) > 100 else comment_data.body,
            "mentions_count": len(mentioned_user_ids)
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    # Событие для ленты «Все действия» (Event != audit — лента читает таблицу events)
    body_preview = (
        comment_data.body[:80] + "…" if len(comment_data.body) > 80 else comment_data.body
    )
    session.add(
        Event(
            company_id=company_id,
            type="comment",
            actor_type="human",
            actor_user_id=actor_user_id,
            text=f"Комментарий: {body_preview}",
            candidate_id=candidate_id,
        )
    )

    await session.flush()

    # Get author info for response
    author_result = await session.execute(
        select(User.full_name, User.role).where(User.id == actor_user_id)
    )
    author = author_result.one()

    return CommentOut(
        id=comment.id,
        author_name=author.full_name,
        author_role=author.role,
        body=comment.body,
        mentions=comment.mentions or [],
        created_at=comment.created_at
    )