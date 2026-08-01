"""Движок расчёта результатов модуля «Тесты» — ЧИСТЫЕ функции (без БД).

Тестируется без базы: на вход идут plain-структуры (dict'ы или объекты с атрибутами).
Функции переиспользует будущая фаза API при финализации прохождения.

⚠️ Балл в шкале коэффициента интеллекта НЕ считается и не возвращается НИГДЕ — нет
валидных норм → это была бы выдумка и юридический риск. Отдаём только сырой балл,
разбивку по блокам, категорию, перцентиль (при достаточной базе) и флаги достоверности.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

# Порог накопленной базы компании, ниже которого перцентиль СКРЫВАЕТСЯ.
PERCENTILE_MIN_BASE = 30

# Среднее время на матрицу (сек), ниже которого срабатывает флаг «слишком быстро».
FAST_MATRIX_SECONDS = 15

# Доля пропущенных заданий (по таймауту), выше которой срабатывает флаг «не завершено».
INCOMPLETE_SKIP_FRACTION = 0.25

# Минимум отвеченных заданий для флага «аномальная ровность» (иначе неинформативно).
UNIFORM_MIN_ANSWERED = 3

# Коды флагов достоверности.
FLAG_TOO_FAST = "too_fast"
FLAG_REVERSE_GRADIENT = "reverse_gradient"
FLAG_INCOMPLETE = "incomplete"
FLAG_UNIFORM_POSITION = "uniform_position"

# Человекочитаемые формулировки (для плашки «Результат может быть недостоверен: …»).
FLAG_MESSAGES = {
    FLAG_TOO_FAST: "слишком быстрое прохождение (среднее время на задание меньше 15 секунд)",
    FLAG_REVERSE_GRADIENT: "обратный градиент сложности (лёгкие задания решены хуже трудных)",
    FLAG_INCOMPLETE: "тест не завершён (более четверти заданий пропущено)",
    FLAG_UNIFORM_POSITION: "все ответы выбраны в одной и той же позиции",
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Единый доступ к полю dict'а или атрибута объекта."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def compute_raw_score(answers: Iterable[Any]) -> int:
    """Сырой балл = число верных ответов (без частичных)."""
    return sum(1 for a in answers if bool(_get(a, "is_correct", False)))


def compute_block_scores(answers: Iterable[Any], item_block: Mapping[Any, str]) -> dict[str, int]:
    """Разбивка верных ответов по блокам.

    item_block: item_id -> block_key. Ответы на задания без блока (single-тест)
    в разбивку не попадают.
    """
    scores: dict[str, int] = {}
    for a in answers:
        block_key = item_block.get(_get(a, "item_id"))
        if block_key is None:
            continue
        scores.setdefault(block_key, 0)
        if bool(_get(a, "is_correct", False)):
            scores[block_key] += 1
    return scores


def categorize(raw_score: int, thresholds: Optional[Sequence[Mapping[str, Any]]]) -> Optional[dict]:
    """Категория по настраиваемым порогам.

    thresholds — список бэндов {min, max, key, label, marker}. Возвращает бэнд,
    в диапазон которого [min; max] попал raw_score, либо None (нет порогов / не попал).
    """
    if not thresholds:
        return None
    for band in thresholds:
        lo = band.get("min")
        hi = band.get("max")
        if lo is None or hi is None:
            continue
        if lo <= raw_score <= hi:
            return {
                "key": band.get("key"),
                "label": band.get("label"),
                "marker": band.get("marker"),
            }
    return None


def percentile(
    raw_score: int,
    company_scores: Sequence[int],
    *,
    min_base: int = PERCENTILE_MIN_BASE,
) -> Optional[int]:
    """Перцентиль по накопленной базе КОМПАНИИ.

    percentile = (кандидатов с баллом СТРОГО ниже / всего) × 100.
    ⚠️ Возвращает None, если база < min_base (по умолчанию 30) — перцентиль скрывается.

    company_scores — все сырые баллы завершённых прохождений в компании (эта база
    и определяет достаточность выборки).
    """
    total = len(company_scores)
    if total < min_base:
        return None
    below = sum(1 for s in company_scores if s < raw_score)
    return int(round(below / total * 100))


def validity_flags(
    answers: Iterable[Any],
    items: Iterable[Any],
    *,
    expected_count: Optional[int] = None,
) -> list[str]:
    """Флаги достоверности результата (список кодов из FLAG_*).

    answers — ответы {item_id, chosen_option_id, is_correct, time_ms, chosen_index?}.
    items   — задания {id, order_index, kind}. order_index для «Логики» — 1..20
              (блок A = 1..4, блок D = 17..20).
    expected_count — сколько заданий всего было назначено (для доли пропусков); если
              None, берётся число заданий в items.
    """
    answers = list(answers)
    items = list(items)
    item_by_id = {_get(it, "id"): it for it in items}

    flags: list[str] = []

    # ── (1) Слишком быстро: среднее время на МАТРИЦУ < 15 сек ─────────────────
    matrix_times_ms: list[int] = []
    for a in answers:
        it = item_by_id.get(_get(a, "item_id"))
        if it is not None and _get(it, "kind") == "matrix":
            t = _get(a, "time_ms")
            if t is not None:
                matrix_times_ms.append(int(t))
    if matrix_times_ms:
        avg_sec = (sum(matrix_times_ms) / len(matrix_times_ms)) / 1000.0
        if avg_sec < FAST_MATRIX_SECONDS:
            flags.append(FLAG_TOO_FAST)

    # ── (2) Обратный градиент: верных в блоке D (17..20) > верных в блоке A (1..4) ─
    correct_by_order: dict[int, bool] = {}
    for a in answers:
        it = item_by_id.get(_get(a, "item_id"))
        if it is None:
            continue
        oi = _get(it, "order_index")
        if oi is not None:
            correct_by_order[int(oi)] = bool(_get(a, "is_correct", False))
    block_a = sum(1 for oi in range(1, 5) if correct_by_order.get(oi))
    block_d = sum(1 for oi in range(17, 21) if correct_by_order.get(oi))
    # Флаг имеет смысл только если оба блока реально присутствуют в задании.
    has_a = any(oi in correct_by_order for oi in range(1, 5))
    has_d = any(oi in correct_by_order for oi in range(17, 21))
    if has_a and has_d and block_d > block_a:
        flags.append(FLAG_REVERSE_GRADIENT)

    # ── (3) Не завершено: пропущено > 25% (по таймауту) ──────────────────────
    total = expected_count if expected_count is not None else len(items)
    if total > 0:
        answered_ids = {
            _get(a, "item_id")
            for a in answers
            if _get(a, "chosen_option_id") is not None
        }
        skipped = total - len(answered_ids)
        if skipped / total > INCOMPLETE_SKIP_FRACTION:
            flags.append(FLAG_INCOMPLETE)

    # ── (4) Аномальная ровность: все ответы в одной позиции ──────────────────
    positions: list[Any] = []
    for a in answers:
        if _get(a, "chosen_option_id") is None:
            continue
        # Предпочитаем позицию слота (chosen_index); иначе — id варианта.
        pos = _get(a, "chosen_index")
        if pos is None:
            pos = _get(a, "chosen_option_id")
        positions.append(pos)
    if len(positions) >= UNIFORM_MIN_ANSWERED and len(set(positions)) == 1:
        flags.append(FLAG_UNIFORM_POSITION)

    return flags
