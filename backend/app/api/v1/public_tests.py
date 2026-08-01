"""Публичный экзамен-API модуля «Тесты» (БЕЗ авторизации).

Кандидат получает ссылку /test/{token} и проходит тест. company_id определяется ТОЛЬКО
из TestAssignment по токену. Зеркалит public_schedule.py: крипто-токен, ленивое
истечение, in-memory rate-limit (30/60с per IP:token), единый конверт ошибок
HTTPException(detail={"error":{code,message}}). Монтируется в router.py с prefix="/public"
БЕЗ auth-гарда.

⚠️ БЕЗОПАСНОСТЬ-ЯДРО (см. schemas/public_test.py и services/tests_public.py):
  1. correct_option_id НИКОГДА не уходит клиенту — только body + options (id + params/text).
  2. Задания выдаются ПО ОДНОМУ (по current_item_index/current_block_id); банк целиком
     недоступен. Следующее — только после ответа на текущее.
  3. Таймер СЕРВЕРНЫЙ (started_at / block_started_at + duration). Ответ вне окна не
     засчитывается — «время истекло», блок/тест завершается, отвеченное сохранено.
  4. Ответы пишутся ПО МЕРЕ (каждый POST answer → TestAnswer сразу).
  5. Продвижение — атомарный conditional UPDATE (защита от двойного submit).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models import (
    Application,
    Company,
    TestAnswer,
    TestAssignment,
    TestAttempt,
    TestBlock,
    TestItem,
    Test,
)
from ...schemas.public_test import (
    PublicAnswerRequest,
    PublicAnswerResponse,
    PublicBlockInfo,
    PublicBlockNextResponse,
    PublicCurrentBlock,
    PublicCurrentResponse,
    PublicItem,
    PublicOption,
    PublicStartRequest,
    PublicStartResponse,
    PublicTestInfo,
)
from ...services import tests_public as svc

logger = logging.getLogger(__name__)

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Rate limiter (in-memory, best-effort) — как в public_schedule
# ──────────────────────────────────────────────────────────────────────────────
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = asyncio.Lock()
_RATE_LIMIT = 30
_RATE_WINDOW = 60.0


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    return forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )


async def _check_rate_limit(request: Request, token: str) -> None:
    key = f"{_client_ip(request)}:{token}"
    now = time.monotonic()
    async with _rate_lock:
        timestamps = [t for t in _rate_store[key] if now - t < _RATE_WINDOW]
        if len(timestamps) >= _RATE_LIMIT:
            _rate_store[key] = timestamps
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "RATE_LIMITED", "message": "Слишком много запросов. Попробуйте позже."}},
            )
        timestamps.append(now)
        _rate_store[key] = timestamps


# ──────────────────────────────────────────────────────────────────────────────
# Ошибки — единый конверт
# ──────────────────────────────────────────────────────────────────────────────
def _err(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


# ──────────────────────────────────────────────────────────────────────────────
# Загрузка/утилиты
# ──────────────────────────────────────────────────────────────────────────────
def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _load_assignment(session: AsyncSession, token: str) -> TestAssignment:
    a = (
        await session.execute(select(TestAssignment).where(TestAssignment.token == token))
    ).scalar_one_or_none()
    if a is None:
        raise _err(404, "NOT_FOUND", "Ссылка не найдена")
    return a


async def _maybe_expire(session: AsyncSession, assignment: TestAssignment, now: datetime) -> bool:
    """Ленивое истечение: expires_at в прошлом и тест ещё не завершён → status='expired'.

    Возвращает True, если назначение (сейчас) истёкшее. Завершённое (completed) НЕ истекает.
    """
    if assignment.status in ("completed", "cancelled"):
        return False
    exp = _aware(assignment.expires_at)
    if exp is not None and exp < now:
        if assignment.status != "expired":
            assignment.status = "expired"
            await session.commit()
        return True
    return assignment.status == "expired"


async def _load_test(session: AsyncSession, assignment: TestAssignment) -> Test:
    test = await session.get(Test, assignment.test_id)
    if test is None:
        raise _err(404, "NOT_FOUND", "Тест не найден")
    return test


def _to_public_item(item: TestItem, displayed: list[dict]) -> PublicItem:
    """⚠️ Публичное представление задания — БЕЗ correct_option_id и с ЭФЕМЕРНЫМИ id вариантов
    (реальный seed-id, с которым сервер сверяет верность, наружу НЕ уходит — см. svc.public_options)."""
    return PublicItem(
        id=str(item.id),
        kind=item.kind,
        body=item.body,
        options=[
            PublicOption(id=po["id"], params=po.get("params"), text=po.get("text"))
            for po in svc.public_options(displayed)
        ],
    )


def _instruction(test: Test, item_count: int, blocks: list[TestBlock]) -> str:
    if test.kind == "single":
        mins = int((test.duration_sec or 0) / 60)
        return (
            f"Тест «{test.name}» содержит {item_count} заданий. На каждое задание выберите "
            f"один вариант ответа. На весь тест отведено {mins} минут — по истечении времени "
            f"тест завершится автоматически, отвеченное сохранится. Переход только вперёд."
        )
    return (
        f"Тест «{test.name}» состоит из {len(blocks)} блоков, на каждый блок отведено своё "
        f"время. Отвечайте по одному заданию. Внутри блока можно возвращаться к предыдущим "
        f"заданиям и менять ответ; после перехода к следующему блоку возврат невозможен. "
        f"По истечении времени блока он завершается автоматически."
    )


def _completed_view() -> PublicCurrentResponse:
    # ⚠️ Ни задания, ни баллов — только факт завершения.
    return PublicCurrentResponse(status="completed", item=None)


async def _build_current_view(
    session: AsyncSession,
    *,
    assignment: TestAssignment,
    attempt: TestAttempt,
    test: Test,
    items: list[TestItem],
    blocks: list[TestBlock],
    now: datetime,
    review_index: Optional[int] = None,
) -> PublicCurrentResponse:
    """Строит представление ТЕКУЩЕГО задания. Может финализировать при истечении времени.

    ⚠️ Считает остаток времени сам (серверный таймер). Отдаёт ОДНО задание.
    """
    seed = attempt.options_seed
    single_items, by_block = svc.partition_items(items)

    # ── single: один общий таймер ────────────────────────────────────────────
    if test.kind == "single":
        started = _aware(attempt.started_at) or now
        end = started + timedelta(seconds=int(test.duration_sec or 0))
        if now >= end or attempt.current_item_index >= len(single_items):
            await svc.finalize_attempt(
                session, attempt=attempt, assignment=assignment, test=test,
                items=items, blocks=blocks, now=now,
            )
            return _completed_view()
        idx = attempt.current_item_index
        item = single_items[idx]
        disp = svc.displayed_options(item, seed)
        return PublicCurrentResponse(
            status="in_progress",
            index=idx,
            total=len(single_items),
            time_left_sec=max(0, int((end - now).total_seconds())),
            item=_to_public_item(item, disp),
        )

    # ── blocked: таймер на каждый блок ────────────────────────────────────────
    block_by_id = {b.id: b for b in blocks}
    block = block_by_id.get(attempt.current_block_id) if attempt.current_block_id else None
    if block is None:
        # Блок не установлен (не должно случаться после /start) — считаем тест завершённым.
        await svc.finalize_attempt(
            session, attempt=attempt, assignment=assignment, test=test,
            items=items, blocks=blocks, now=now,
        )
        return _completed_view()

    block_items = by_block.get(block.id, [])
    bstart = _aware(attempt.block_started_at) or now
    bend = bstart + timedelta(seconds=int(block.duration_sec or 0))
    block_done = now >= bend or attempt.current_item_index >= len(block_items)

    if block_done:
        # Следующий блок по порядку.
        pos = blocks.index(block)
        nxt = blocks[pos + 1] if pos + 1 < len(blocks) else None
        if nxt is None:
            await svc.finalize_attempt(
                session, attempt=attempt, assignment=assignment, test=test,
                items=items, blocks=blocks, now=now,
            )
            return _completed_view()
        return PublicCurrentResponse(
            status="awaiting_next_block",
            index=len(block_items),
            total=len(block_items),
            next_block_title=nxt.title,
        )

    # Активный блок: показываем текущее (или ранее пройденное — allow_back review).
    idx = attempt.current_item_index
    if (
        review_index is not None
        and test.allow_back
        and 0 <= review_index <= attempt.current_item_index
        and review_index < len(block_items)
    ):
        idx = review_index
    item = block_items[idx]
    disp = svc.displayed_options(item, seed)
    binfo = PublicCurrentBlock(
        index=blocks.index(block),
        total=len(blocks),
        key=block.key,
        title=block.title,
        time_left_sec=max(0, int((bend - now).total_seconds())),
    )
    return PublicCurrentResponse(
        status="in_progress",
        index=idx,
        total=len(block_items),
        block=binfo,
        item=_to_public_item(item, disp),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Эндпоинты
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/test/{token}/info", response_model=PublicTestInfo)
async def get_test_info(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Инфо-экран до старта. БЕЗ заданий/ответов/PII кандидата."""
    await _check_rate_limit(request, token)
    assignment = await _load_assignment(session, token)
    now = datetime.now(timezone.utc)

    test = await _load_test(session, assignment)
    items = await svc.load_items(session, test.id)
    blocks = await svc.load_blocks(session, test.id)

    # Статус для фронта: completed > expired > started > sent.
    if assignment.status == "completed":
        status = "completed"
    elif await _maybe_expire(session, assignment, now):
        status = "expired"
    else:
        attempt = await svc.get_attempt(session, assignment.id)
        status = "started" if (attempt and attempt.status == "in_progress") else assignment.status

    company = await session.get(Company, assignment.company_id)
    company_name = company.name if company else ""

    duration_min = int((test.duration_sec or 0) / 60) if test.kind == "single" else None
    block_infos = [
        PublicBlockInfo(
            index=i,
            key=b.key,
            title=b.title,
            item_count=b.item_count,
            duration_min=int((b.duration_sec or 0) / 60),
        )
        for i, b in enumerate(blocks)
    ]

    return PublicTestInfo(
        status=status,
        company_name=company_name,
        test_name=test.name,
        kind=test.kind,
        instruction=_instruction(test, len(items), blocks),
        item_count=len(items),
        duration_min=duration_min,
        blocks=block_infos,
    )


@router.post("/test/{token}/start", response_model=PublicStartResponse)
async def start_test(
    token: str,
    body: PublicStartRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Старт прохождения. ⚠️ Согласие обязательно; таймер стартует НА СЕРВЕРЕ.

    Идемпотентно: повторный /start при уже начатой попытке возвращает текущее состояние,
    НЕ пересоздаёт попытку и НЕ сбрасывает таймер (иначе это эксплойт продления времени).
    """
    await _check_rate_limit(request, token)
    assignment = await _load_assignment(session, token)
    now = datetime.now(timezone.utc)

    if assignment.status == "completed":
        raise _err(409, "TEST_COMPLETED", "Тест уже пройден")
    if await _maybe_expire(session, assignment, now):
        raise _err(410, "LINK_EXPIRED", "Срок ссылки истёк")

    if not body.consent:
        # ⚠️ 152-ФЗ: без согласия прохождение невозможно.
        raise _err(403, "CONSENT_REQUIRED", "Для прохождения теста требуется согласие на обработку данных")

    test = await _load_test(session, assignment)
    blocks = await svc.load_blocks(session, test.id)

    attempt = await svc.get_attempt(session, assignment.id)
    if attempt is not None and attempt.status == "in_progress":
        # Уже идёт — не трогаем таймер.
        return PublicStartResponse(status="started", kind=test.kind)
    if attempt is not None and attempt.status == "completed":
        raise _err(409, "TEST_COMPLETED", "Тест уже пройден")

    attempt = TestAttempt(
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        application_id=assignment.application_id,
        started_at=now,
        consent_agreed_at=now,
        consent_ip=_client_ip(request),
        current_item_index=0,
        status="in_progress",
    )
    if test.kind == "blocked" and blocks:
        attempt.current_block_id = blocks[0].id
        attempt.block_started_at = now
    session.add(attempt)
    await session.flush()
    # Seed рандомизации — детерминированно из id попытки (стабильно, воспроизводимо).
    attempt.options_seed = svc.seed_from_attempt(attempt.id)

    assignment.status = "started"

    from ...services.audit import audit
    await audit(
        session,
        action="test_started",
        entity_type="application",
        entity_id=assignment.application_id,
        after={
            "assignment_id": str(assignment.id),
            "attempt_id": str(attempt.id),
            "test_id": str(test.id),
            "consent_agreed_at": now.isoformat(),
        },
        actor_user_id=None,
        actor_type="system",
        company_id=assignment.company_id,
    )
    await session.commit()

    return PublicStartResponse(status="started", kind=test.kind)


@router.get("/test/{token}/current", response_model=PublicCurrentResponse)
async def get_current_item(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    index: Optional[int] = Query(default=None, ge=0),
):
    """Текущее (ОДНО) задание. Сервер сам считает остаток времени и авто-завершает
    блок/тест при истечении. `index` — обзор ранее пройденного в блоке (только allow_back).
    """
    await _check_rate_limit(request, token)
    assignment = await _load_assignment(session, token)
    now = datetime.now(timezone.utc)

    if assignment.status == "completed":
        return _completed_view()
    if await _maybe_expire(session, assignment, now):
        raise _err(410, "LINK_EXPIRED", "Срок ссылки истёк")

    attempt = await svc.get_attempt(session, assignment.id)
    if attempt is None or attempt.status != "in_progress":
        if attempt is not None and attempt.status == "completed":
            return _completed_view()
        raise _err(409, "NOT_STARTED", "Тест ещё не начат")

    test = await _load_test(session, assignment)
    items = await svc.load_items(session, test.id)
    blocks = await svc.load_blocks(session, test.id)

    return await _build_current_view(
        session, assignment=assignment, attempt=attempt, test=test,
        items=items, blocks=blocks, now=now, review_index=index,
    )


@router.post("/test/{token}/answer", response_model=PublicAnswerResponse)
async def submit_answer(
    token: str,
    body: PublicAnswerRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Ответ на задание. Сервер: (а) сверяет, что задание — текущее; (б) проверяет окно
    таймера; (в) считает is_correct САМ; (г) пишет TestAnswer; (д) АТОМАРНО продвигает
    индекс (защита от двойного submit). ⚠️ Ответ БЕЗ признака верности.
    """
    await _check_rate_limit(request, token)
    assignment = await _load_assignment(session, token)
    now = datetime.now(timezone.utc)

    if assignment.status == "completed":
        raise _err(409, "TEST_COMPLETED", "Тест уже пройден")
    if await _maybe_expire(session, assignment, now):
        raise _err(410, "LINK_EXPIRED", "Срок ссылки истёк")

    attempt = await svc.get_attempt(session, assignment.id)
    if attempt is None or attempt.status != "in_progress":
        if attempt is not None and attempt.status == "completed":
            raise _err(409, "TEST_COMPLETED", "Тест уже пройден")
        raise _err(409, "NOT_STARTED", "Тест ещё не начат")

    test = await _load_test(session, assignment)
    items = await svc.load_items(session, test.id)
    blocks = await svc.load_blocks(session, test.id)
    single_items, by_block = svc.partition_items(items)
    seed = attempt.options_seed

    # ── Определяем текущий поток заданий и окно таймера ────────────────────────
    if test.kind == "single":
        flow_items = single_items
        started = _aware(attempt.started_at) or now
        window_end = started + timedelta(seconds=int(test.duration_sec or 0))
        is_last_flow = True
    else:
        block_by_id = {b.id: b for b in blocks}
        block = block_by_id.get(attempt.current_block_id) if attempt.current_block_id else None
        if block is None:
            raise _err(409, "NO_ACTIVE_BLOCK", "Нет активного блока")
        flow_items = by_block.get(block.id, [])
        bstart = _aware(attempt.block_started_at) or now
        window_end = bstart + timedelta(seconds=int(block.duration_sec or 0))
        pos = blocks.index(block)
        is_last_flow = pos + 1 >= len(blocks)

    cur_idx = attempt.current_item_index

    # ── Ищем задание из тела в текущем потоке ──────────────────────────────────
    target_pos = next((i for i, it in enumerate(flow_items) if str(it.id) == body.item_id), None)
    if target_pos is None:
        # Задание не из текущего блока/потока (или неизвестно) — отвечать нельзя.
        raise _err(409, "NOT_CURRENT_ITEM", "Это задание сейчас недоступно для ответа")

    # ── Окно таймера истекло → не засчитываем, завершаем блок/тест ─────────────
    if now >= window_end:
        if test.kind == "single" or is_last_flow:
            await svc.finalize_attempt(
                session, attempt=attempt, assignment=assignment, test=test,
                items=items, blocks=blocks, now=now,
            )
            raise _err(410, "TIME_EXPIRED", "Время истекло — тест завершён")
        # blocked, не последний блок: блок закрыт, дальше — через /block/next.
        raise _err(410, "BLOCK_TIME_EXPIRED", "Время блока истекло — перейдите к следующему блоку")

    target = flow_items[target_pos]
    displayed = svc.displayed_options(target, seed)
    resolved_id, is_correct = svc.resolve_choice(
        target, displayed, body.chosen_option_id, body.chosen_index
    )
    if resolved_id is None:
        raise _err(400, "INVALID_CHOICE", "Не выбран корректный вариант ответа")

    time_ms = body.time_ms if (body.time_ms is not None and body.time_ms >= 0) else None

    # ── Ответ на ТЕКУЩЕЕ (frontier) задание: атомарно продвигаем индекс ─────────
    if target_pos == cur_idx:
        advanced = await session.execute(
            update(TestAttempt)
            .where(TestAttempt.id == attempt.id, TestAttempt.current_item_index == cur_idx)
            .values(current_item_index=cur_idx + 1)
            .returning(TestAttempt.current_item_index)
        )
        if advanced.first() is None:
            # Кто-то уже продвинул индекс (двойной submit) — не дублируем.
            raise _err(409, "ALREADY_ANSWERED", "Ответ на это задание уже принят")
        attempt.current_item_index = cur_idx + 1

        await _upsert_answer(session, assignment, attempt, target, resolved_id, is_correct, time_ms, now)

        new_idx = cur_idx + 1
        # Поток/блок завершён?
        if new_idx >= len(flow_items):
            if test.kind == "single" or is_last_flow:
                await svc.finalize_attempt(
                    session, attempt=attempt, assignment=assignment, test=test,
                    items=items, blocks=blocks, now=now,
                )
                return PublicAnswerResponse(ok=True, status="completed")
            # blocked, не последний: ждём /block/next.
            await session.commit()
            return PublicAnswerResponse(ok=True, status="awaiting_next_block")

        await session.commit()
        return PublicAnswerResponse(ok=True, status="in_progress")

    # ── allow_back: перезапись ответа на РАНЕЕ пройденное задание в текущем блоке ─
    if test.kind == "blocked" and test.allow_back and target_pos < cur_idx:
        await _upsert_answer(session, assignment, attempt, target, resolved_id, is_correct, time_ms, now)
        await session.commit()
        return PublicAnswerResponse(ok=True, status="in_progress")

    # target_pos > cur_idx (или back без allow_back) — пропуск вперёд запрещён.
    raise _err(409, "NOT_CURRENT_ITEM", "Это задание сейчас недоступно для ответа")


async def _upsert_answer(
    session: AsyncSession,
    assignment: TestAssignment,
    attempt: TestAttempt,
    item: TestItem,
    resolved_id: Optional[str],
    is_correct: bool,
    time_ms: Optional[int],
    now: datetime,
) -> None:
    """Пишет/перезаписывает TestAnswer (unique attempt_id+item_id)."""
    existing = (
        await session.execute(
            select(TestAnswer).where(
                TestAnswer.attempt_id == attempt.id, TestAnswer.item_id == item.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.chosen_option_id = resolved_id
        existing.is_correct = is_correct
        existing.time_ms = time_ms
        existing.answered_at = now
    else:
        session.add(TestAnswer(
            company_id=assignment.company_id,
            attempt_id=attempt.id,
            item_id=item.id,
            chosen_option_id=resolved_id,
            is_correct=is_correct,
            time_ms=time_ms,
            answered_at=now,
        ))
    await session.flush()


@router.post("/test/{token}/block/next", response_model=PublicBlockNextResponse)
async def next_block(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Переход к следующему блоку (blocked). Таймер нового блока стартует ЭТИМ вызовом
    (пауза между блоками не ограничена). Между блоками — только вперёд.
    """
    await _check_rate_limit(request, token)
    assignment = await _load_assignment(session, token)
    now = datetime.now(timezone.utc)

    if assignment.status == "completed":
        raise _err(409, "TEST_COMPLETED", "Тест уже пройден")
    if await _maybe_expire(session, assignment, now):
        raise _err(410, "LINK_EXPIRED", "Срок ссылки истёк")

    attempt = await svc.get_attempt(session, assignment.id)
    if attempt is None or attempt.status != "in_progress":
        if attempt is not None and attempt.status == "completed":
            raise _err(409, "TEST_COMPLETED", "Тест уже пройден")
        raise _err(409, "NOT_STARTED", "Тест ещё не начат")

    test = await _load_test(session, assignment)
    if test.kind != "blocked":
        raise _err(400, "NOT_BLOCKED", "У этого теста нет блоков")

    items = await svc.load_items(session, test.id)
    blocks = await svc.load_blocks(session, test.id)
    _single, by_block = svc.partition_items(items)

    block_by_id = {b.id: b for b in blocks}
    block = block_by_id.get(attempt.current_block_id) if attempt.current_block_id else None
    if block is None:
        raise _err(409, "NO_ACTIVE_BLOCK", "Нет активного блока")

    block_items = by_block.get(block.id, [])
    bstart = _aware(attempt.block_started_at) or now
    bend = bstart + timedelta(seconds=int(block.duration_sec or 0))
    block_finished = attempt.current_item_index >= len(block_items) or now >= bend
    if not block_finished:
        # Нельзя покинуть активный блок с оставшимся временем/заданиями.
        raise _err(409, "BLOCK_NOT_FINISHED", "Текущий блок ещё не завершён")

    pos = blocks.index(block)
    nxt = blocks[pos + 1] if pos + 1 < len(blocks) else None
    if nxt is None:
        await svc.finalize_attempt(
            session, attempt=attempt, assignment=assignment, test=test,
            items=items, blocks=blocks, now=now,
        )
        return PublicBlockNextResponse(status="completed")

    # Стартуем следующий блок: индекс с нуля, таймер блока — СЕРВЕРНЫЙ, от now.
    attempt.current_block_id = nxt.id
    attempt.current_item_index = 0
    attempt.block_started_at = now
    await session.commit()

    nxt_items = by_block.get(nxt.id, [])
    return PublicBlockNextResponse(
        status="in_progress",
        block=PublicCurrentBlock(
            index=pos + 1,
            total=len(blocks),
            key=nxt.key,
            title=nxt.title,
            time_left_sec=int(nxt.duration_sec or 0),
        ),
    )
