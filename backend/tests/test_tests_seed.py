"""Тесты сева банка заданий модуля «Тесты» (реальная тест-БД, фикстура db_session).

Модели импортируем через модуль (`from app.models import tests as tm`), чтобы имена
классов `Test*` не попадали в неймспейс тест-файла и не коллектились pytest'ом.
"""
import re
import uuid

from sqlalchemy import select

from app.models import Company
from app.models import tests as tm
from app import seed_tests as seed_mod
from app.services import tests_scoring as scoring_mod

ALLOWED_CELL_KEYS = {"shape", "fill", "size", "count", "rot", "lines"}


async def _make_company(db_session) -> uuid.UUID:
    comp = Company(id=uuid.uuid4(), name="Тест-компания для модуля Тесты")
    db_session.add(comp)
    await db_session.flush()
    return comp.id


def _correct_option(item):
    return next(o for o in item.options if o["id"] == item.correct_option_id)


# ── «Логика»: 20 матриц, ч/б, correct отделён ──────────────────────────────────
async def test_seed_logic_20_matrices(db_session):
    cid = await _make_company(db_session)
    await seed_mod.seed_tests(db_session, cid)
    await db_session.flush()

    logic = (
        await db_session.execute(
            select(tm.Test).where(tm.Test.company_id == cid, tm.Test.key == "logic")
        )
    ).scalar_one()
    assert logic.kind == "single"
    assert logic.duration_sec == 18 * 60
    assert logic.category_thresholds  # пороги категорий засеяны

    items = (
        await db_session.execute(
            select(tm.TestItem).where(tm.TestItem.test_id == logic.id)
        )
    ).scalars().all()
    assert len(items) == 20  # ровно 20 матриц

    for it in items:
        assert it.kind == "matrix"
        assert it.company_id == cid  # company-scoped
        # 8 вариантов, уникальные стабильные id
        ids = [o["id"] for o in it.options]
        assert len(ids) == 8
        assert len(set(ids)) == 8
        # РОВНО ОДИН correct_option_id, указывает на реальный вариант
        assert it.correct_option_id in ids
        # ⚠️ correct отделён: признака правильности НЕТ ни в options, ни в body
        for o in it.options:
            assert "correct" not in o and "is_correct" not in o
            assert set(o["params"].keys()) == ALLOWED_CELL_KEYS  # только 6 ключей, без цвета
        body_str = str(it.body)
        assert "correct" not in body_str and it.correct_option_id not in body_str
        # тело: 3×3, ячейка-вопрос [2][2] пустая, все ячейки без цвета
        cells = it.body["cells"]
        assert it.body["question_cell"] == [2, 2]
        assert len(cells) == 3 and all(len(row) == 3 for row in cells)
        assert cells[2][2] is None
        for r in range(3):
            for cc in range(3):
                cell = cells[r][cc]
                if cell is None:
                    continue
                assert set(cell.keys()) == ALLOWED_CELL_KEYS

    # сложность нарастает по блокам A/B/C/D (order 1-4 / 5-10 / 11-16 / 17-20)
    by_order = {it.order_index: it for it in items}
    assert by_order[1].difficulty == 1
    assert by_order[5].difficulty == 2
    assert by_order[11].difficulty == 3
    assert by_order[17].difficulty == 4


async def test_seed_logic_correct_answers_faithful(db_session):
    """Верные ответы из банка совпадают со спекой → тест дискриминирует."""
    cid = await _make_company(db_session)
    await seed_mod.seed_tests(db_session, cid)
    await db_session.flush()
    logic = (
        await db_session.execute(
            select(tm.Test).where(tm.Test.company_id == cid, tm.Test.key == "logic")
        )
    ).scalar_one()
    items = {
        it.order_index: it
        for it in (
            await db_session.execute(select(tm.TestItem).where(tm.TestItem.test_id == logic.id))
        ).scalars().all()
    }
    # A1 (order 1): PP(size) → triangle/empty/L
    a1 = _correct_option(items[1])["params"]
    assert a1["shape"] == "triangle" and a1["fill"] == "empty" and a1["size"] == "L"
    # B6 (order 6): A/S union → линии {vert, diag-r}
    b6 = _correct_option(items[6])["params"]
    assert sorted(b6["lines"]) == ["diag-r", "vert"]


# ── «Структура интеллекта»: 57 заданий в 4 блоках ──────────────────────────────
async def test_seed_intelligence_57_items(db_session):
    cid = await _make_company(db_session)
    await seed_mod.seed_tests(db_session, cid)
    await db_session.flush()

    intel = (
        await db_session.execute(
            select(tm.Test).where(tm.Test.company_id == cid, tm.Test.key == "intelligence")
        )
    ).scalar_one()
    assert intel.kind == "blocked"
    assert intel.duration_sec is None  # таймеры в блоках

    blocks = (
        await db_session.execute(
            select(tm.TestBlock).where(tm.TestBlock.test_id == intel.id).order_by(tm.TestBlock.order_index)
        )
    ).scalars().all()
    assert len(blocks) == 4
    counts = {b.key: b.item_count for b in blocks}
    assert counts == {"exclusion": 15, "analogy": 15, "series": 15, "generalization": 12}

    items = (
        await db_session.execute(
            select(tm.TestItem).where(tm.TestItem.test_id == intel.id)
        )
    ).scalars().all()
    assert len(items) == 57  # 15+15+15+12

    for it in items:
        assert it.kind == "text"
        assert it.company_id == cid
        assert it.block_id is not None
        ids = [o["id"] for o in it.options]
        assert len(ids) == 5  # ровно 5 вариантов
        assert len(set(ids)) == 5
        assert it.correct_option_id in ids
        for o in it.options:
            assert "text" in o
            assert "correct" not in o and "is_correct" not in o

    # item_count блока совпадает с реальным числом заданий
    for b in blocks:
        real = [it for it in items if it.block_id == b.id]
        assert len(real) == b.item_count


async def test_seed_intelligence_correct_answers_faithful(db_session):
    cid = await _make_company(db_session)
    await seed_mod.seed_tests(db_session, cid)
    await db_session.flush()
    intel = (
        await db_session.execute(
            select(tm.Test).where(tm.Test.company_id == cid, tm.Test.key == "intelligence")
        )
    ).scalar_one()
    blocks = {
        b.key: b
        for b in (
            await db_session.execute(select(tm.TestBlock).where(tm.TestBlock.test_id == intel.id))
        ).scalars().all()
    }

    async def _items(block_key):
        rows = (
            await db_session.execute(
                select(tm.TestItem)
                .where(tm.TestItem.block_id == blocks[block_key].id)
                .order_by(tm.TestItem.order_index)
            )
        ).scalars().all()
        return rows

    excl = await _items("exclusion")
    assert _correct_option(excl[0])["text"] == "ковёр"  # мебель vs ковёр
    ana = await _items("analogy")
    assert _correct_option(ana[0])["text"] == "книга"   # лес:дерево=библиотека:книга
    ser = await _items("series")
    assert _correct_option(ser[0])["text"] == "14"      # 2 4 6 8 10 12 → 14
    gen = await _items("generalization")
    assert _correct_option(gen[0])["text"] == "злаки"   # пшеница—рожь → злаки


async def test_series_options_include_distractors(db_session):
    """Для числовых рядов сгенерированы 5 вариантов = верный + 4 правдоподобных."""
    cid = await _make_company(db_session)
    await seed_mod.seed_tests(db_session, cid)
    await db_session.flush()
    intel = (
        await db_session.execute(
            select(tm.Test).where(tm.Test.company_id == cid, tm.Test.key == "intelligence")
        )
    ).scalar_one()
    series_block = (
        await db_session.execute(
            select(tm.TestBlock).where(tm.TestBlock.test_id == intel.id, tm.TestBlock.key == "series")
        )
    ).scalar_one()
    items = (
        await db_session.execute(
            select(tm.TestItem).where(tm.TestItem.block_id == series_block.id)
        )
    ).scalars().all()
    for it in items:
        texts = [o["text"] for o in it.options]
        assert len(texts) == 5 and len(set(texts)) == 5  # все различны
        assert all(t.lstrip("-").isdigit() for t in texts)  # числа


# ── Идемпотентность ────────────────────────────────────────────────────────────
async def test_seed_idempotent(db_session):
    cid = await _make_company(db_session)
    await seed_mod.seed_tests(db_session, cid)
    await db_session.flush()

    def _count(model):
        return db_session.execute(select(model).where(model.company_id == cid))

    tests1 = (await _count(tm.Test)).scalars().all()
    items1 = (await _count(tm.TestItem)).scalars().all()
    blocks1 = (await _count(tm.TestBlock)).scalars().all()
    assert len(tests1) == 2
    assert len(items1) == 77  # 20 матриц + 57 вербальных
    assert len(blocks1) == 4

    # повторный сев не дублирует
    await seed_mod.seed_tests(db_session, cid)
    await db_session.flush()
    tests2 = (await _count(tm.Test)).scalars().all()
    items2 = (await _count(tm.TestItem)).scalars().all()
    blocks2 = (await _count(tm.TestBlock)).scalars().all()
    assert len(tests2) == 2
    assert len(items2) == 77
    assert len(blocks2) == 4


async def test_seed_company_scoped(db_session):
    """Данные одной компании не видны другой."""
    cid_a = await _make_company(db_session)
    cid_b = await _make_company(db_session)
    await seed_mod.seed_tests(db_session, cid_a)
    await db_session.flush()

    items_a = (
        await db_session.execute(select(tm.TestItem).where(tm.TestItem.company_id == cid_a))
    ).scalars().all()
    items_b = (
        await db_session.execute(select(tm.TestItem).where(tm.TestItem.company_id == cid_b))
    ).scalars().all()
    assert len(items_a) == 77
    assert len(items_b) == 0  # компании B ничего не засеяли


# ── IQ не считается нигде в коде модуля ─────────────────────────────────────────
def test_no_iq_in_module_source():
    for mod in (seed_mod, scoring_mod, tm):
        with open(mod.__file__, encoding="utf-8") as fh:
            src = fh.read()
        assert re.search(r"\biq\b", src, re.IGNORECASE) is None, mod.__file__
