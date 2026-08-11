"""Тесты импорта комментариев работодателя с hh в блок «Комментарии» кандидата.

Мокается hh-клиент (живой токен не дёргается). Проверяем: импорт создаёт
Comment(source='hh', author_user_id=None, author_name_ext); повторный синк НЕ двоит
(дедуп по external_id + applicant_id из кэша, resume не перечитывается); company-
изоляция (чужой кандидат не трогается); get_candidate_comments отдаёт и наши, и hh
(outer join не падает на nullable author); наш create_comment остаётся source='manual';
кандидат без hh-резюме → {imported:0} без ошибки.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models import Candidate, Comment, Company, User
from app.schemas.comment import CommentCreate
from app.services.comment import create_comment, get_candidate_comments
from app.services.integrations.hh.comments import sync_candidate_hh_comments

_SYNC = "app.services.integrations.hh.comments"


async def _make_hh_candidate(db_session, company_id, resume_id="resume_hex_1"):
    cand = Candidate(
        company_id=company_id,
        last_name="Хэдхантеров",
        first_name="Кандидат",
        source="hh",
        external_id=resume_id,
    )
    db_session.add(cand)
    await db_session.commit()
    await db_session.refresh(cand)
    return cand


def _comments_page(items, pages=1):
    return {"items": items, "found": len(items), "page": 0, "pages": pages, "per_page": 100}


@pytest.mark.asyncio
async def test_sync_imports_hh_comments(db_session, test_company, admin_user):
    cand = await _make_hh_candidate(db_session, test_company.id)

    resume = {"id": "resume_hex_1", "owner": {"id": 555111}}
    page = _comments_page([
        {
            "id": 9001,
            "text": "Сильный кандидат, звонил — готов выйти",
            "created_at": "2026-07-01T10:00:00+03:00",
            "author": {"first_name": "Иван", "last_name": "Работодатель"},
            "access_type": {"id": "owner"},
        },
        {
            "id": 9002,
            "text": "Уточнить зарплатные ожидания",
            "created_at": "2026-07-02T12:30:00+03:00",
            "author": {"full_name": "HR Отдел"},
            "access_type": {"id": "coworkers"},
        },
    ])

    with patch(f"{_SYNC}.get_valid_access_token", new_callable=AsyncMock, return_value="tok"), \
         patch(f"{_SYNC}.hh_client.get_resume_by_id", new_callable=AsyncMock, return_value=resume) as m_resume, \
         patch(f"{_SYNC}.hh_client.get_applicant_comments", new_callable=AsyncMock, return_value=page):
        result = await sync_candidate_hh_comments(
            db_session, company_id=test_company.id, candidate_id=cand.id
        )
    await db_session.commit()

    assert result == {"imported": 2}
    m_resume.assert_awaited_once()  # applicant_id резолвился один раз

    rows = (await db_session.execute(
        select(Comment).where(Comment.candidate_id == cand.id).order_by(Comment.external_id)
    )).scalars().all()
    assert len(rows) == 2
    for r in rows:
        assert r.source == "hh"
        assert r.author_user_id is None
        assert r.company_id == test_company.id
        assert r.external_id in ("9001", "9002")
    assert rows[0].author_name_ext == "Работодатель Иван"
    assert rows[1].author_name_ext == "HR Отдел"

    # applicant_id закэширован в extra → следующий синк не пойдёт за резюме
    await db_session.refresh(cand)
    assert cand.extra.get("hh_applicant_id") == "555111"


@pytest.mark.asyncio
async def test_sync_dedup_no_double(db_session, test_company, admin_user):
    cand = await _make_hh_candidate(db_session, test_company.id)
    resume = {"id": "resume_hex_1", "owner": {"id": 42}}
    page = _comments_page([
        {"id": 700, "text": "Заметка", "created_at": "2026-07-01T10:00:00+03:00",
         "author": {"full_name": "Рекрутёр"}},
    ])

    with patch(f"{_SYNC}.get_valid_access_token", new_callable=AsyncMock, return_value="tok"), \
         patch(f"{_SYNC}.hh_client.get_resume_by_id", new_callable=AsyncMock, return_value=resume) as m_resume, \
         patch(f"{_SYNC}.hh_client.get_applicant_comments", new_callable=AsyncMock, return_value=page):
        r1 = await sync_candidate_hh_comments(db_session, company_id=test_company.id, candidate_id=cand.id)
        await db_session.commit()
        r2 = await sync_candidate_hh_comments(db_session, company_id=test_company.id, candidate_id=cand.id)
        await db_session.commit()

    assert r1 == {"imported": 1}
    assert r2 == {"imported": 0}  # повторный синк не двоит (дедуп по external_id)
    # applicant_id взят из кэша на втором прогоне → резюме перечитано ровно один раз
    assert m_resume.await_count == 1

    count = (await db_session.execute(
        select(Comment).where(Comment.candidate_id == cand.id)
    )).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_company_isolation(db_session, test_company, admin_user):
    """Кандидат компании A не трогается синком под company_id компании B."""
    cand_a = await _make_hh_candidate(db_session, test_company.id)

    other_company = Company(id=uuid.uuid4(), name="Чужая компания")
    db_session.add(other_company)
    await db_session.commit()

    resume = {"id": "resume_hex_1", "owner": {"id": 1}}
    page = _comments_page([{"id": 1, "text": "x", "author": {"full_name": "y"}}])

    with patch(f"{_SYNC}.get_valid_access_token", new_callable=AsyncMock, return_value="tok") as m_tok, \
         patch(f"{_SYNC}.hh_client.get_resume_by_id", new_callable=AsyncMock, return_value=resume) as m_resume, \
         patch(f"{_SYNC}.hh_client.get_applicant_comments", new_callable=AsyncMock, return_value=page):
        # Синк под ЧУЖОЙ company_id над кандидатом A → он не находится (company-scoped)
        result = await sync_candidate_hh_comments(
            db_session, company_id=other_company.id, candidate_id=cand_a.id
        )
    await db_session.commit()

    assert result == {"imported": 0}
    m_tok.assert_not_awaited()   # до токена/резюме дело не дошло — кандидат не найден
    m_resume.assert_not_awaited()

    rows = (await db_session.execute(
        select(Comment).where(Comment.candidate_id == cand_a.id)
    )).scalars().all()
    assert rows == []  # чужой кандидат не тронут


@pytest.mark.asyncio
async def test_get_comments_mixed_manual_and_hh(db_session, test_company, admin_user, test_candidate):
    """get_candidate_comments отдаёт и наш (author из User), и hh (author из
    author_name_ext); outer join не падает на nullable author."""
    # Наш ручной комментарий
    await create_comment(
        db_session, test_candidate.id, CommentCreate(body="Наш комментарий"),
        test_company.id, admin_user.id,
    )
    # hh-комментарий (без нашего автора)
    db_session.add(Comment(
        company_id=test_company.id,
        candidate_id=test_candidate.id,
        author_user_id=None,
        source="hh",
        external_id="hh_777",
        author_name_ext="Работодатель с hh",
        body="Заметка с hh",
        mentions=[],
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    items = await get_candidate_comments(db_session, test_candidate.id, test_company.id)
    by_source = {c.source: c for c in items}
    assert set(by_source) == {"manual", "hh"}

    assert by_source["manual"].author_name == admin_user.full_name
    assert by_source["manual"].author_role == admin_user.role

    assert by_source["hh"].author_name == "Работодатель с hh"
    assert by_source["hh"].author_role is None  # у hh-заметки роли нет
    assert by_source["hh"].body == "Заметка с hh"


@pytest.mark.asyncio
async def test_create_comment_stays_manual(db_session, test_company, admin_user, test_candidate):
    """Наш POST-комментарий по-прежнему source='manual' и author_user_id=actor."""
    out = await create_comment(
        db_session, test_candidate.id, CommentCreate(body="Обычная заметка"),
        test_company.id, admin_user.id,
    )
    await db_session.commit()
    assert out.source == "manual"

    row = (await db_session.execute(
        select(Comment).where(Comment.id == out.id)
    )).scalar_one()
    assert row.source == "manual"
    assert row.author_user_id == admin_user.id
    assert row.external_id is None


@pytest.mark.asyncio
async def test_sync_no_hh_resume_returns_zero(db_session, test_company, admin_user, test_candidate):
    """Кандидат без hh-резюме (source='manual', нет external_id/hh_resume_id) →
    {imported:0}, hh не дёргается."""
    with patch(f"{_SYNC}.get_valid_access_token", new_callable=AsyncMock) as m_tok, \
         patch(f"{_SYNC}.hh_client.get_resume_by_id", new_callable=AsyncMock) as m_resume, \
         patch(f"{_SYNC}.hh_client.get_applicant_comments", new_callable=AsyncMock) as m_comments:
        result = await sync_candidate_hh_comments(
            db_session, company_id=test_company.id, candidate_id=test_candidate.id
        )
    assert result == {"imported": 0}
    m_tok.assert_not_awaited()
    m_resume.assert_not_awaited()
    m_comments.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_graceful_when_hh_returns_none(db_session, test_company, admin_user):
    """get_applicant_comments вернул None (эндпоинт не пинен / 403) → {imported:0},
    без исключения и без фейковых комментариев."""
    cand = await _make_hh_candidate(db_session, test_company.id)
    resume = {"id": "resume_hex_1", "owner": {"id": 9}}

    with patch(f"{_SYNC}.get_valid_access_token", new_callable=AsyncMock, return_value="tok"), \
         patch(f"{_SYNC}.hh_client.get_resume_by_id", new_callable=AsyncMock, return_value=resume), \
         patch(f"{_SYNC}.hh_client.get_applicant_comments", new_callable=AsyncMock, return_value=None):
        result = await sync_candidate_hh_comments(
            db_session, company_id=test_company.id, candidate_id=cand.id
        )
    await db_session.commit()

    assert result == {"imported": 0}
    rows = (await db_session.execute(
        select(Comment).where(Comment.candidate_id == cand.id)
    )).scalars().all()
    assert rows == []
