"""Импорт комментариев работодателя к резюме с hh в блок «Комментарии» кандидата.

Зеркало `services/chats.sync_candidate_hh_inbound`: тянет заметки работодателя к
соискателю на hh и сохраняет их как Comment(source='hh') — read-only, с пометкой
источника. Это ИМПОРТ, а не действие пользователя: Event('comment', actor='human')
и mention-парсинг НЕ пишутся (§2.2), audit не пишется.

Разовый перенос = первый прогон крона `jobs.poll_hh_comments` (идемпотентен по
дедупу external_id). Инкрементальный синк — тот же путь по требованию (on-demand
роут при открытии блока).

⚠️ applicant_id (числовой owner.id резюме) нигде не хранится — резолвится один раз
через get_resume_by_id и кэшируется в candidate.extra['hh_applicant_id']. ⚠️ Резолв
тратит квоту просмотров резюме hh (get_resume_by_id — ПЛАТНО), но ТОЛЬКО при первом
синке кандидата; далее берётся из кэша. Сам applicant_comments — бесплатный.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Candidate, Comment
from . import client as hh_client
from .service import get_hh_token_for_user, view_resume_with_cascade

logger = logging.getLogger(__name__)

# Кап страниц пагинации заметок (защита от бесконечного цикла на кривом ответе).
_MAX_PAGES = 20


def _author_name(author) -> str | None:
    """Собирает отображаемое имя автора-заметки из объекта author hh (форма не пинена
    — читаем защитно несколько возможных ключей)."""
    if not isinstance(author, dict):
        return None
    for key in ("full_name", "name"):
        v = author.get(key)
        if v and str(v).strip():
            return str(v).strip()
    parts = [author.get("last_name"), author.get("first_name"), author.get("middle_name")]
    joined = " ".join(str(p).strip() for p in parts if p and str(p).strip())
    return joined or None


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def _resolve_applicant_id(
    session: AsyncSession,
    candidate: Candidate,
    resume_id: str,
    *,
    company_id: UUID,
    user_id: UUID | None = None,
) -> str | None:
    """applicant_id (owner.id) из кэша extra ИЛИ из полного резюме (с кэшированием).

    ⚠️ Просмотр резюме тратит квоту просмотров hh — потому кэшируем в extra и зовём
    только если applicant_id ещё не известен. Идёт под КАСКАДОМ квоты
    (view_resume_with_cascade): личный токен рекрутёра → общий при исчерпании суточного
    лимита. Любой сбой резолва → None (graceful — блок «Комментарии» не роняем)."""
    cached = (candidate.extra or {}).get("hh_applicant_id")
    if cached:
        return str(cached)

    try:
        resume = await view_resume_with_cascade(
            session, company_id=company_id, user_id=user_id, resume_id=resume_id
        )
    except Exception as exc:
        logger.warning("[hh-comments] резолв applicant_id: сбой resume=%s exc=%s", resume_id, exc)
        return None

    owner = (resume or {}).get("owner") or {}
    applicant_id = owner.get("id")
    if applicant_id is None:
        return None
    applicant_id = str(applicant_id)

    # Кэшируем (JSONB переприсваиваем целиком — мутация dict не отслеживается ORM).
    candidate.extra = {**(candidate.extra or {}), "hh_applicant_id": applicant_id}
    return applicant_id


async def sync_candidate_hh_comments(
    session: AsyncSession,
    *,
    company_id: UUID,
    candidate_id: UUID,
    user_id: UUID | None = None,
) -> dict:
    """Импорт заметок работодателя с hh для ОДНОГО кандидата → {"imported": N}.

    Токен: on-demand-путь из роута передаёт user_id рекрутёра → ЛИЧНЫЙ токен (фолбэк на
    общий). КРОННЫЙ путь (jobs.poll_hh_comments) user_id НЕ передаёт → общий компанийный
    токен. ⚠️ резолв applicant_id (get_resume_by_id) тратит квоту просмотров hh — с личным
    токеном она списывается персонально; но только при ПЕРВОМ синке кандидата (далее кэш).

    Company-scoped ВЕЗДЕ. Дедуп по (company_id, source='hh', external_id) — повторный
    вызов не плодит. Коммит — на вызывающем (роут/крон). Любой недостающий кусок
    (нет hh-резюме / нет токена / нет applicant_id / hh вернул None) → {"imported": 0}
    без исключения (никаких фейков)."""
    candidate = (
        await session.execute(
            select(Candidate).where(
                Candidate.id == candidate_id,
                Candidate.company_id == company_id,
                Candidate.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        return {"imported": 0}

    resume_id = candidate.external_id or (candidate.extra or {}).get("hh_resume_id")
    if not resume_id:
        return {"imported": 0}

    try:
        access_token = await get_hh_token_for_user(
            session, company_id=company_id, user_id=user_id
        )
    except Exception:
        # Сбой рефреша личного токена — тянуть нечего, блок не роняем.
        return {"imported": 0}
    if not access_token:
        # hh не подключён/токен протух — тянуть нечего, блок не роняем.
        return {"imported": 0}

    applicant_id = await _resolve_applicant_id(
        session, candidate, str(resume_id), company_id=company_id, user_id=user_id
    )
    if not applicant_id:
        return {"imported": 0}

    imported = 0
    page = 0
    now = datetime.now(timezone.utc)
    while page < _MAX_PAGES:
        data = await hh_client.get_applicant_comments(
            access_token, applicant_id, page=page, per_page=100
        )
        if not data:
            break
        items = data.get("items") or []
        for item in items:
            raw_id = item.get("id")
            if raw_id is None:
                continue
            ext_id = str(raw_id)

            body = (item.get("text") or "").strip()
            if not body:
                continue

            # Дедуп: company-scoped, среди hh-комментариев по external_id.
            existing = (
                await session.execute(
                    select(Comment.id).where(
                        Comment.company_id == company_id,
                        Comment.source == "hh",
                        Comment.external_id == ext_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue  # уже импортирован — не трогаем (read-only, без churn)

            comment = Comment(
                company_id=company_id,
                candidate_id=candidate_id,
                application_id=None,
                author_user_id=None,  # у заметки с hh нет нашего автора
                source="hh",
                external_id=ext_id,
                author_name_ext=_author_name(item.get("author")),
                body=body,
                mentions=[],
                created_at=_parse_dt(item.get("created_at")) or now,
            )
            # Savepoint: если параллельный процесс (крон + on-demand) вставил тот же
            # external_id между нашим SELECT и INSERT — partial unique index даёт
            # IntegrityError → откатываем ТОЛЬКО этот insert, батч не валим (дедуп-гонка).
            try:
                async with session.begin_nested():
                    session.add(comment)
                    await session.flush()
                imported += 1
            except IntegrityError:
                continue

        # Пагинация: hh отдаёт pages (число страниц). Идём, пока не кончились.
        pages = data.get("pages")
        if not isinstance(pages, int) or page + 1 >= pages:
            break
        page += 1

    return {"imported": imported}
