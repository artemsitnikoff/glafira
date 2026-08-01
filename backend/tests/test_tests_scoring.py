"""Юнит-тесты движка расчёта модуля «Тесты» (чистые функции, без БД)."""
import re

from app.services import tests_scoring as ts


# ── Хелпер построения задания/ответа ───────────────────────────────────────────
def _item(order_index, kind="matrix", item_id=None):
    return {"id": item_id or f"i{order_index}", "order_index": order_index, "kind": kind}


def _ans(item_id, *, is_correct=False, chosen="o1", time_ms=30000, chosen_index=None):
    a = {"item_id": item_id, "chosen_option_id": chosen, "is_correct": is_correct, "time_ms": time_ms}
    if chosen_index is not None:
        a["chosen_index"] = chosen_index
    return a


# ── compute_raw_score / block_scores ───────────────────────────────────────────
def test_compute_raw_score_counts_correct():
    answers = [
        {"is_correct": True}, {"is_correct": False},
        {"is_correct": True}, {"is_correct": True}, {"is_correct": False},
    ]
    assert ts.compute_raw_score(answers) == 3
    assert ts.compute_raw_score([]) == 0


def test_compute_block_scores_groups_by_block():
    answers = [
        {"item_id": "a1", "is_correct": True},
        {"item_id": "a2", "is_correct": False},
        {"item_id": "b1", "is_correct": True},
        {"item_id": "b2", "is_correct": True},
        {"item_id": "x1", "is_correct": True},  # без блока — не попадает в разбивку
    ]
    item_block = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}
    scores = ts.compute_block_scores(answers, item_block)
    assert scores == {"A": 1, "B": 2}


# ── categorize (пороги «Логики») ───────────────────────────────────────────────
def test_categorize_bands():
    th = ts_thresholds()
    assert ts.categorize(20, th)["key"] == "high"
    assert ts.categorize(17, th)["key"] == "high"
    assert ts.categorize(16, th)["key"] == "above"
    assert ts.categorize(13, th)["key"] == "above"
    assert ts.categorize(12, th)["key"] == "medium"
    assert ts.categorize(9, th)["key"] == "medium"
    assert ts.categorize(8, th)["key"] == "below"
    assert ts.categorize(5, th)["key"] == "below"
    assert ts.categorize(4, th)["key"] == "low"
    assert ts.categorize(0, th)["key"] == "low"
    # маркеры проброшены
    assert ts.categorize(20, th)["marker"] == "🟢"
    assert ts.categorize(0, th)["marker"] == "🔴"


def test_categorize_none_thresholds():
    assert ts.categorize(15, None) is None
    assert ts.categorize(15, []) is None


def ts_thresholds():
    return [
        {"min": 17, "max": 20, "key": "high", "label": "Высокий", "marker": "🟢"},
        {"min": 13, "max": 16, "key": "above", "label": "Выше среднего", "marker": "🟢"},
        {"min": 9, "max": 12, "key": "medium", "label": "Средний", "marker": "🟡"},
        {"min": 5, "max": 8, "key": "below", "label": "Ниже среднего", "marker": "🟠"},
        {"min": 0, "max": 4, "key": "low", "label": "Низкий", "marker": "🔴"},
    ]


# ── percentile (скрыт при базе < 30) ───────────────────────────────────────────
def test_percentile_hidden_below_30():
    base29 = [10] * 29
    assert ts.percentile(10, base29) is None  # 29 < 30 → скрыт
    base30 = [10] * 30
    assert ts.percentile(10, base30) is not None  # ровно 30 → считается


def test_percentile_value():
    base = [10] * 15 + [20] * 15  # 30 прохождений
    # балл 15 выше всех «10» (15 из 30) → 50%
    assert ts.percentile(15, base) == 50
    assert ts.percentile(5, base) == 0     # ниже всех
    assert ts.percentile(25, base) == 100  # выше всех
    assert ts.percentile(20, base) == 50   # 20 не строго ниже 20 → только «10»


def test_percentile_custom_min_base():
    assert ts.percentile(3, [1, 2, 3, 4, 5], min_base=5) == 40  # 2 из 5 строго ниже 3


# ── validity_flags — каждый флаг ДИСКРИМИНИРУЮЩЕ (срабатывает и НЕ срабатывает) ─
def test_flag_too_fast_fires_and_control():
    items = [_item(i) for i in range(1, 6)]
    # быстрое: 5 сек на матрицу < 15 → флаг; ответы верные (нет реверс-градиента),
    # позиции разные (нет ровности)
    fast = [_ans(f"i{i}", is_correct=True, chosen=f"o{i}", time_ms=5000) for i in range(1, 6)]
    flags = ts.validity_flags(fast, items, expected_count=5)
    assert ts.FLAG_TOO_FAST in flags
    # контроль: 30 сек → нет флага
    slow = [_ans(f"i{i}", is_correct=True, chosen=f"o{i}", time_ms=30000) for i in range(1, 6)]
    assert ts.FLAG_TOO_FAST not in ts.validity_flags(slow, items, expected_count=5)


def test_flag_reverse_gradient_fires_and_control():
    orders = [1, 2, 3, 4, 17, 18, 19, 20]
    items = [_item(o) for o in orders]
    # блок A неверно, блок D верно → обратный градиент
    ans = []
    for o in orders:
        ans.append(_ans(f"i{o}", is_correct=(o >= 17), chosen=f"o{(o % 5) + 1}", time_ms=30000))
    flags = ts.validity_flags(ans, items, expected_count=8)
    assert ts.FLAG_REVERSE_GRADIENT in flags
    # контроль: A верно, D неверно → нет флага
    ctrl = []
    for o in orders:
        ctrl.append(_ans(f"i{o}", is_correct=(o < 5), chosen=f"o{(o % 5) + 1}", time_ms=30000))
    assert ts.FLAG_REVERSE_GRADIENT not in ts.validity_flags(ctrl, items, expected_count=8)


def test_flag_incomplete_fires_and_boundary():
    items = [_item(i) for i in range(1, 21)]  # 20 заданий
    # отвечено 14, пропущено 6 = 30% > 25% → флаг
    ans = [_ans(f"i{i}", is_correct=True, chosen=f"o{(i % 5) + 1}", time_ms=30000) for i in range(1, 15)]
    assert ts.FLAG_INCOMPLETE in ts.validity_flags(ans, items, expected_count=20)
    # граница: пропущено ровно 5 = 25%, НЕ > 25% → нет флага
    ans15 = [_ans(f"i{i}", is_correct=True, chosen=f"o{(i % 5) + 1}", time_ms=30000) for i in range(1, 16)]
    assert ts.FLAG_INCOMPLETE not in ts.validity_flags(ans15, items, expected_count=20)


def test_flag_uniform_position_fires_and_control():
    items = [_item(i) for i in range(1, 7)]
    # все ответы в позиции 'o3' → ровность (>=3 отвеченных)
    same = [_ans(f"i{i}", is_correct=(i % 2 == 0), chosen="o3", time_ms=30000) for i in range(1, 7)]
    assert ts.FLAG_UNIFORM_POSITION in ts.validity_flags(same, items, expected_count=6)
    # контроль: разные позиции → нет флага
    varied = [_ans(f"i{i}", is_correct=True, chosen=f"o{(i % 5) + 1}", time_ms=30000) for i in range(1, 7)]
    assert ts.FLAG_UNIFORM_POSITION not in ts.validity_flags(varied, items, expected_count=6)


def test_flag_uniform_needs_min_answered():
    items = [_item(1), _item(2)]
    # всего 2 одинаковых → меньше порога UNIFORM_MIN_ANSWERED → не флагуем
    ans = [_ans("i1", chosen="o2", time_ms=30000), _ans("i2", chosen="o2", time_ms=30000)]
    assert ts.FLAG_UNIFORM_POSITION not in ts.validity_flags(ans, items, expected_count=2)


def test_flag_uniform_uses_chosen_index_when_present():
    items = [_item(i) for i in range(1, 5)]
    # id вариантов разные, но позиция слота одна и та же → ровность
    ans = [_ans(f"i{i}", chosen=f"o{i}", chosen_index=2, time_ms=30000) for i in range(1, 5)]
    assert ts.FLAG_UNIFORM_POSITION in ts.validity_flags(ans, items, expected_count=4)


def test_flags_clean_run_has_none():
    items = [_item(i) for i in range(1, 21)]
    ans = [_ans(f"i{i}", is_correct=(i <= 12), chosen=f"o{(i % 5) + 1}", time_ms=40000) for i in range(1, 21)]
    assert ts.validity_flags(ans, items, expected_count=20) == []


def test_flag_messages_cover_all_codes():
    for code in (ts.FLAG_TOO_FAST, ts.FLAG_REVERSE_GRADIENT, ts.FLAG_INCOMPLETE, ts.FLAG_UNIFORM_POSITION):
        assert code in ts.FLAG_MESSAGES and ts.FLAG_MESSAGES[code]


# ── IQ нигде не считается и не фигурирует в коде движка ─────────────────────────
def test_no_iq_in_scoring_source():
    with open(ts.__file__, encoding="utf-8") as fh:
        src = fh.read()
    # слово-токен «iq» (регистронезависимо); \b не заматчит «unique»
    assert re.search(r"\biq\b", src, re.IGNORECASE) is None
