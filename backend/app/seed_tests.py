"""Сев банка заданий модуля «Тесты» (Фаза 1, data-слой).

Засевает ДВА теста для компании:
  • «Логика» (key='logic', kind='single', 18 мин) — 20 матриц 3×3 (аналог Равена SPM),
    построенных ПАРАМЕТРАМИ (ч/б геометрия, БЕЗ цвета). Правильный ответ — в
    отдельной колонке TestItem.correct_option_id, НЕ в body/options.
  • «Структура интеллекта» (key='intelligence', kind='blocked') — 4 блока
    (Исключение слова 15 / Аналогии 15 / Числовые ряды 15 / Обобщение 12 = 57 заданий).

Источник правды по банку и методике — project/docs/14a - Тесты - структура и задания.md.

Запуск (в контейнере backend на VPS):
    python -m app.seed_tests

⚠️ Идемпотентно: exists-guard по (company_id, test.key) — повторный вызов НЕ дублирует.
⚠️ ДЛЯ НОВОГО ТЕНАНТА сев запускается ОТДЕЛЬНО (не входит в app.seed / app.seed_demo):
    python -m app.seed_tests  — с нужным company_id (по умолчанию settings.DEFAULT_COMPANY_ID).

⚠️ Правильные ответы (correct_option_id) живут ТОЛЬКО на сервере — публичная фаза их
не сериализует. body (тело задания) и options (варианты) признака правильности не несут.
"""
import asyncio
import logging
import random
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Test, TestBlock, TestItem

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Домены атрибутов (только ч/б геометрия — НЕТ цвета) ─────────────────────────
SHAPE_DOMAIN = ["circle", "square", "triangle", "hexagon", "diamond", "star", "key"]
FILL_DOMAIN = ["empty", "hatch-h", "hatch-v", "dots", "solid"]
SIZE_DOMAIN = ["S", "M", "L"]
COUNT_DOMAIN = [1, 2, 3]
ROT_DOMAIN = [0, 45, 90, 135, 180]
# «Фигурные» линии внутри ячейки. Внутренний маркер D2 хранится в том же поле `lines`
# ОТДЕЛЬНЫМИ токенами 'inner:dot' / 'inner:cross' — чтобы не конфликтовать с фигурой
# (нужно в D20, где у ячейки есть И линия-фигура, И внутренний крест). Рендер их
# различает по префиксу. Это остаётся в разрешённом ключе `lines` и не вводит цвета.
LINE_DOMAIN = ["vert", "horiz", "diag-l", "diag-r", "arc-top", "arc-bottom"]

_DOMAINS = {
    "shape": SHAPE_DOMAIN,
    "fill": FILL_DOMAIN,
    "size": SIZE_DOMAIN,
    "count": COUNT_DOMAIN,
    "rot": ROT_DOMAIN,
}

# Категории теста «Логика» (стартовые, настраиваемые) — из спеки.
LOGIC_CATEGORY_THRESHOLDS = [
    {"min": 17, "max": 20, "key": "high", "label": "Высокий", "marker": "🟢"},
    {"min": 13, "max": 16, "key": "above", "label": "Выше среднего", "marker": "🟢"},
    {"min": 9, "max": 12, "key": "medium", "label": "Средний", "marker": "🟡"},
    {"min": 5, "max": 8, "key": "below", "label": "Ниже среднего", "marker": "🟠"},
    {"min": 0, "max": 4, "key": "low", "label": "Низкий", "marker": "🔴"},
]

LOGIC_DURATION_SEC = 18 * 60  # общий таймер теста «Логика»


# ── Хелперы построения ячейки ──────────────────────────────────────────────────
def c(shape=None, fill=None, size=None, count=None, rot=None, lines=None) -> dict:
    """Ячейка матрицы — ВСЕГДА ровно 6 ключей (None где атрибут не задействован).

    Никакого цвета: только shape/fill/size/count/rot/lines.
    """
    return {
        "shape": shape,
        "fill": fill,
        "size": size,
        "count": count,
        "rot": rot,
        "lines": list(lines) if lines is not None else None,
    }


def _copy(p: Optional[dict]) -> Optional[dict]:
    if p is None:
        return None
    return {k: (list(v) if isinstance(v, list) else v) for k, v in p.items()}


def _latin_row3(a, b, cc):
    """Латинский квадрат 3×3 с нижним рядом [a, b, cc] (D3 — распределение трёх)."""
    return [[cc, a, b], [b, cc, a], [a, b, cc]]


def _inner_lines(figure, inner_val):
    """Собрать поле lines: фигурные линии + токен внутреннего маркера D2."""
    out = list(figure) if figure else []
    if inner_val and inner_val != "none":
        out.append(f"inner:{inner_val}")
    return out or None


# ── Банк матриц «Логика» (20 шт., по нарастанию сложности) ──────────────────────
def _matrix_grids() -> list[dict]:
    """20 матриц: полная сетка 3×3 (с заполненной ячейкой-ответом [2][2]).

    correct = grid[2][2] (потом её обнуляем в body). Для A1/B6 дистракторы явные
    (из спеки), для прочих генерируются по 7 типам.
    """
    specs: list[dict] = []

    # ── Блок A (1 правило, difficulty=1) ──
    # A1 PP(size) — triangle/empty, размер S→M→L
    rowA1 = [c("triangle", "empty", "S"), c("triangle", "empty", "M"), c("triangle", "empty", "L")]
    specs.append(dict(
        key="A1", block="A", difficulty=1,
        grid=[list(map(_copy, rowA1)) for _ in range(3)],
        distractors_explicit=[
            c("triangle", "empty", "S"), c("triangle", "empty", "M"),
            c("circle", "empty", "L"), c("square", "empty", "L"),
            c("triangle", "solid", "L"), c("triangle", "empty", "L", rot=180),
            c("diamond", "empty", "L"),
        ],
    ))
    # A2 CR(shape=triangle)×PP(fill) empty→hatch-h→solid
    rowA2 = [c("triangle", "empty"), c("triangle", "hatch-h"), c("triangle", "solid")]
    specs.append(dict(key="A2", block="A", difficulty=1,
                      grid=[list(map(_copy, rowA2)) for _ in range(3)]))
    # A3 PP(count) star 1→2→3
    rowA3 = [c("star", count=1), c("star", count=2), c("star", count=3)]
    specs.append(dict(key="A3", block="A", difficulty=1,
                      grid=[list(map(_copy, rowA3)) for _ in range(3)]))
    # A4 D3(shape) латинский квадрат triangle/circle/square, row3=[triangle,circle,square]
    shp = _latin_row3("triangle", "circle", "square")
    specs.append(dict(key="A4", block="A", difficulty=1,
                      grid=[[c(shape=shp[r][cc]) for cc in range(3)] for r in range(3)]))

    # ── Блок B (2 правила, difficulty=2) ──
    # B5 D3(shape)×D3(fill)
    shp = _latin_row3("triangle", "circle", "square")
    fil = _latin_row3("solid", "empty", "hatch-h")
    specs.append(dict(key="B5", block="B", difficulty=2,
                      grid=[[c(shape=shp[r][cc], fill=fil[r][cc]) for cc in range(3)] for r in range(3)]))
    # B6 A/S union (линии): c3 = c1 ∪ c2
    gridB6 = [
        [c(lines=["horiz"]), c(lines=["arc-top"]), c(lines=["horiz", "arc-top"])],
        [c(lines=["diag-l"]), c(lines=["vert"]), c(lines=["diag-l", "vert"])],
        [c(lines=["vert"]), c(lines=["diag-r"]), c(lines=["vert", "diag-r"])],
    ]
    specs.append(dict(
        key="B6", block="B", difficulty=2, grid=gridB6,
        distractors_explicit=[
            c(lines=["vert"]), c(lines=["diag-r"]),
            c(lines=["vert", "diag-l"]), c(lines=["horiz", "diag-r"]),
            c(lines=["vert", "horiz", "diag-r"]),
            c(lines=["vert", "diag-r"], count=1, fill="dots"),  # лишний элемент (точка)
            c(lines=[]),  # пустая
        ],
    ))
    # B7 A/S subtraction: c3 = c1 − c2
    gridB7 = [
        [c(lines=["vert", "horiz", "arc-top"]), c(lines=["arc-top"]), c(lines=["vert", "horiz"])],
        [c(lines=["diag-l", "horiz", "arc-bottom"]), c(lines=["arc-bottom"]), c(lines=["diag-l", "horiz"])],
        [c(lines=["horiz", "diag-l", "diag-r"]), c(lines=["horiz"]), c(lines=["diag-l", "diag-r"])],
    ]
    specs.append(dict(key="B7", block="B", difficulty=2, grid=gridB7))
    # B8 A/S XOR: c3 = c1 ⊕ c2
    gridB8 = [
        [c(lines=["vert", "diag-r"]), c(lines=["diag-r", "horiz"]), c(lines=["vert", "horiz"])],
        [c(lines=["arc-top", "vert"]), c(lines=["vert", "diag-l"]), c(lines=["arc-top", "diag-l"])],
        [c(lines=["diag-l", "horiz"]), c(lines=["horiz", "arc-bottom"]), c(lines=["diag-l", "arc-bottom"])],
    ]
    specs.append(dict(key="B8", block="B", difficulty=2, grid=gridB8))
    # B9 PP(rotation)×CR(shape=key)
    gridB9 = [
        [c("key", rot=0), c("key", rot=45), c("key", rot=90)],
        [c("key", rot=45), c("key", rot=90), c("key", rot=135)],
        [c("key", rot=90), c("key", rot=135), c("key", rot=180)],
    ]
    specs.append(dict(key="B9", block="B", difficulty=2, grid=gridB9))
    # B10 PP(size)×PP(count) встречное: size L→M→S, count 1→2→3
    rowB10 = [c("triangle", size="L", count=1), c("triangle", size="M", count=2), c("triangle", size="S", count=3)]
    specs.append(dict(key="B10", block="B", difficulty=2,
                      grid=[list(map(_copy, rowB10)) for _ in range(3)]))

    # ── Блок C (2–3 правила, difficulty=3) ──
    # C11 D3(shape)×D3(fill)×CR(size=L)
    shp = _latin_row3("triangle", "circle", "square")
    fil = _latin_row3("solid", "empty", "hatch-h")
    specs.append(dict(key="C11", block="C", difficulty=3,
                      grid=[[c(shape=shp[r][cc], fill=fil[r][cc], size="L") for cc in range(3)] for r in range(3)]))
    # C12 A/S union × D3(фон-fill)
    fil = _latin_row3("dots", "empty", "hatch-v")
    lin = [
        [["horiz"], ["diag-l"], ["horiz", "diag-l"]],
        [["diag-r"], ["arc-bottom"], ["diag-r", "arc-bottom"]],
        [["vert"], ["arc-top"], ["vert", "arc-top"]],
    ]
    specs.append(dict(key="C12", block="C", difficulty=3,
                      grid=[[c(lines=lin[r][cc], fill=fil[r][cc]) for cc in range(3)] for r in range(3)]))
    # C13 PP(count)×D3(shape)×PP(size): hexagon×1/L, diamond×2/M, star×3/S
    shp = _latin_row3("hexagon", "diamond", "star")
    cnt = [1, 2, 3]
    siz = ["L", "M", "S"]
    specs.append(dict(key="C13", block="C", difficulty=3,
                      grid=[[c(shape=shp[r][cc], count=cnt[cc], size=siz[cc]) for cc in range(3)] for r in range(3)]))
    # C14 XOR × D3(rotation): row3 rot=[180,0,90]
    rot = _latin_row3(180, 0, 90)
    lin = [
        [["vert", "diag-r"], ["diag-r"], ["vert"]],
        [["horiz", "arc-top"], ["arc-top", "vert"], ["horiz", "vert"]],
        [["vert", "horiz"], ["horiz"], ["vert"]],
    ]
    specs.append(dict(key="C14", block="C", difficulty=3,
                      grid=[[c(lines=lin[r][cc], rot=rot[r][cc]) for cc in range(3)] for r in range(3)]))
    # C15 D2 (внутр. none/dot/cross), внешняя circle
    inn = _latin_row3("none", "dot", "cross")
    specs.append(dict(key="C15", block="C", difficulty=3,
                      grid=[[c(shape="circle", lines=_inner_lines(None, inn[r][cc])) for cc in range(3)] for r in range(3)]))
    # C16 D2 × PP(size): square, size S→M→L
    inn = _latin_row3("none", "dot", "cross")
    siz = ["S", "M", "L"]
    specs.append(dict(key="C16", block="C", difficulty=3,
                      grid=[[c(shape="square", size=siz[cc], lines=_inner_lines(None, inn[r][cc])) for cc in range(3)] for r in range(3)]))

    # ── Блок D (3+ правила, макс. сложность, difficulty=4) ──
    # D17 A/S union × PP(rotation 0/45/90) × CR(fill=hatch-h)
    rotc = [0, 45, 90]
    lin = [
        [["horiz"], ["arc-top"], ["horiz", "arc-top"]],
        [["diag-l"], ["vert"], ["diag-l", "vert"]],
        [["vert"], ["diag-r"], ["vert", "diag-r"]],
    ]
    specs.append(dict(key="D17", block="D", difficulty=4,
                      grid=[[c(lines=lin[r][cc], rot=rotc[cc], fill="hatch-h") for cc in range(3)] for r in range(3)]))
    # D18 D3(shape)×D3(fill)×PP(count)×CR(size=M)
    shp = _latin_row3("hexagon", "star", "diamond")
    fil = _latin_row3("solid", "empty", "hatch-v")
    cnt = [1, 2, 3]
    specs.append(dict(key="D18", block="D", difficulty=4,
                      grid=[[c(shape=shp[r][cc], fill=fil[r][cc], count=cnt[cc], size="M") for cc in range(3)] for r in range(3)]))
    # D19 D2 × D3(shape) × PP(size)
    shp = _latin_row3("triangle", "hexagon", "circle")
    inn = _latin_row3("none", "dot", "cross")
    siz = ["S", "M", "L"]
    specs.append(dict(key="D19", block="D", difficulty=4,
                      grid=[[c(shape=shp[r][cc], size=siz[cc], lines=_inner_lines(None, inn[r][cc])) for cc in range(3)] for r in range(3)]))
    # D20 XOR × D2 × PP(rotation): row3 inner=[dot,none,cross], фигура-XOR
    rotc = [0, 45, 90]
    inn = _latin_row3("dot", "none", "cross")
    fig = [
        [["diag-l", "arc-top"], ["arc-top"], ["diag-l"]],
        [["vert", "diag-r"], ["diag-r"], ["vert"]],
        [["vert", "horiz"], ["horiz"], ["vert"]],
    ]
    specs.append(dict(key="D20", block="D", difficulty=4,
                      grid=[[c(lines=_inner_lines(fig[r][cc], inn[r][cc]), rot=rotc[cc]) for cc in range(3)] for r in range(3)]))

    return specs


# ── Генерация дистракторов (7 типов) ───────────────────────────────────────────
def _pkey(p: dict):
    lines = p.get("lines")
    lk = tuple(sorted(map(str, lines))) if lines else ()
    return (p.get("shape"), p.get("fill"), p.get("size"), p.get("count"), p.get("rot"), lk)


def _figure_lines(p: dict) -> list:
    return [l for l in (p.get("lines") or []) if not str(l).startswith("inner:")]


def _inner_markers(p: dict) -> list:
    return [l for l in (p.get("lines") or []) if str(l).startswith("inner:")]


def _other_value(attr, v):
    dom = _DOMAINS[attr]
    idx = dom.index(v) if v in dom else 0
    return dom[(idx + 1) % len(dom)]


def _other_line(l):
    idx = LINE_DOMAIN.index(l) if l in LINE_DOMAIN else 0
    return LINE_DOMAIN[(idx + 1) % len(LINE_DOMAIN)]


def _diff(correct: dict) -> dict:
    """Тип 2 — ответ с ОДНИМ изменённым атрибутом."""
    for attr in ("size", "count", "rot", "fill", "shape"):
        if correct.get(attr) is not None:
            p = _copy(correct)
            p[attr] = _other_value(attr, correct[attr])
            return p
    fl = _figure_lines(correct)
    if fl:
        p = _copy(correct)
        p["lines"] = [_other_line(fl[0])] + fl[1:] + _inner_markers(correct)
        return p
    im = _inner_markers(correct)
    if im:
        p = _copy(correct)
        other = "inner:cross" if im[0] == "inner:dot" else "inner:dot"
        p["lines"] = [other]
        return p
    p = _copy(correct)
    p["rot"] = 45
    return p


def _incomplete(correct: dict) -> dict:
    """Тип 3 — правило применено ЧАСТИЧНО (на шаг короче)."""
    p = _copy(correct)
    if correct.get("size") is not None:
        p["size"] = {"L": "M", "M": "S", "S": "M"}[correct["size"]]
        return p
    if correct.get("count") is not None:
        p["count"] = correct["count"] - 1 if correct["count"] > 1 else correct["count"] + 1
        return p
    if correct.get("rot") is not None:
        p["rot"] = correct["rot"] - 45 if correct["rot"] >= 45 else correct["rot"] + 45
        return p
    fl = _figure_lines(correct)
    if len(fl) >= 2:
        p["lines"] = fl[:-1] + _inner_markers(correct)
        return p
    if correct.get("fill") is not None:
        i = FILL_DOMAIN.index(correct["fill"])
        p["fill"] = FILL_DOMAIN[i - 1] if i > 0 else FILL_DOMAIN[i + 1]
        return p
    return _diff(correct)


def _union_err(correct: dict) -> dict:
    """Тип 6 — лишний/недостающий элемент при A/S."""
    p = _copy(correct)
    fl = _figure_lines(correct)
    if fl:
        extra = next((l for l in LINE_DOMAIN if l not in fl), None)
        p["lines"] = (fl + ([extra] if extra else [])) + _inner_markers(correct)
        return p
    # не-линейная ячейка: добавляем спурьёзный элемент-линию
    p["lines"] = (correct.get("lines") or []) + ["arc-top"]
    return p


def _random_cell(correct: dict, rng: random.Random) -> dict:
    """Тип 7 — случайная правдоподобная ячейка того же семейства."""
    if _figure_lines(correct) or correct.get("lines") is not None or correct.get("shape") is None:
        k = rng.randint(1, 2)
        p = c(lines=rng.sample(LINE_DOMAIN, k))
        if correct.get("rot") is not None:
            p["rot"] = rng.choice(ROT_DOMAIN)
        if correct.get("fill") is not None:
            p["fill"] = rng.choice(FILL_DOMAIN)
        return p
    return c(
        shape=rng.choice(SHAPE_DOMAIN),
        fill=rng.choice(FILL_DOMAIN) if correct.get("fill") is not None else None,
        size=rng.choice(SIZE_DOMAIN) if correct.get("size") is not None else None,
        count=rng.choice(COUNT_DOMAIN) if correct.get("count") is not None else None,
        rot=rng.choice(ROT_DOMAIN) if correct.get("rot") is not None else None,
    )


def _make_distractors(correct: dict, grid: list, rng: random.Random) -> list[dict]:
    neighbor = grid[2][1]
    row_start = grid[2][0]
    wrong_pos = grid[0][2]
    cands = [
        _copy(neighbor),        # 1 Repetition (копия соседней ячейки)
        _diff(correct),         # 2 Difference (один атрибут изменён)
        _incomplete(correct),   # 3 Incomplete correlate
        _copy(row_start),       # 4 Wrong principle (другая закономерность — начало ряда)
        _copy(wrong_pos),       # 5 Matrix construction (элемент не из той позиции)
        _union_err(correct),    # 6 Union error
        _random_cell(correct, rng),  # 7 Random
    ]
    ck = _pkey(correct)
    out: list[dict] = []
    seen: set = set()
    for d in cands:
        dd = d
        tries = 0
        while _pkey(dd) == ck or _pkey(dd) in seen:
            dd = _random_cell(correct, rng)
            tries += 1
            if tries > 30:
                break
        if _pkey(dd) == ck:  # жёсткая гарантия: дистрактор НИКОГДА не равен верному
            dd = _copy(correct)
            dd["rot"] = _other_value("rot", dd.get("rot") if dd.get("rot") is not None else 0)
        out.append(dd)
        seen.add(_pkey(dd))
    return out


def _assemble_matrix_options(correct: dict, distractors: list[dict], order_index: int):
    """8 вариантов со стабильными id o1..o8; верный ставится на варьируемую позицию."""
    slots = [_copy(d) for d in distractors]
    ci = (order_index - 1) % 8
    slots.insert(ci, _copy(correct))
    options = [{"id": f"o{i + 1}", "params": slots[i]} for i in range(8)]
    return options, f"o{ci + 1}"


def build_logic_items(company_id: uuid.UUID, test_id: uuid.UUID) -> list[TestItem]:
    items: list[TestItem] = []
    for order_index, spec in enumerate(_matrix_grids(), start=1):
        grid = spec["grid"]
        correct = _copy(grid[2][2])
        body_cells = [[_copy(grid[r][cc]) for cc in range(3)] for r in range(3)]
        body_cells[2][2] = None  # ячейка-вопрос пустая
        body = {"cells": body_cells, "question_cell": [2, 2]}
        if spec.get("distractors_explicit"):
            distractors = [_copy(d) for d in spec["distractors_explicit"]]
        else:
            rng = random.Random(spec["key"])
            distractors = _make_distractors(correct, grid, rng)
        options, correct_id = _assemble_matrix_options(correct, distractors, order_index)
        items.append(TestItem(
            company_id=company_id,
            test_id=test_id,
            block_id=None,
            kind="matrix",
            order_index=order_index,
            difficulty=spec["difficulty"],
            body=body,
            options=options,
            correct_option_id=correct_id,
        ))
    return items


# ── Банк «Структура интеллекта» ────────────────────────────────────────────────
# (terms[5 слов], лишнее)
EXCLUSION_ITEMS = [
    (["стол", "стул", "шкаф", "диван", "ковёр"], "ковёр"),
    (["дождь", "снег", "град", "туман", "ветер"], "ветер"),
    (["метр", "литр", "килограмм", "градус", "циркуль"], "циркуль"),
    (["смелый", "решительный", "отважный", "злой", "храбрый"], "злой"),
    (["берёза", "сосна", "дуб", "клён", "тополь"], "сосна"),
    (["молоток", "пила", "отвёртка", "гвоздь", "рубанок"], "гвоздь"),
    (["секунда", "час", "год", "неделя", "скорость"], "скорость"),
    (["река", "озеро", "море", "пруд", "мост"], "мост"),
    (["делить", "умножать", "вычитать", "складывать", "читать"], "читать"),
    (["глаз", "ухо", "нос", "язык", "рука"], "рука"),
    (["директор", "менеджер", "бухгалтер", "вакансия", "инженер"], "вакансия"),
    (["круг", "квадрат", "треугольник", "куб", "ромб"], "куб"),
    (["быстро", "медленно", "стремительно", "скоро", "шумно"], "шумно"),
    (["нефть", "уголь", "газ", "торф", "гранит"], "гранит"),
    (["договор", "счёт", "накладная", "акт", "принтер"], "принтер"),
]

# (a, b, c, options[5], верный)
ANALOGY_ITEMS = [
    ("лес", "дерево", "библиотека", ["полка", "книга", "читатель", "здание", "тишина"], "книга"),
    ("врач", "лечить", "учитель", ["школа", "ученик", "учить", "доска", "урок"], "учить"),
    ("холод", "зима", "жара", ["солнце", "лето", "пляж", "пот", "июль"], "лето"),
    ("нож", "резать", "ручка", ["бумага", "писать", "чернила", "карман", "стол"], "писать"),
    ("слово", "буква", "предложение", ["текст", "точка", "слово", "смысл", "страница"], "слово"),
    ("рыба", "плавать", "птица", ["гнездо", "перо", "летать", "небо", "клюв"], "летать"),
    ("голод", "еда", "жажда", ["вода", "стакан", "пустыня", "сухость", "соль"], "вода"),
    ("начало", "конец", "вопрос", ["ответ", "знак", "тема", "диалог", "сомнение"], "ответ"),
    ("город", "улица", "дом", ["крыша", "комната", "окно", "подъезд", "адрес"], "комната"),
    ("композитор", "музыка", "архитектор", ["дом", "чертёж", "здание", "проект", "стройка"], "здание"),
    ("тепло", "термометр", "вес", ["масса", "гиря", "весы", "килограмм", "груз"], "весы"),
    ("ошибка", "исправить", "болезнь", ["врач", "лечить", "боль", "диагноз", "аптека"], "лечить"),
    ("зерно", "мука", "дерево", ["лес", "доска", "лист", "корень", "тень"], "доска"),
    ("резюме", "кандидат", "отчёт", ["цифры", "руководитель", "сотрудник", "таблица", "итог"], "сотрудник"),
    ("замок", "ключ", "задача", ["ответ", "решение", "условие", "сложность", "время"], "решение"),
]

# (последовательность, верное продолжение)
SERIES_ITEMS = [
    ([2, 4, 6, 8, 10, 12], 14),
    ([3, 6, 12, 24, 48], 96),
    ([1, 4, 9, 16, 25], 36),
    ([21, 18, 15, 12, 9], 6),
    ([2, 3, 5, 8, 12, 17], 23),
    ([64, 32, 16, 8, 4], 2),
    ([1, 2, 4, 7, 11, 16], 22),
    ([5, 10, 9, 18, 17, 34], 33),
    ([1, 1, 2, 3, 5, 8], 13),
    ([90, 45, 46, 23, 24, 12], 13),
    ([7, 14, 12, 24, 22, 44], 42),
    ([3, 7, 15, 31, 63], 127),
    ([100, 81, 64, 49, 36], 25),
    ([2, 6, 12, 20, 30, 42], 56),
    ([4, 5, 8, 13, 20, 29], 40),
]

# (слово1, слово2, options[5], верный)
GENERALIZATION_ITEMS = [
    ("пшеница", "рожь", ["еда", "злаки", "поле", "растения", "хлеб"], "злаки"),
    ("лампа", "свеча", ["огонь", "тепло", "источники света", "воск", "дом"], "источники света"),
    ("глаз", "ухо", ["голова", "лицо", "органы чувств", "нервы", "тело"], "органы чувств"),
    ("договор", "устав", ["бумага", "документы", "право", "текст", "юрист"], "документы"),
    ("час", "метр", ["число", "время", "единицы измерения", "прибор", "расстояние"], "единицы измерения"),
    ("яблоко", "груша", ["сад", "фрукты", "сладость", "дерево", "витамины"], "фрукты"),
    ("дождь", "снег", ["небо", "зима", "осадки", "вода", "погода"], "осадки"),
    ("молоток", "пила", ["железо", "стройка", "инструменты", "работа", "гвозди"], "инструменты"),
    ("прибыль", "убыток", ["деньги", "бизнес", "финансовые результаты", "отчёт", "налог"], "финансовые результаты"),
    ("роман", "поэма", ["книга", "литературные произведения", "автор", "чтение", "страницы"], "литературные произведения"),
    ("собеседование", "тестирование", ["HR", "отбор", "методы оценки кандидатов", "работа", "вопросы"], "методы оценки кандидатов"),
    ("смелость", "честность", ["человек", "качества характера", "поведение", "мораль", "поступок"], "качества характера"),
]

# Блоки «Структуры интеллекта»: (key, title, duration_sec)
INTELLIGENCE_BLOCKS = [
    ("exclusion", "Исключение слова", 300),
    ("analogy", "Аналогии", 360),
    ("series", "Числовые ряды", 480),
    ("generalization", "Обобщение", 360),
]


def _text_options_fixed(words: list[str], correct_word: str):
    """Варианты в порядке из спеки; стабильные id o1..oN; верный на своей позиции."""
    options = [{"id": f"o{i + 1}", "text": w} for i, w in enumerate(words)]
    correct_id = next(o["id"] for o in options if o["text"] == correct_word)
    return options, correct_id


def _series_distractors(seq: list[int], correct: int) -> list[int]:
    """4 правдоподобных дистрактора для числового ряда.

    Дистракторы = близкие «промахи» (±1, ±2) и результаты наивной ЛИНЕЙНОЙ
    экстраполяции (повтор последнего шага seq[-1]-seq[-2], повтор последнего члена).
    Это валидно: типичные ошибки — арифметическая описка на 1–2 и подстановка простого
    линейного правила вместо истинного (степенного/чередующегося). Берём первые 4
    различных положительных, не равных верному.
    """
    last = seq[-1]
    step = seq[-1] - seq[-2]
    pool = [correct + 1, correct - 1, correct + 2, correct - 2,
            last + step, correct + step, correct - step, last, last * 2, correct + 3]
    out: list[int] = []
    for v in pool:
        if isinstance(v, int) and v > 0 and v != correct and v not in out:
            out.append(v)
        if len(out) == 4:
            break
    k = correct + 4
    while len(out) < 4:  # страховка (для гипотетических вырожденных рядов)
        if k > 0 and k != correct and k not in out:
            out.append(k)
        k += 1
    return out


def _series_options(seq: list[int], correct: int):
    distr = _series_distractors(seq, correct)
    values = sorted(set([correct] + distr))  # числовая сортировка распределяет верный
    options = [{"id": f"o{i + 1}", "text": str(v)} for i, v in enumerate(values)]
    correct_id = next(o["id"] for o in options if o["text"] == str(correct))
    return options, correct_id


def _block_items(block_key: str, company_id, test_id, block_id) -> list[TestItem]:
    items: list[TestItem] = []
    if block_key == "exclusion":
        for i, (words, correct_word) in enumerate(EXCLUSION_ITEMS, start=1):
            options, cid = _text_options_fixed(words, correct_word)
            body = {"kind": "exclusion",
                    "prompt": "Из пяти слов четыре объединены общим признаком. Найдите лишнее.",
                    "terms": list(words)}
            items.append(TestItem(company_id=company_id, test_id=test_id, block_id=block_id,
                                  kind="text", order_index=i, difficulty=1,
                                  body=body, options=options, correct_option_id=cid))
    elif block_key == "analogy":
        for i, (a, b, cc, words, correct_word) in enumerate(ANALOGY_ITEMS, start=1):
            options, cid = _text_options_fixed(words, correct_word)
            body = {"kind": "analogy", "prompt": "a : b = c : ?",
                    "terms": {"a": a, "b": b, "c": cc}}
            items.append(TestItem(company_id=company_id, test_id=test_id, block_id=block_id,
                                  kind="text", order_index=i, difficulty=2,
                                  body=body, options=options, correct_option_id=cid))
    elif block_key == "series":
        for i, (seq, correct) in enumerate(SERIES_ITEMS, start=1):
            options, cid = _series_options(seq, correct)
            body = {"kind": "series", "prompt": "Продолжите числовой ряд одним числом.",
                    "terms": list(seq)}
            items.append(TestItem(company_id=company_id, test_id=test_id, block_id=block_id,
                                  kind="text", order_index=i, difficulty=3,
                                  body=body, options=options, correct_option_id=cid))
    elif block_key == "generalization":
        for i, (w1, w2, words, correct_word) in enumerate(GENERALIZATION_ITEMS, start=1):
            options, cid = _text_options_fixed(words, correct_word)
            body = {"kind": "generalization",
                    "prompt": "Найдите общее понятие для двух слов.",
                    "terms": [w1, w2]}
            items.append(TestItem(company_id=company_id, test_id=test_id, block_id=block_id,
                                  kind="text", order_index=i, difficulty=2,
                                  body=body, options=options, correct_option_id=cid))
    else:
        raise ValueError(f"unknown block key: {block_key}")
    return items


# ── Сев ────────────────────────────────────────────────────────────────────────
async def seed_logic_test(session: AsyncSession, company_id: uuid.UUID) -> bool:
    """Сев теста «Логика». Идемпотентно (guard по company_id+key). True — если создан."""
    existing = (
        await session.execute(
            select(Test).where(Test.company_id == company_id, Test.key == "logic")
        )
    ).scalar_one_or_none()
    if existing:
        logger.info("Test 'logic' already exists for company %s", company_id)
        return False

    test = Test(
        company_id=company_id,
        key="logic",
        name="Логика",
        kind="single",
        duration_sec=LOGIC_DURATION_SEC,
        randomize_options=True,
        allow_back=False,
        category_thresholds=LOGIC_CATEGORY_THRESHOLDS,
        auto_reject_below=None,
        status="active",
    )
    session.add(test)
    await session.flush()

    items = build_logic_items(company_id, test.id)
    for it in items:
        session.add(it)
    logger.info("Seeded test 'logic': %d matrix items", len(items))
    return True


async def seed_intelligence_test(session: AsyncSession, company_id: uuid.UUID) -> bool:
    """Сев теста «Структура интеллекта». Идемпотентно (guard по company_id+key)."""
    existing = (
        await session.execute(
            select(Test).where(Test.company_id == company_id, Test.key == "intelligence")
        )
    ).scalar_one_or_none()
    if existing:
        logger.info("Test 'intelligence' already exists for company %s", company_id)
        return False

    test = Test(
        company_id=company_id,
        key="intelligence",
        name="Структура интеллекта",
        kind="blocked",
        duration_sec=None,
        randomize_options=True,
        allow_back=True,  # внутри блока переход свободный
        category_thresholds=None,  # стартовых категорий для этого теста в спеке нет
        auto_reject_below=None,
        status="active",
    )
    session.add(test)
    await session.flush()

    total_items = 0
    for order_index, (bkey, title, duration) in enumerate(INTELLIGENCE_BLOCKS, start=1):
        block = TestBlock(
            company_id=company_id,
            test_id=test.id,
            key=bkey,
            title=title,
            order_index=order_index,
            duration_sec=duration,
            item_count=0,
        )
        session.add(block)
        await session.flush()

        items = _block_items(bkey, company_id, test.id, block.id)
        for it in items:
            session.add(it)
        block.item_count = len(items)
        total_items += len(items)
        logger.info("Seeded block '%s': %d items", bkey, len(items))

    logger.info("Seeded test 'intelligence': %d items across %d blocks", total_items, len(INTELLIGENCE_BLOCKS))
    return True


async def seed_tests(session: AsyncSession, company_id: Optional[uuid.UUID] = None) -> None:
    """Оркестрация сева обоих тестов для компании (идемпотентно)."""
    company_id = company_id or uuid.UUID(settings.DEFAULT_COMPANY_ID)
    await seed_logic_test(session, company_id)
    await seed_intelligence_test(session, company_id)


async def main() -> None:
    logger.info("Seeding tests bank")
    async with AsyncSessionLocal() as session:
        try:
            await seed_tests(session)
            await session.commit()
            logger.info("Tests seed completed")
        except Exception:
            await session.rollback()
            logger.exception("Tests seed failed")
            raise


if __name__ == "__main__":
    asyncio.run(main())
