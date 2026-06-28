"""
Бэкфилл фото существующих hh-кандидатов.

Читает кандидатов с hh_resume_id, у которых нет photo_url и нет метки photo_checked,
запрашивает резюме через hh API и проставляет proxy-URL фото (или метку photo_checked=True,
если фото нет). Учитывает суточный лимит hh (429 → quota_exhausted, прерываем батч).
"""

import asyncio
import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models import Candidate
from ..core.errors import ValidationError
from ..services.integrations.hh import service as hh_service
from ..services.integrations.hh import client as hh_client
from ..services.photo_proxy import build_photo_proxy_url
from ..services.smart_search import check_access

logger = logging.getLogger(__name__)


async def _mark_checked(cand_id, company_id) -> None:
    """Ставит photo_checked=True в отдельной короткой сессии."""
    try:
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Candidate).where(
                    Candidate.id == cand_id,
                    Candidate.company_id == company_id,
                    Candidate.deleted_at.is_(None),
                )
            )
            c = result.scalar_one_or_none()
            if c is not None:
                c.extra = {**(c.extra or {}), "photo_checked": True}
                await s.commit()
    except Exception:
        logger.exception("Не удалось пометить photo_checked для кандидата %s", cand_id)


async def backfill_candidate_photos(
    session: AsyncSession, company_id, limit: int = 50
) -> dict:
    """
    Батч-бэкфилл фото hh-кандидатов для компании.

    Возвращает:
        {
            "processed": int,   # обработано в этом батче
            "updated": int,     # проставлено фото
            "remaining": int,   # осталось (до следующего запуска)
            "quota_exhausted": bool,  # True — hh вернул 429, лимит исчерпан
        }
    """
    # Гейт: hh должен быть подключён
    has_access, _has_paid_access, _ = await check_access(session, company_id)
    if not has_access:
        raise ValidationError("hh.ru не подключён")

    base_filter = [
        Candidate.company_id == company_id,
        Candidate.deleted_at.is_(None),
        Candidate.extra["hh_resume_id"].astext.isnot(None),
        Candidate.extra["photo_url"].astext.is_(None),
        Candidate.extra["photo_checked"].astext.is_(None),
    ]

    # Считаем сколько всего осталось (до выборки батча)
    count_q = select(func.count()).select_from(Candidate).where(*base_filter)
    remaining_total: int = (await session.execute(count_q)).scalar_one()

    # Выбираем батч (id + resume_id) и сразу материализуем в питон-список
    rows_q = (
        select(Candidate.id, Candidate.extra["hh_resume_id"].astext)
        .where(*base_filter)
        .limit(limit)
    )
    rows = (await session.execute(rows_q)).all()
    pairs: list[tuple] = [(r[0], r[1]) for r in rows]

    # Токен снимаем ОДИН РАЗ до цикла
    token: str = await hh_service.get_valid_access_token(session, company_id)

    processed = 0
    updated = 0
    quota_exhausted = False

    for cand_id, resume_id in pairs:
        try:
            full = await asyncio.wait_for(
                hh_client.get_resume_by_id(token, resume_id),
                timeout=25,
            )
        except ValidationError as exc:
            if "квота" in str(exc).lower():
                # Суточный лимит hh исчерпан — прерываем батч, НЕ помечаем checked
                quota_exhausted = True
                logger.warning(
                    "Квота просмотров hh исчерпана, прерываем бэкфилл (processed=%d)", processed
                )
                break
            # Прочая ValidationError одного кандидата — помечаем checked и идём дальше
            logger.warning("ValidationError для резюме %s: %s", resume_id, exc)
            await _mark_checked(cand_id, company_id)
            processed += 1
            continue
        except asyncio.TimeoutError:
            logger.exception("Таймаут при получении резюме %s", resume_id)
            await _mark_checked(cand_id, company_id)
            processed += 1
            continue
        except Exception:
            logger.exception("Ошибка при получении резюме %s", resume_id)
            await _mark_checked(cand_id, company_id)
            processed += 1
            continue

        # Успешно получили резюме — строим proxy URL фото
        proxy_url = build_photo_proxy_url(full.get("photo"))

        try:
            async with AsyncSessionLocal() as s:
                result = await s.execute(
                    select(Candidate).where(
                        Candidate.id == cand_id,
                        Candidate.company_id == company_id,
                        Candidate.deleted_at.is_(None),
                    )
                )
                candidate = result.scalar_one_or_none()
                if candidate is None:
                    processed += 1
                    continue

                if proxy_url:
                    candidate.extra = {**(candidate.extra or {}), "photo_url": proxy_url}
                else:
                    candidate.extra = {**(candidate.extra or {}), "photo_checked": True}

                await s.commit()
        except Exception:
            logger.exception("Ошибка при сохранении фото кандидата %s", cand_id)
            processed += 1
            continue

        processed += 1
        if proxy_url:
            updated += 1

    return {
        "processed": processed,
        "updated": updated,
        "remaining": max(0, remaining_total - processed),
        "quota_exhausted": quota_exhausted,
    }
