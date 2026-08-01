"""Сервис публичного экзамен-флоу модуля «Тесты» (бизнес-логика, вне роутера).

Здесь живут:
  • детерминированная рандомизация порядка вариантов (воспроизводима по options_seed);
  • серверная проверка выбора (маппинг позиции/id → correct_option_id, is_correct СЧИТАЕТ
    сервер) — правильный ответ клиенту НЕ раскрывается;
  • финализация прохождения (расчёт TestResult через tests_scoring + Event + audit).

⚠️ КЛИЕНТУ НИКОГДА не отдаётся correct_option_id и признак верности. Функции ниже
работают с ним ТОЛЬКО на сервере.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Application,
    Event,
    TestAnswer,
    TestAssignment,
    TestAttempt,
    TestBlock,
    TestItem,
    TestResult,
)
from ..services.audit import audit
from ..services import tests_scoring

logger = logging.getLogger(__name__)

# Postgres INTEGER (int32) — options_seed влезает в 0..2^31-1.
_SEED_MOD = 2_147_483_647


def seed_from_attempt(attempt_id: uuid.UUID) -> int:
    """Детерминированный seed рандомизации из id попытки (стабилен, без Math.random)."""
    return attempt_id.int % _SEED_MOD


def displayed_options(item: TestItem, seed: Optional[int]) -> list[dict]:
    """Порядок вариантов, КАК ИХ ВИДИТ КАНДИДАТ — ВСЕГДА перемешан детерминированно секретным
    per-attempt seed (seed = seed_from_attempt(attempt.id), наружу НЕ уходит).

    ⚠️ АНТИ-УТЕЧКА (важно): перемешивание ОБЯЗАТЕЛЬНО, не опционально. Позиция верного варианта
    в банке выводима из order_index (а order_index — из публичного `index`), поэтому секретный
    shuffle делает ЭКРАННУЮ позицию верного непредсказуемой для клиента. Воспроизводимо на
    сервере: один и тот же (seed, item.id) → один порядок, поэтому позицию k можно принять и на
    любом последующем запросе смапить в тот же реальный вариант. seed=None (только вне активной
    попытки, напр. каталог) → натуральный порядок.
    """
    opts = [dict(o) for o in (item.options or [])]
    if seed is None:
        return opts
    rng = random.Random(f"{seed}:{item.id}")
    order = opts[:]
    rng.shuffle(order)
    return order


def ephemeral_option_id(pos: int) -> str:
    """Эфемерная метка варианта ПО ПОЗИЦИИ ПОКАЗА (o1..oN в выданном порядке).

    ⚠️ Реальный seed-id варианта (с ним завязан correct_option_id) клиенту НЕ раскрывается —
    наружу уходит только эта позиционная метка. Позиция верного = секретный per-attempt shuffle
    (см. displayed_options) → метка верного НЕ выводима из публичного `index`.
    """
    return f"o{pos + 1}"


def public_options(displayed: list[dict]) -> list[dict]:
    """Варианты для КЛИЕНТА: id = эфемерная позиция показа, params/text — как в банке.
    Реальный seed-id скрыт (не входит в публичный трафик)."""
    return [
        {"id": ephemeral_option_id(i), "params": o.get("params"), "text": o.get("text")}
        for i, o in enumerate(displayed)
    ]


def resolve_choice(
    item: TestItem,
    displayed: list[dict],
    chosen_option_id: Optional[str],
    chosen_index: Optional[int],
) -> tuple[Optional[str], bool]:
    """Возвращает (resolved_real_id, is_correct). ⚠️ Сверку с correct_option_id делает СЕРВЕР —
    ни это значение, ни признак верности наружу НЕ уходят.

    Выбор принимается по ЭФЕМЕРНОЙ метке позиции (o1..oN в ВЫДАННОМ порядке, см. public_options)
    ЛИБО по chosen_index — оба мапятся в позицию показа, затем в реальный вариант displayed[pos].
    Реальный seed-id клиенту неизвестен, прислать его напрямую нельзя. Возвращает (None, False),
    если выбор не задан/невалиден — вызывающий решает про 400.
    """
    pos: Optional[int] = None
    if chosen_index is not None and 0 <= chosen_index < len(displayed):
        pos = chosen_index
    elif chosen_option_id is not None:
        labels = [ephemeral_option_id(i) for i in range(len(displayed))]
        if chosen_option_id in labels:
            pos = labels.index(chosen_option_id)
    if pos is None:
        return None, False
    resolved = displayed[pos].get("id")  # реальный seed-id — для персиста/сверки на сервере
    return resolved, (resolved == item.correct_option_id)


async def get_attempt(session: AsyncSession, assignment_id: uuid.UUID) -> Optional[TestAttempt]:
    """Последняя попытка по назначению (в этом флоу она одна)."""
    return (
        await session.execute(
            select(TestAttempt)
            .where(TestAttempt.assignment_id == assignment_id)
            .order_by(TestAttempt.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def load_items(session: AsyncSession, test_id: uuid.UUID) -> list[TestItem]:
    return list(
        (
            await session.execute(
                select(TestItem)
                .where(TestItem.test_id == test_id)
                .order_by(TestItem.order_index, TestItem.id)
            )
        ).scalars().all()
    )


async def load_blocks(session: AsyncSession, test_id: uuid.UUID) -> list[TestBlock]:
    return list(
        (
            await session.execute(
                select(TestBlock)
                .where(TestBlock.test_id == test_id)
                .order_by(TestBlock.order_index, TestBlock.id)
            )
        ).scalars().all()
    )


def partition_items(items: list[TestItem]) -> tuple[list[TestItem], dict[uuid.UUID, list[TestItem]]]:
    """(single_items — без блока; items_by_block — id блока → список заданий)."""
    single: list[TestItem] = []
    by_block: dict[uuid.UUID, list[TestItem]] = {}
    for it in items:
        if it.block_id is None:
            single.append(it)
        else:
            by_block.setdefault(it.block_id, []).append(it)
    return single, by_block


async def finalize_attempt(
    session: AsyncSession,
    *,
    attempt: TestAttempt,
    assignment: TestAssignment,
    test,
    items: list[TestItem],
    blocks: list[TestBlock],
    now: Optional[datetime] = None,
) -> None:
    """Финализация прохождения: раскладка баллов, TestResult, Event(type='test'), audit.

    Идемпотентно: атомарный захват статуса in_progress→completed (RETURNING). Проиграл
    гонку (двойной submit / параллельный /current) → второй просто выходит, дубля нет.
    Коммитит сам.
    """
    now = now or datetime.now(timezone.utc)

    # Атомарный захват: только один запрос переведёт in_progress→completed и запишет итог.
    claimed = await session.execute(
        update(TestAttempt)
        .where(TestAttempt.id == attempt.id, TestAttempt.status == "in_progress")
        .values(status="completed", finished_at=now)
        .returning(TestAttempt.id)
    )
    if claimed.first() is None:
        # Уже финализировано другим запросом — синхронизируем инстанс и выходим.
        attempt.status = "completed"
        if attempt.finished_at is None:
            attempt.finished_at = now
        return
    attempt.status = "completed"
    attempt.finished_at = now

    # ── Ответы попытки ──────────────────────────────────────────────────────────
    answers = list(
        (
            await session.execute(
                select(TestAnswer).where(TestAnswer.attempt_id == attempt.id)
            )
        ).scalars().all()
    )
    item_by_id = {it.id: it for it in items}
    block_key_by_id = {b.id: b.key for b in blocks}

    # item_id → block_key (для разбивки по блокам).
    item_block: dict[uuid.UUID, str] = {}
    for it in items:
        if it.block_id is not None and it.block_id in block_key_by_id:
            item_block[it.id] = block_key_by_id[it.block_id]

    # ── Реконструкция экранной позиции выбора (для флага «ровность») ─────────────
    # Порядок вариантов перемешан детерминированно → chosen_index восстанавливаем по seed,
    # чтобы «всегда одна и та же позиция» ловилось даже при рандомизации.
    seed = attempt.options_seed
    ans_dicts: list[dict] = []
    for a in answers:
        it = item_by_id.get(a.item_id)
        chosen_index = None
        if it is not None and a.chosen_option_id is not None:
            disp = displayed_options(it, seed)
            for k, o in enumerate(disp):
                if o.get("id") == a.chosen_option_id:
                    chosen_index = k
                    break
        ans_dicts.append({
            "item_id": a.item_id,
            "chosen_option_id": a.chosen_option_id,
            "is_correct": a.is_correct,
            "time_ms": a.time_ms,
            "chosen_index": chosen_index,
        })

    total_items = len(items)
    raw_score = tests_scoring.compute_raw_score(ans_dicts)
    block_scores = tests_scoring.compute_block_scores(ans_dicts, item_block)
    category = tests_scoring.categorize(raw_score, test.category_thresholds)

    # Перцентиль — по НАКОПЛЕННОЙ базе компании (все прошлые результаты этого теста).
    company_scores = list(
        (
            await session.execute(
                select(TestResult.raw_score).where(
                    TestResult.company_id == assignment.company_id,
                    TestResult.test_id == test.id,
                )
            )
        ).scalars().all()
    )
    pct = tests_scoring.percentile(raw_score, company_scores)

    flags = tests_scoring.validity_flags(ans_dicts, items, expected_count=total_items)

    duration_sec: Optional[int] = None
    if attempt.started_at is not None:
        started = attempt.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        duration_sec = max(0, int((now - started).total_seconds()))

    result = TestResult(
        company_id=assignment.company_id,
        application_id=assignment.application_id,
        assignment_id=assignment.id,
        test_id=test.id,
        raw_score=raw_score,
        max_score=total_items,
        block_scores=block_scores,
        category=(category or {}).get("key") if category else None,
        percentile=pct,
        validity_flags=flags,
        duration_sec=duration_sec,
    )
    session.add(result)

    assignment.status = "completed"

    # ── Контекст для Event/audit (кандидат/вакансия) ────────────────────────────
    app = (
        await session.execute(
            select(Application).where(Application.id == assignment.application_id)
        )
    ).scalar_one_or_none()
    vacancy_id = app.vacancy_id if app else None
    candidate_id = assignment.candidate_id

    cat_label = (category or {}).get("label") if category else None
    ev_text = (
        f"Кандидат прошёл тест «{test.name}»: {raw_score} из {total_items}"
        + (f", категория: {cat_label}" if cat_label else "")
        + (f". Достоверность под вопросом ({len(flags)} флага(ов))" if flags else "")
        + "."
    )
    session.add(Event(
        company_id=assignment.company_id,
        type="test",
        actor_type="system",
        actor_user_id=None,
        text=ev_text,
        entities=[],
        candidate_id=candidate_id,
        vacancy_id=vacancy_id,
    ))

    await audit(
        session,
        action="test_completed",
        entity_type="application",
        entity_id=assignment.application_id,
        after={
            "test_id": str(test.id),
            "test_key": test.key,
            "raw_score": raw_score,
            "max_score": total_items,
            "block_scores": block_scores,
            "category": (category or {}).get("key") if category else None,
            "percentile": pct,
            "validity_flags": flags,
            "assignment_id": str(assignment.id),
            "attempt_id": str(attempt.id),
        },
        actor_user_id=None,
        actor_type="system",
        company_id=assignment.company_id,
    )

    # Авто-отказ по результату теста (opt-in: только если у теста задан порог auto_reject_below).
    # Сбой авто-отказа НЕ должен ронять финиш прохождения → savepoint + лог.
    try:
        from ..services.tests_assign import maybe_auto_reject
        async with session.begin_nested():
            await maybe_auto_reject(
                session, test=test, raw_score=raw_score,
                application_id=assignment.application_id, company_id=assignment.company_id,
            )
    except Exception:
        logger.exception("[tests] авто-отказ по результату теста не выполнен")

    await session.commit()
