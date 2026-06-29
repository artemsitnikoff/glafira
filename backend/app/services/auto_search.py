"""
Автоподбор — сервис сохранённых автопоисков резюме hh (saved searches).

Ф1: синхронизация списка сохранённых поисков работодателя с hh + чтение из кэша.
Не импортирует smart_search в обратную сторону — цикла нет
(smart_search НЕ импортирует auto_search).
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qsl, quote
from uuid import UUID

from sqlalchemy import select, desc, nullslast, update, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.errors import NotFoundError, ValidationError, ConflictError, GlafiraParseError
from ..database import AsyncSessionLocal
from ..models.auto_search import AutoSearch, AutoSearchRun
from ..models.candidate import Candidate
from ..models import Vacancy, Application
from .audit import audit
from .candidate import format_duration
from .integrations.hh import client as hh_client
from .integrations.hh import service as hh_service
from .integrations.hh.service import get_valid_access_token, build_candidate_resume_sections, _hh_period
from .smart_search import (
    check_access,
    _parse_api_quota,
    _is_ai_credits_error,
    _create_candidate_from_resume,
)
from .base_search import _create_synthetic_vacancy_for_scoring
from .glafira.scoring import score_resume_dict
from .settings.glafira import get_company_openrouter_key, get_company_llm_model

# Денежный бэкстоп: максимум резюме за один запрос «забрать контакт» — чтобы клиент
# не слил весь платный пул контактов одним вызовом (полноценный whitelist как в
# take_selected невозможен: кандидаты автопоиска не персистятся до оценки).
AUTO_TAKE_BATCH_CAP = 25

# Предохранитель расхода: верхний предел N для AI-оценки в Автоподборе (фаза EVALUATE).
# ОТДЕЛЬНЫЙ от GLAFIRA_MAX_EVALUATE (=100, умный подбор по своей базе) — Автоподбор
# гоняет большие сохранённые поиски hh, поэтому кап выше (1000). Каждый = LLM-вызов = деньги.
AUTO_MAX_EVALUATE = int(getattr(settings, "AUTO_MAX_EVALUATE", 1000))

logger = logging.getLogger(__name__)

_auto_active_tasks: dict = {}
AUTO_STUCK_RECONCILE_SECONDS = 270


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _run_is_dead_running(run) -> bool:
    """True, если прогон формально 'running', но фоновая задача давно его не трогала
    (передеплой убил asyncio-таск → updated_at завис старше порога reconcile)."""
    if run.status != "running" or run.updated_at is None:
        return False
    updated = run.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    return age >= AUTO_STUCK_RECONCILE_SECONDS


def _reconcile_stuck_run(run) -> bool:
    """Финализирует мёртвый running-прогон IN-PLACE (БЕЗ commit). Возвращает True,
    если что-то изменилось (и вызывающему нужно закоммитить).

    Зависимости от непустого scored НЕТ: даже прогон с 0 оценённых добивается
    (в 'error'), иначе partial-unique индекс uq_auto_search_run_active навечно
    блокирует перезапуск оценки (вечный ConflictError)."""
    if not _run_is_dead_running(run):
        return False
    scored = run.scored_candidates or []
    if scored:
        run.status = "done"
        run.stage = "done"
        run.evaluated = len(scored)
        if not run.note:
            run.note = (
                "Авто-финализация при чтении: фоновая задача не обновила статус"
            )
    else:
        run.status = "error"
        if not run.error:
            run.error = (
                "Прервано — фоновая задача не обновляла статус (перезапуск/зависание)"
            )
    run.finished_at = _utc_naive_now()
    return True


def _extract_photo_url(photo) -> str | None:
    """Достаёт URL фото из hh-объекта photo, устойчиво к разным структурам:
    dict {medium/small} ИЛИ {'500','100','40',...} ИЛИ плоская строка-URL."""
    if not photo:
        return None
    if isinstance(photo, str):
        return photo if photo.startswith("http") else None
    if isinstance(photo, dict):
        # приоритет по убыванию размера/предпочтения
        for k in ("medium", "500", "100", "small", "40"):
            v = photo.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        # фолбэк: первое строковое значение-URL (кроме id)
        for k, v in photo.items():
            if k == "id":
                continue
            if isinstance(v, str) and v.startswith("http"):
                return v
    return None


def parse_saved_search_url(url: str) -> list[tuple[str, str]]:
    """Разбирает query-строку saved_search-URL в список пар (без page/per_page).

    Понадобится в Ф2 для перенаправления параметров поиска в /resumes.
    Определяем сейчас, чтобы зафиксировать контракт.
    """
    if not url:
        return []
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    return [(k, v) for k, v in pairs if k not in ("page", "per_page")]


async def sync_saved_searches(session: AsyncSession, company_id: UUID) -> list[AutoSearch]:
    """Синхронизирует сохранённые автопоиски резюме hh в локальную таблицу auto_searches.

    UPSERT по (company_id, hh_saved_search_id). При обновлении не трогает
    пользовательские поля basis/auto_eval/last_seen_at — только то, что приходит из hh.
    """
    token = await get_valid_access_token(session, company_id)

    items: list[dict] = []
    page = 0
    while True:
        raw = await hh_client.list_saved_resume_searches(token, page=page)
        page_items = (raw.get("items") or []) if isinstance(raw, dict) else []
        items.extend(page_items)
        # определить, есть ли ещё страницы
        pages = raw.get("pages") if isinstance(raw, dict) else None
        if isinstance(pages, int):
            page += 1
            if page >= pages:
                break
        else:
            # фолбэк, если hh не вернул pages: остановиться, если страница неполная
            if len(page_items) < 10:
                break
            page += 1
        if page >= 50:  # предохранитель (макс 500 автопоисков), не зациклиться
            break

    for item in items:
        if not isinstance(item, dict):
            continue

        hh_id = item.get("id")
        if hh_id is None:
            continue
        hh_id = str(hh_id)

        name = item.get("name") or "Без названия"

        items_obj = item.get("items") or {}
        if not isinstance(items_obj, dict):
            items_obj = {}
        new_obj = item.get("new_items") or {}
        if not isinstance(new_obj, dict):
            new_obj = {}

        items_url = items_obj.get("url")
        new_items_url = new_obj.get("url")

        total = items_obj.get("count")
        if total is None:
            total = item.get("found")

        new_count = new_obj.get("count")
        if new_count is None:
            new_count = 0

        subscribed = bool(item.get("subscription", False))

        # region best-effort: hh может отдать area как dict {name}, как строку, или не отдать
        area = item.get("area") or item.get("region")
        if isinstance(area, dict):
            region = area.get("name")
        elif isinstance(area, str):
            region = area
        else:
            region = None

        existing = (
            await session.execute(
                select(AutoSearch).where(
                    AutoSearch.company_id == company_id,
                    AutoSearch.hh_saved_search_id == hh_id,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.name = name
            existing.region = region
            existing.items_url = items_url
            existing.new_items_url = new_items_url
            existing.total = total
            existing.new_count = new_count
            existing.subscribed = subscribed
            existing.last_synced_at = _utc_naive_now()
            # НЕ трогаем basis / auto_eval / last_seen_at — это пользовательские поля
        else:
            obj = AutoSearch(
                company_id=company_id,
                hh_saved_search_id=hh_id,
                name=name,
                region=region,
                items_url=items_url,
                new_items_url=new_items_url,
                total=total,
                new_count=new_count,
                subscribed=subscribed,
                auto_eval=False,
                basis=None,
                last_synced_at=_utc_naive_now(),
            )
            session.add(obj)

    await session.commit()
    return await list_auto_searches(session, company_id)


async def list_auto_searches(session: AsyncSession, company_id: UUID) -> list[AutoSearch]:
    """Читает автопоиски компании из кэша. Сортировка: сначала с новыми (new_count desc), затем по имени.

    Навешивает transient-атрибуты прогресса последней AI-оценки (eval_status/eval_done/
    eval_total) на каждый ORM-объект — pydantic AutoSearchItem прочитает их через
    from_attributes. Последний прогон по каждому автопоиску берётся ОДНИМ запросом
    (DISTINCT ON), без N+1. В БД здесь НЕ пишем — только для отображения."""
    result = await session.execute(
        select(AutoSearch)
        .where(AutoSearch.company_id == company_id)
        .order_by(nullslast(desc(AutoSearch.new_count)), AutoSearch.name)
    )
    items = list(result.scalars().all())

    last_runs_res = await session.execute(
        select(AutoSearchRun)
        .where(AutoSearchRun.company_id == company_id)
        .order_by(AutoSearchRun.auto_search_id, desc(AutoSearchRun.created_at))
        .distinct(AutoSearchRun.auto_search_id)
    )
    last_by_as = {r.auto_search_id: r for r in last_runs_res.scalars().all()}

    for s in items:
        run = last_by_as.get(s.id)
        if run is not None:
            s.eval_status = (
                "error"
                if (run.status == "running" and _run_is_dead_running(run))
                else run.status
            )
            s.eval_done = run.evaluated or 0
            s.eval_total = run.to_evaluate or 0
        else:
            s.eval_status = None
            s.eval_done = 0
            s.eval_total = 0

    return items


async def get_auto_access(session: AsyncSession, company_id: UUID) -> dict:
    """Доступ к Автоподбору: hh подключён + (best-effort) остаток платного пула."""
    has_access, has_paid_access, reason = await check_access(session, company_id)

    pool_left = None
    if has_access:
        try:
            token = await get_valid_access_token(session, company_id)
            me = await hh_client.get_me(token)
            employer_id = (me.get("employer") or {}).get("id")
            if employer_id:
                quota = await hh_client.get_payable_api_actions(token, str(employer_id))
                _u, limited_remaining, _h = _parse_api_quota(quota)
                # ⚠️ pool_left = limited_remaining (остаток платных API-действий) —
                # ПРИБЛИЗИТЕЛЬНО; точное поле контактного пула пиннится на живом токене.
                pool_left = limited_remaining
        except Exception as e:
            pool_left = None
            logger.warning("[auto] pool_left best-effort failed: %s", e)

    return {
        "has_access": has_access,
        "has_paid_access": has_paid_access,
        "reason": reason,
        "pool_left": pool_left,
    }


async def get_auto_candidates(
    session: AsyncSession,
    company_id: UUID,
    auto_search_id: UUID,
    segment: str = "all",
    page: int = 0,
    sort: str = "updated",
) -> dict:
    """Кандидаты автопоиска на БЕСПЛАТНЫХ полях hh, синхронно, с пагинацией по 10.

    Читает items_url (segment='all') или new_items_url (segment='new') сохранённого
    автопоиска hh и отдаёт страницу резюме без открытия контактов/чтения полного резюме.
    sort принимается, пока игнорируется (резюме отдаёт hh в порядке поиска).
    """
    auto_search = (
        await session.execute(
            select(AutoSearch).where(
                AutoSearch.company_id == company_id,
                AutoSearch.id == auto_search_id,
            )
        )
    ).scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")

    url = auto_search.new_items_url if segment == "new" else auto_search.items_url
    if not url:
        return {"items": [], "total": 0, "page": page, "pages": 0, "per_page": 10}

    params = parse_saved_search_url(url) + [("per_page", "10"), ("page", str(page))]

    token = await get_valid_access_token(session, company_id)
    raw = await hh_client.search_resumes(token, params)

    items = raw.get("items") or []
    # ДИАГ-ЛОГ: только КЛЮЧИ первого item (структура ответа), НЕ значения (PII).
    if items and isinstance(items[0], dict):
        logger.info("[auto] resume item keys=%s", list(items[0].keys()))
        logger.info("[auto] resume item has_photo=%s", bool((items[0].get("photo") or {})) if isinstance(items[0], dict) else False)
        # ДИАГ (PII-безопасно): СТРУКТУРА photo первого item — только ключи/тип, БЕЗ URL (URL фото = лицо, PII).
        logger.info(
            "[auto] photo struct=%s",
            (list(p.keys()) if isinstance((p := items[0].get("photo")), dict) else type(items[0].get("photo")).__name__),
        )

    # БАТЧ-дедуп: один запрос по всем валидным hh_resume_id страницы.
    resume_ids = [str(item.get("id")) for item in items
                  if isinstance(item, dict) and item.get("id") is not None]
    taken_ids: set[str] = set()
    if resume_ids:
        rows = await session.execute(
            select(Candidate.extra["hh_resume_id"].astext).where(
                Candidate.company_id == company_id,
                Candidate.extra["hh_resume_id"].astext.in_(resume_ids),
                Candidate.deleted_at.is_(None),
            )
        )
        taken_ids = {r for r in rows.scalars().all() if r is not None}

    items_mapped: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = item.get("id")
        if rid is None:
            continue
        hh_resume_id = str(rid)

        area = item.get("area") or {}
        salary_obj = item.get("salary") or {}
        total_exp = item.get("total_experience") or {}

        last_job = None
        experience_list = item.get("experience") or []
        if isinstance(experience_list, list):
            for exp in experience_list:
                if not isinstance(exp, dict):
                    continue
                position = exp.get("position")
                company = exp.get("company")
                parts = [p for p in (position, company) if p]
                last_job = " · ".join(parts) if parts else None
                break

        real_photo_url = _extract_photo_url(item.get("photo"))
        photo_url = f"/api/v1/smart/auto/photo?src={quote(real_photo_url, safe='')}" if real_photo_url else None

        items_mapped.append({
            "hh_resume_id": hh_resume_id,
            "title": item.get("title"),
            "age": item.get("age"),
            "city": area.get("name") if isinstance(area, dict) else None,
            "anonymous": bool(item.get("hidden_fields")),
            "salary": salary_obj.get("amount") if isinstance(salary_obj, dict) else None,
            "experience": format_duration((total_exp.get("months") if isinstance(total_exp, dict) else None) or 0),
            "skills": item.get("skill_set") or [],
            "last_job": last_job,
            "updated_at": item.get("updated_at"),
            "is_new": segment == "new",
            "score": None,
            "taken": hh_resume_id in taken_ids,
            "photo_url": photo_url,
            "hh_url": item.get("alternate_url"),
        })

    total = min(raw.get("found", 0) or 0, 2000)
    pages = math.ceil(total / 10) if total else 0

    if segment == "new":
        auto_search.last_seen_at = _utc_naive_now()
        await session.commit()

    # Инжектируем score из НЕДАВНИХ прогонов (НЕ только последнего 'done').
    # Раньше читался ровно один прогон со status=='done' — из-за чего:
    #  • прогон, прервавшийся после N оценок (status='error': таймаут/кредиты),
    #    терял ВСЕ свои оценки в UI, хотя они персистнуты в scored_candidates
    #    (= клиент уже заплатил за оценку, а её не видно — «где оценки??»);
    #  • маленький до-прогон (напр. 122/123) перекрывал большой (480) — кандидаты
    #    вне маленького показывались прочерком;
    #  • при отсутствии свежего 'done' читался старый крошечный прогон (1 балл).
    # Теперь мёржим оценки из нескольких последних прогонов, НЕЗАВИСИМО от статуса;
    # при конфликте по hh_resume_id побеждает балл из БОЛЕЕ НОВОГО прогона.
    recent_runs_result = await session.execute(
        select(AutoSearchRun)
        .where(
            AutoSearchRun.company_id == company_id,
            AutoSearchRun.auto_search_id == auto_search_id,
        )
        .order_by(desc(AutoSearchRun.created_at))
        .limit(8)
    )
    score_map: dict[str, int] = {}
    for run in recent_runs_result.scalars().all():  # от новых к старым
        for c in (run.scored_candidates or []):
            if not isinstance(c, dict):
                continue
            rid = c.get("hh_resume_id")
            sc = c.get("score")
            if rid is None or sc is None:
                continue
            score_map.setdefault(str(rid), sc)  # первый = из самого нового прогона
    if score_map:
        for it in items_mapped:
            rid = str(it.get("hh_resume_id", ""))
            if rid in score_map:
                it["score"] = score_map[rid]
    if sort == "score":
        items_mapped.sort(
            key=lambda x: (x.get("score") is None, -(x.get("score") or 0))
        )

    return {
        "items": items_mapped,
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": 10,
    }


async def get_auto_candidate_detail(
    session: AsyncSession,
    company_id: UUID,
    hh_resume_id: str,
) -> dict:
    """ПОЛНОЕ резюме кандидата автоподбора через GET /resumes/{id} БЕЗ открытия контакта.

    Это ПРОСМОТР резюме (тратит суточную квоту просмотров hh, 429 при превышении),
    НЕ списание контакта из платного пула — контакты в ответе hh будут null
    (with_contact не передаётся), ФИО/телефон/email НЕ маппим и НЕ отдаём.
    Доступно при активной услуге доступа к базе резюме hh; 403 → понятная ошибка.
    """
    has_access, _has_paid_access, reason = await check_access(session, company_id)
    if not has_access:
        raise ValidationError(reason or "hh.ru не подключён")

    token = await get_valid_access_token(session, company_id)

    try:
        full = await hh_client.get_resume_by_id(token, hh_resume_id)
    except ValidationError as e:
        msg = str(e)
        if "квота" in msg.lower():
            raise ValidationError("Превышен суточный лимит просмотров резюме hh")
        raise ValidationError(f"Резюме недоступно: {msg[:150]}")

    # ДИАГ-ЛОГ (один раз): только КЛЮЧИ полного резюме, без PII — для пиннинга имён полей.
    if isinstance(full, dict):
        logger.info("[auto] resume detail keys=%s", list(full.keys()))
        # ДИАГ (PII-безопасно): СТРУКТУРА photo полного резюме — только ключи/тип, БЕЗ URL (PII).
        logger.info(
            "[auto] detail photo struct=%s",
            (list(p.keys()) if isinstance((p := full.get("photo")), dict) else type(full.get("photo")).__name__),
        )

    # Защитный маппинг (паттерн build_candidate_resume_sections / get_auto_candidates)
    area = full.get("area") or {}
    salary_obj = full.get("salary") or {}
    total_exp = full.get("total_experience") or {}
    photo = full.get("photo")

    real_photo_url = _extract_photo_url(photo)
    photo_url = (
        f"/api/v1/smart/auto/photo?src={quote(real_photo_url, safe='')}"
        if real_photo_url else None
    )
    # ВРЕМЕННО (диаг): ключи объекта photo (НЕ URL, не PII) — для пиннинга структуры curl'ом.
    photo_keys = list(photo.keys()) if isinstance(photo, dict) else None

    # Навыки: skill_set — список строк ИЛИ объектов {name} (защитно)
    skills: list[str] = []
    for sk in (full.get("skill_set") or []):
        if isinstance(sk, dict):
            name = sk.get("name")
        else:
            name = sk
        if name:
            s = str(name).strip()
            if s:
                skills.append(s)

    # Опыт
    experience: list[dict] = []
    for e in (full.get("experience") or []):
        if not isinstance(e, dict):
            continue
        experience.append({
            "position": e.get("position"),
            "company": e.get("company"),
            "period": _hh_period(e.get("start"), e.get("end")),
            "description": e.get("description"),
        })

    # Образование: hh education = {primary:[...], additional:[...]} (защитно)
    education: list[dict] = []
    edu_obj = full.get("education") or {}
    if isinstance(edu_obj, dict):
        for bucket in ("primary", "additional"):
            for ed in (edu_obj.get(bucket) or []):
                if not isinstance(ed, dict):
                    continue
                year_raw = ed.get("year")
                try:
                    year = int(year_raw) if year_raw is not None else None
                except (ValueError, TypeError):
                    year = None
                education.append({
                    "name": ed.get("name"),
                    "organization": ed.get("organization"),
                    "year": year,
                    "result": ed.get("result"),
                })

    # Языки: [{name, level:{name}}] → "Русский — Родной" (защитно)
    languages: list[str] = []
    for lng in (full.get("language") or []):
        if not isinstance(lng, dict):
            continue
        lname = lng.get("name")
        if not lname:
            continue
        level = (lng.get("level") or {}).get("name") if isinstance(lng.get("level"), dict) else None
        languages.append(f"{lname} — {level}" if level else str(lname))

    return {
        "hh_resume_id": str(hh_resume_id),
        "title": full.get("title"),
        "age": full.get("age"),
        "city": area.get("name") if isinstance(area, dict) else None,
        "salary": salary_obj.get("amount") if isinstance(salary_obj, dict) else None,
        "total_experience": format_duration((total_exp.get("months") if isinstance(total_exp, dict) else None) or 0),
        "anonymous": bool(full.get("hidden_fields")),
        "photo_url": photo_url,
        "photo_keys": photo_keys,  # ВРЕМЕННО (диаг): ключи объекта photo, не URL/PII
        "hh_url": full.get("alternate_url"),
        "about": full.get("skills"),  # в hh-резюме «о себе» лежит в поле skills (ТЕКСТ)
        "skills": skills,
        "experience": experience,
        "education": education,
        "languages": languages,
    }


# === ФАЗА 3: Основа оценки + AI-оценка в фоне ===

async def set_basis(session: AsyncSession, company_id: UUID, auto_search_id: UUID, basis: dict) -> AutoSearch:
    """Задать основу оценки для автопоиска (vacancy или prompt)."""
    from uuid import UUID as _UUID

    result = await session.execute(
        select(AutoSearch).where(
            AutoSearch.company_id == company_id,
            AutoSearch.id == auto_search_id,
        )
    )
    auto_search = result.scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")

    kind = basis.get("kind")
    if kind == "vacancy":
        vacancy_id_raw = basis.get("vacancy_id")
        try:
            vacancy_uuid = _UUID(str(vacancy_id_raw))
        except Exception:
            raise NotFoundError("Вакансия")
        vacancy_result = await session.execute(
            select(Vacancy).where(
                Vacancy.id == vacancy_uuid,
                Vacancy.company_id == company_id,
                Vacancy.deleted_at.is_(None),
            )
        )
        if vacancy_result.scalar_one_or_none() is None:
            raise NotFoundError("Вакансия")
    elif kind == "prompt":
        prompt = (basis.get("prompt") or "").strip()
        if len(prompt) < 3:
            raise ValidationError("Укажите промпт не короче 3 символов")
    else:
        raise ValidationError("Некорректная основа оценки")

    auto_search.basis = basis
    await session.commit()
    return auto_search


async def set_auto_eval(session: AsyncSession, company_id: UUID, auto_search_id: UUID, enabled: bool) -> AutoSearch:
    """Включить/выключить AI-оценку для автопоиска."""
    result = await session.execute(
        select(AutoSearch).where(
            AutoSearch.company_id == company_id,
            AutoSearch.id == auto_search_id,
        )
    )
    auto_search = result.scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")
    if enabled and auto_search.basis is None:
        raise ValidationError("Сначала задайте основу оценки")
    auto_search.auto_eval = enabled
    await session.commit()
    return auto_search


async def start_auto_evaluate(
    session: AsyncSession,
    company_id: UUID,
    auto_search_id: UUID,
    segment: str = "all",
    n: int | None = None,
) -> UUID:
    """TOCTOU-безопасный старт фонового прогона AI-оценки."""
    result = await session.execute(
        select(AutoSearch).where(
            AutoSearch.company_id == company_id,
            AutoSearch.id == auto_search_id,
        )
    )
    auto_search = result.scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")
    if auto_search.basis is None:
        raise ValidationError("Сначала задайте основу оценки")

    to_eval = min(n or AUTO_MAX_EVALUATE, AUTO_MAX_EVALUATE)

    def _new_run() -> AutoSearchRun:
        return AutoSearchRun(
            company_id=company_id,
            auto_search_id=auto_search_id,
            status="running",
            stage="evaluating",
            basis=dict(auto_search.basis),
            to_evaluate=to_eval,
            evaluated=0,
            scored_candidates=[],
        )

    run = _new_run()
    session.add(run)
    try:
        await session.commit()
    except IntegrityError:
        # Partial-unique индекс uq_auto_search_run_active не дал вставить —
        # значит уже есть running-прогон. Если он осиротел (передеплой убил
        # asyncio-таск), вытесняем его и ставим новый. Ровно один ретрай вставки.
        await session.rollback()
        existing = (
            await session.execute(
                select(AutoSearchRun)
                .where(
                    AutoSearchRun.company_id == company_id,
                    AutoSearchRun.auto_search_id == auto_search_id,
                    AutoSearchRun.status == "running",
                )
                .order_by(desc(AutoSearchRun.updated_at))
                .limit(1)
            )
        ).scalar_one_or_none()

        if existing is None or not _run_is_dead_running(existing):
            # Живой (свежий) прогон действительно идёт — честный конфликт.
            raise ConflictError("Оценка уже идёт")

        # Осиротевший прогон — добиваем в error и освобождаем индекс.
        existing.status = "error"
        existing.error = "Прервано (вытеснено новым запуском)"
        existing.finished_at = _utc_naive_now()
        await session.commit()

        run = _new_run()
        session.add(run)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise ConflictError("Оценка уже идёт")

    run_id = run.id
    task = asyncio.create_task(
        _run_auto_evaluate(run_id, company_id, auto_search_id, segment, n)
    )
    _auto_active_tasks[run_id] = task
    task.add_done_callback(lambda t: _auto_active_tasks.pop(run_id, None))
    return run_id


async def _run_auto_evaluate(
    run_id: UUID,
    company_id: UUID,
    auto_search_id: UUID,
    segment: str,
    n: int | None,
) -> None:
    """Фоновая AI-оценка кандидатов автопоиска ТОЛЬКО по бесплатным полям hh (без get_resume_by_id)."""

    async def _inner() -> None:
        token = None
        basis: dict = {}
        vacancy_proxy = None
        url = None
        api_key = None
        model = None

        # INIT: короткая сессия
        async with AsyncSessionLocal() as session:
            run = await session.get(AutoSearchRun, run_id)
            if run is None:
                return
            basis = run.basis or {}

            try:
                token = await get_valid_access_token(session, company_id)
            except Exception as e:
                run.status = "error"
                run.error = f"Ошибка hh-токена: {str(e)[:300]}"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return

            as_result = await session.execute(
                select(AutoSearch).where(
                    AutoSearch.company_id == company_id,
                    AutoSearch.id == auto_search_id,
                )
            )
            auto_search = as_result.scalar_one_or_none()
            if auto_search is None:
                run.status = "error"
                run.error = "Автопоиск не найден"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return

            url = auto_search.new_items_url if segment == "new" else auto_search.items_url

            try:
                api_key = await get_company_openrouter_key(session, company_id)
            except Exception as e:
                run.status = "error"
                run.error = f"OpenRouter не настроен: {str(e)[:300]}"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return

            model = await get_company_llm_model(session, company_id)

            kind = basis.get("kind")
            if kind == "vacancy":
                from uuid import UUID as _UUID
                try:
                    vacancy_uuid = _UUID(str(basis.get("vacancy_id")))
                except Exception:
                    run.status = "error"
                    run.error = "Некорректный ID вакансии-основы"
                    run.finished_at = _utc_naive_now()
                    await session.commit()
                    return
                vac_result = await session.execute(
                    select(Vacancy).where(
                        Vacancy.id == vacancy_uuid,
                        Vacancy.company_id == company_id,
                        Vacancy.deleted_at.is_(None),
                    )
                )
                vacancy = vac_result.scalar_one_or_none()
                if vacancy is None:
                    run.status = "error"
                    run.error = "Вакансия-основа удалена"
                    run.finished_at = _utc_naive_now()
                    await session.commit()
                    return
                vacancy_data = {
                    "name": getattr(vacancy, "name", None),
                    "city": getattr(vacancy, "city", None),
                    "salary_from": getattr(vacancy, "salary_from", None),
                    "salary_to": getattr(vacancy, "salary_to", None),
                    "currency": getattr(vacancy, "currency", None),
                    "description": getattr(vacancy, "description", None),
                    "recruiter_scoring_instructions": getattr(
                        vacancy, "recruiter_scoring_instructions", None
                    ),
                    "glafira_mode": getattr(vacancy, "glafira_mode", "A"),
                    "auto_move": getattr(vacancy, "auto_move", False),
                    "auto_move_threshold": getattr(vacancy, "auto_move_threshold", None),
                }
                vacancy_proxy = type("AutoVacancyProxy", (), vacancy_data)()
            elif kind == "prompt":
                vacancy_proxy = _create_synthetic_vacancy_for_scoring(
                    basis.get("prompt", "")
                )
            else:
                run.status = "error"
                run.error = "Некорректная основа оценки"
                run.finished_at = _utc_naive_now()
                await session.commit()
                return
        # INIT-сессия закрыта

        if not url:
            try:
                async with AsyncSessionLocal() as session:
                    run = await session.get(AutoSearchRun, run_id)
                    if run:
                        run.status = "done"
                        run.stage = "done"
                        run.note = "Нет кандидатов в автопоиске"
                        run.finished_at = _utc_naive_now()
                        await session.commit()
            except Exception as e:
                logger.error("[auto_eval] Не удалось финализировать пустой прогон: %s", e)
            return

        cap = min(n or AUTO_MAX_EVALUATE, AUTO_MAX_EVALUATE)
        accumulated: list[dict] = []
        for page in range(20):
            try:
                params = parse_saved_search_url(url) + [
                    ("per_page", "50"),
                    ("page", str(page)),
                ]
                res = await asyncio.wait_for(
                    hh_client.search_resumes(token, params), timeout=45
                )
                page_items = res.get("items") or []
                if not page_items:
                    break
                accumulated.extend(page_items)
                if len(accumulated) >= cap:
                    break
            except asyncio.TimeoutError:
                logger.warning("[auto_eval] Таймаут пагинации на странице %d", page)
                break
            except Exception as e:
                logger.warning("[auto_eval] Ошибка пагинации: %s", e)
                break

        items = accumulated[:cap]

        if not items:
            try:
                async with AsyncSessionLocal() as session:
                    run = await session.get(AutoSearchRun, run_id)
                    if run:
                        run.status = "done"
                        run.stage = "done"
                        run.note = "Нет кандидатов для оценки"
                        run.finished_at = _utc_naive_now()
                        await session.commit()
            except Exception as e:
                logger.error("[auto_eval] Не удалось финализировать пустой список: %s", e)
            return

        # Обновить to_evaluate реальным числом
        try:
            async with AsyncSessionLocal() as session:
                run = await session.get(AutoSearchRun, run_id)
                if run:
                    run.to_evaluate = len(items)
                    await session.commit()
        except Exception as e:
            logger.warning("[auto_eval] Не удалось обновить to_evaluate: %s", e)

        scored_candidates: list[dict] = []
        evaluated = 0
        credits_note: str | None = None

        for item in items:
            try:
                result = await asyncio.wait_for(
                    score_resume_dict(item, vacancy_proxy, company_id, api_key, model),
                    timeout=180,
                )
                record = {
                    "hh_resume_id": str(item.get("id")),
                    "title": item.get("title"),
                    "score": result.get("score"),
                    "verdict": result.get("verdict"),
                    "summary": result.get("summary"),
                    "strengths": result.get("strengths") or [],
                    "risks": result.get("risks") or [],
                    "requirements_match": result.get("requirements_match") or [],
                    "questions": result.get("questions") or [],
                    "forecast": result.get("forecast"),
                }
                scored_candidates.append(record)
                evaluated += 1
                try:
                    async with AsyncSessionLocal() as session:
                        run = await session.get(AutoSearchRun, run_id)
                        if run:
                            run.scored_candidates = list(scored_candidates)
                            run.evaluated = evaluated
                            await session.commit()
                except Exception as e:
                    logger.warning("[auto_eval] Не удалось обновить прогресс: %s", e)
            except asyncio.TimeoutError:
                logger.warning("[auto_eval] Таймаут оценки резюме %s", item.get("id"))
                continue
            except Exception as e:
                reason = str(e)
                if _is_ai_credits_error(reason, None):
                    credits_note = "AI-кредиты исчерпаны"
                    break
                else:
                    logger.warning(
                        "[auto_eval] Ошибка оценки резюме %s: %s", item.get("id"), e
                    )
                    continue

        # ФИНАЛ
        try:
            async with AsyncSessionLocal() as session:
                run = await session.get(AutoSearchRun, run_id)
                if run:
                    run.status = "done"
                    run.stage = "done"
                    run.scored_candidates = list(scored_candidates)
                    run.evaluated = evaluated
                    run.finished_at = _utc_naive_now()
                    if credits_note:
                        run.note = credits_note
                    await session.commit()
        except Exception as e:
            logger.error("[auto_eval] Не удалось сохранить финал: %s", e)

    try:
        timeout_s = min(6 * 3600, max(1800, (n or AUTO_MAX_EVALUATE) * 30))
        await asyncio.wait_for(_inner(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            async with AsyncSessionLocal() as s:
                run = await s.get(AutoSearchRun, run_id)
                if run and run.status == "running":
                    run.status = "error"
                    run.error = "timeout"
                    run.finished_at = _utc_naive_now()
                    await s.commit()
        except Exception as e:
            logger.error("[auto_eval] Финал по таймауту: %s", e)
    except Exception as e:
        try:
            async with AsyncSessionLocal() as s:
                run = await s.get(AutoSearchRun, run_id)
                if run and run.status == "running":
                    run.status = "error"
                    run.error = str(e)[:500]
                    run.finished_at = _utc_naive_now()
                    await s.commit()
        except Exception as fe:
            logger.error("[auto_eval] Двойной сбой: %s", fe)
    finally:
        _auto_active_tasks.pop(run_id, None)


async def get_auto_run_status(session: AsyncSession, company_id: UUID, run_id: UUID) -> AutoSearchRun:
    """Статус прогона AI-оценки с reconcile застрявших."""
    result = await session.execute(
        select(AutoSearchRun).where(
            AutoSearchRun.id == run_id,
            AutoSearchRun.company_id == company_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise NotFoundError("Прогон")

    # Reconcile застрявших (в т.ч. с 0 оценённых — иначе perma-CONFLICT при перезапуске)
    if _reconcile_stuck_run(run):
        run_pk = run.id
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            re_result = await session.execute(
                select(AutoSearchRun).where(AutoSearchRun.id == run_pk)
            )
            run = re_result.scalar_one_or_none()

    return run


async def sweep_orphaned_auto_runs() -> None:
    """Закрывает зависшие прогоны AI-оценки при старте сервера."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
        async with AsyncSessionLocal() as session:
            stmt = (
                update(AutoSearchRun)
                .where(
                    AutoSearchRun.status == "running",
                    AutoSearchRun.updated_at < cutoff,
                )
                .values(
                    status="error",
                    error="Прервано (зависание/перезапуск)",
                    finished_at=_utc_naive_now(),
                )
                .returning(AutoSearchRun.id)
            )
            result = await session.execute(stmt)
            ids = result.scalars().all()
            if ids:
                await session.commit()
                logger.info(
                    "[auto_eval] sweep: закрыто %d зависших прогонов: %s",
                    len(ids),
                    ids,
                )
    except Exception as e:
        logger.error("[auto_eval] sweep_orphaned_auto_runs ошибка: %s", e)


# === ФАЗА 4: «Забрать контакт / Перевести» (ПЛАТНО) ===

async def _auto_pool_left(session: AsyncSession, company_id: UUID) -> int | None:
    """Best-effort остаток платных API-действий hh после открытия контактов.

    Тот же приблизительный показатель, что и в get_auto_access (limited_remaining).
    Точное поле контактного пула пиннится на живом токене.
    """
    try:
        token = await get_valid_access_token(session, company_id)
        me = await hh_client.get_me(token)
        employer_id = (me.get("employer") or {}).get("id")
        if not employer_id:
            return None
        quota = await hh_client.get_payable_api_actions(token, str(employer_id))
        _u, limited_remaining, _h = _parse_api_quota(quota)
        return limited_remaining
    except Exception as e:
        logger.warning("[auto] pool_left best-effort failed: %s", e)
        return None


async def take_auto_contact(
    session: AsyncSession,
    company_id: UUID,
    actor_user_id: UUID,
    auto_search_id: UUID,
    resume_ids: list[str],
    target: str = "pool",
    vacancy_id: UUID | None = None,
) -> dict:
    """«Забрать контакт / Перевести» — открыть контакт hh (ПЛАТНО, get_resume_by_id даёт
    ФИО+контакты), создать Candidate в базе компании. target:
      - 'pool'   → только Candidate (общая база, БЕЗ Application);
      - 'vacancy'→ Candidate + Application(stage='added') в воронке указанной вакансии.

    По образцу smart_search.take_selected:
    - Гейт has_paid_access ДО любого платного вызова (get_resume_by_id тратит контакт).
    - Дедуп по extra->>'hh_resume_id' (company-scoped, deleted_at IS NULL) — существующий
      кандидат НЕ открывает контакт повторно (платный API не дёргается).
    - 429/квота на get_resume_by_id → ValidationError «Пул контактов исчерпан», прерывает
      дальнейшие платные вызовы в этом запросе.
    - Денежный бэкстоп: кап размера батча (AUTO_TAKE_BATCH_CAP).
    - source='smart', extra.auto_search=True (extra критичен для дедупа), audit actor_type='human'.

    Returns: {'results': list[dict], 'taken': int, 'pool_left': int|None}.
    """
    from .candidate import assign_candidate_to_vacancy

    # Денежный бэкстоп: кап размера батча ДО любого платного вызова
    if len(resume_ids) > AUTO_TAKE_BATCH_CAP:
        raise ValidationError(
            f"Слишком много резюме за один раз (максимум {AUTO_TAKE_BATCH_CAP})"
        )

    # Загружаем автопоиск company-scoped (нужен hh_saved_search_id для extra)
    auto_search = (
        await session.execute(
            select(AutoSearch).where(
                AutoSearch.company_id == company_id,
                AutoSearch.id == auto_search_id,
            )
        )
    ).scalar_one_or_none()
    if auto_search is None:
        raise NotFoundError("Автопоиск")
    saved_search_id = auto_search.hh_saved_search_id

    # target='vacancy' → vacancy_id обязателен + company-scoped существует
    target_vacancy_id: UUID | None = None
    if target == "vacancy":
        if vacancy_id is None:
            raise ValidationError("Для перевода в воронку укажите вакансию")
        vacancy = (
            await session.execute(
                select(Vacancy).where(
                    Vacancy.id == vacancy_id,
                    Vacancy.company_id == company_id,
                    Vacancy.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if vacancy is None:
            raise NotFoundError("Вакансия")
        target_vacancy_id = vacancy.id

    # Гейт: платный доступ обязателен ДО get_resume_by_id (тратит контакт)
    has_access, has_paid_access, _ = await check_access(session, company_id)
    if not has_paid_access:
        raise ValidationError(
            "Нет платного доступа к базе резюме hh — открытие контактов недоступно."
        )

    # Снимаем токен и освобождаем request-сессию перед сетевым циклом
    access_token = await get_valid_access_token(session, company_id)
    await session.commit()

    results: list[dict] = []
    taken = 0

    for resume_id in resume_ids:
        try:
            # Дедуп: кандидат уже в базе по hh_resume_id (company-scoped, не удалён)?
            async with AsyncSessionLocal() as check_session:
                existing = (
                    await check_session.execute(
                        select(Candidate).where(
                            Candidate.company_id == company_id,
                            Candidate.extra["hh_resume_id"].astext == str(resume_id),
                            Candidate.deleted_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()

            if existing is not None:
                # Контакт уже открыт ранее — платный API НЕ дёргаем.
                if target == "vacancy":
                    try:
                        async with AsyncSessionLocal() as assign_session:
                            await assign_candidate_to_vacancy(
                                assign_session,
                                existing.id,
                                target_vacancy_id,
                                "added",
                                company_id,
                                actor_user_id,
                            )
                            await assign_session.commit()
                    except ConflictError:
                        # уже привязан к этой вакансии — не ошибка
                        pass
                results.append({
                    "hh_resume_id": str(resume_id),
                    "status": "already",
                    "candidate_id": existing.id,
                    "error": None,
                })
                continue

            # Открываем контакт — get_resume_by_id (ПЛАТНО)
            try:
                full_resume = await asyncio.wait_for(
                    hh_client.get_resume_by_id(access_token, resume_id),
                    timeout=25,
                )
            except asyncio.TimeoutError:
                results.append({
                    "hh_resume_id": str(resume_id),
                    "status": "error",
                    "candidate_id": None,
                    "error": "Таймаут получения резюме (25с)",
                })
                continue
            except ValidationError as e:
                msg = str(e)
                # 429/квота → дальше платные вызовы бессмысленны: прерываем цикл
                if "квота" in msg.lower():
                    results.append({
                        "hh_resume_id": str(resume_id),
                        "status": "error",
                        "candidate_id": None,
                        "error": "Пул контактов исчерпан",
                    })
                    break
                results.append({
                    "hh_resume_id": str(resume_id),
                    "status": "error",
                    "candidate_id": None,
                    "error": f"Резюме недоступно: {msg[:120]}",
                })
                continue
            except Exception as e:
                results.append({
                    "hh_resume_id": str(resume_id),
                    "status": "error",
                    "candidate_id": None,
                    "error": f"Ошибка получения резюме: {str(e)[:100]}",
                })
                continue

            # Создаём кандидата (+ Application для vacancy) короткой сессией
            try:
                async with AsyncSessionLocal() as create_session:
                    candidate = _create_candidate_from_resume(full_resume, company_id)
                    candidate.source = "smart"
                    candidate.extra = {
                        "smart_search": True,
                        "auto_search": True,
                        "saved_search_id": saved_search_id,
                        "hh_resume_id": str(resume_id),
                    }
                    create_session.add(candidate)
                    await create_session.flush()

                    # Опыт / навыки / образование из hh-резюме
                    for row in build_candidate_resume_sections(
                        candidate.id, company_id, full_resume
                    ):
                        create_session.add(row)

                    # target='vacancy' → Application(stage='added'); 'pool' → НЕ создавать
                    if target == "vacancy":
                        application = Application(
                            company_id=company_id,
                            candidate_id=candidate.id,
                            vacancy_id=target_vacancy_id,
                            stage="added",
                            hh_negotiation_id=None,
                        )
                        create_session.add(application)

                    # Audit: actor_type='human' (действие рекрутёра)
                    after = {
                        "target": target,
                        "saved_search_id": saved_search_id,
                        "hh_resume_id": str(resume_id),
                        "source": "smart",
                    }
                    if target == "vacancy":
                        after["vacancy_id"] = str(target_vacancy_id)
                    await audit(
                        create_session,
                        action="auto_search_take",
                        entity_type="candidate",
                        entity_id=candidate.id,
                        after=after,
                        actor_type="human",
                        actor_user_id=actor_user_id,
                        company_id=company_id,
                    )

                    # Best-effort PDF резюме в «Документы» (как при invite)
                    await hh_service.save_hh_resume_document(
                        session=create_session,
                        company_id=company_id,
                        candidate=candidate,
                        full_resume=full_resume,
                        access_token=access_token,
                        actor_user_id=actor_user_id,
                    )

                    await create_session.commit()
                    candidate_id = candidate.id

                taken += 1
                results.append({
                    "hh_resume_id": str(resume_id),
                    "status": "created",
                    "candidate_id": candidate_id,
                    "error": None,
                })
            except Exception as e:
                logger.error("[auto] Ошибка создания кандидата (take) %s: %s", resume_id, e)
                results.append({
                    "hh_resume_id": str(resume_id),
                    "status": "error",
                    "candidate_id": None,
                    "error": f"Ошибка создания кандидата: {str(e)[:100]}",
                })
                continue

        except (ValidationError, NotFoundError):
            raise
        except Exception as e:
            logger.error("[auto] Ошибка при «забирании» контакта %s: %s", resume_id, e)
            results.append({
                "hh_resume_id": str(resume_id),
                "status": "error",
                "candidate_id": None,
                "error": f"Внутренняя ошибка: {str(e)[:100]}",
            })
            continue

    # pool_left — best-effort после открытия контактов (новой короткой сессией)
    pool_left: int | None = None
    try:
        async with AsyncSessionLocal() as quota_session:
            pool_left = await _auto_pool_left(quota_session, company_id)
    except Exception as e:
        logger.warning("[auto] pool_left после take failed: %s", e)

    return {"results": results, "taken": taken, "pool_left": pool_left}
