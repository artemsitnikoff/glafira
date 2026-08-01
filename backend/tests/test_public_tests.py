"""Тесты публичного экзамен-API модуля «Тесты» (backend/app/api/v1/public_tests.py).

⚠️ Каждый тест — ДИСКРИМИНИРУЮЩИЙ (проверяет реальный инвариант, а не «мимо поля»):
  • correct_option_id / признак верности ОТСУТСТВУЮТ в трафике клиента (грепаем тело);
  • задания выдаются ПО ОДНОМУ; следующее — только после ответа;
  • таймер СЕРВЕРНЫЙ: ответ после истечения окна НЕ засчитывается, отвеченное сохранено;
  • подсчёт raw_score/категории/перцентиля; перцентиль скрыт при базе <30;
  • флаги достоверности сохраняются при финише;
  • повторное открытие завершённого → completed без формы/баллов;
  • токен чужой → 404, истёкший → 410, без consent → старт невозможен;
  • изоляция компаний; привязка к Application (2 вакансии → 2 независимых прохождения);
  • рандомизация options воспроизводима по options_seed.

Реальные фикстуры (минимальные Test/Item с ИЗВЕСТНЫМИ верными ответами) — чтобы можно
было и пройти корректно, и проверить подсчёт. Верный ответ читаем ИЗ БД (сервер вправе),
а вот в HTTP-ответе его быть НЕ должно — это и проверяем.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import (
    Application,
    Candidate,
    Company,
    Test,
    TestAnswer,
    TestAssignment,
    TestAttempt,
    TestBlock,
    TestItem,
    TestResult,
    User,
)
from app.core.security import get_password_hash


# ──────────────────────────────────────────────────────────────────────────────
# Фикстуры данных
# ──────────────────────────────────────────────────────────────────────────────

def _matrix_item(company_id, test_id, order_index, correct="o2"):
    body = {"cells": [[None, None, None], [None, None, None], [None, None, None]],
            "question_cell": [2, 2]}
    options = [
        {"id": "o1", "params": {"shape": "circle"}},
        {"id": "o2", "params": {"shape": "square"}},
        {"id": "o3", "params": {"shape": "triangle"}},
        {"id": "o4", "params": {"shape": "hexagon"}},
    ]
    return TestItem(
        company_id=company_id, test_id=test_id, block_id=None, kind="matrix",
        order_index=order_index, difficulty=1, body=body, options=options,
        correct_option_id=correct,
    )


def _text_item(company_id, test_id, block_id, order_index, correct="o3"):
    options = [{"id": f"o{i}", "text": w} for i, w in enumerate(["раз", "два", "три", "четыре"], start=1)]
    body = {"kind": "exclusion", "prompt": "Найдите лишнее.", "terms": ["раз", "два", "три", "четыре"]}
    return TestItem(
        company_id=company_id, test_id=test_id, block_id=block_id, kind="text",
        order_index=order_index, difficulty=1, body=body, options=options,
        correct_option_id=correct,
    )


@pytest_asyncio.fixture
async def mini_single_test(db_session, admin_user):
    """single-тест: 3 матрицы, все верные = 'o2'. Пороги: 3=high, 2=mid, 0-1=low."""
    test = Test(
        company_id=admin_user.company_id, key="mini_logic", name="Мини-логика",
        kind="single", duration_sec=600, randomize_options=True, allow_back=False,
        category_thresholds=[
            {"min": 3, "max": 3, "key": "high", "label": "Высокий", "marker": "🟢"},
            {"min": 2, "max": 2, "key": "mid", "label": "Средний", "marker": "🟡"},
            {"min": 0, "max": 1, "key": "low", "label": "Низкий", "marker": "🔴"},
        ],
        status="active",
    )
    db_session.add(test)
    await db_session.flush()
    items = [_matrix_item(admin_user.company_id, test.id, i) for i in (1, 2, 3)]
    for it in items:
        db_session.add(it)
    await db_session.commit()
    for it in items:
        await db_session.refresh(it)
    return {"test": test, "items": items}


@pytest_asyncio.fixture
async def mini_blocked_test(db_session, admin_user):
    """blocked-тест: 2 блока по 2 текстовых задания, allow_back=True. Все верные = 'o3'."""
    test = Test(
        company_id=admin_user.company_id, key="mini_intel", name="Мини-структура",
        kind="blocked", duration_sec=None, randomize_options=True, allow_back=True,
        category_thresholds=None, status="active",
    )
    db_session.add(test)
    await db_session.flush()
    blocks = []
    items = []
    for bi, key in enumerate(("b1", "b2"), start=1):
        block = TestBlock(
            company_id=admin_user.company_id, test_id=test.id, key=key,
            title=f"Блок {bi}", order_index=bi, duration_sec=300, item_count=2,
        )
        db_session.add(block)
        await db_session.flush()
        blocks.append(block)
        for oi in (1, 2):
            it = _text_item(admin_user.company_id, test.id, block.id, oi)
            db_session.add(it)
            items.append(it)
    await db_session.commit()
    for it in items:
        await db_session.refresh(it)
    return {"test": test, "blocks": blocks, "items": items}


@pytest_asyncio.fixture
async def application(db_session, admin_user, test_candidate, test_vacancy):
    app = Application(
        company_id=admin_user.company_id,
        candidate_id=test_candidate.id,
        vacancy_id=test_vacancy.id,
        stage="interview",
    )
    db_session.add(app)
    await db_session.flush()
    return app


async def _mk_assignment(db_session, company_id, application_id, candidate_id, test_id,
                         token=None, expires_days=14, status="sent"):
    token = token or secrets.token_urlsafe(32)
    a = TestAssignment(
        company_id=company_id, application_id=application_id, candidate_id=candidate_id,
        test_id=test_id, token=token, status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
    )
    db_session.add(a)
    await db_session.flush()
    return a


@pytest_asyncio.fixture
async def single_assignment(db_session, admin_user, application, mini_single_test):
    return await _mk_assignment(
        db_session, admin_user.company_id, application.id, application.candidate_id,
        mini_single_test["test"].id,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Хелперы прохождения
# ──────────────────────────────────────────────────────────────────────────────

async def _start(client, token, consent=True):
    return await client.post(f"/api/v1/public/test/{token}/start", json={"consent": consent})


async def _current(client, token, index=None):
    url = f"/api/v1/public/test/{token}/current"
    if index is not None:
        url += f"?index={index}"
    return await client.get(url)


async def _answer(client, token, item_id, chosen_option_id=None, chosen_index=None, time_ms=5000):
    payload = {"item_id": item_id, "time_ms": time_ms}
    if chosen_option_id is not None:
        payload["chosen_option_id"] = chosen_option_id
    if chosen_index is not None:
        payload["chosen_index"] = chosen_index
    return await client.post(f"/api/v1/public/test/{token}/answer", json=payload)


def _content_key(opt: dict):
    """Содержимое варианта (params/text) — им отличаем верный от дистракторов независимо от id."""
    return (opt.get("params"), opt.get("text"))


async def _answer_correct(client, token, item, time_ms=5000, index=None):
    """Отвечает ВЕРНО под контрактом эфемерных id (реальный correct_option_id клиенту не виден).

    Мимикрия реального решателя: берём ВЫДАННЫЕ /current варианты (в порядке показа, с
    эфемерными позиционными id), находим тот, чьё СОДЕРЖИМОЕ совпадает с верным вариантом банка
    (он уникален среди опций — дистрактор никогда не равен верному), и шлём его эфемерный id.
    index → обзор ранее пройденного задания блока (allow_back), иначе текущее (frontier).
    """
    correct = next(o for o in item.options if o["id"] == item.correct_option_id)
    served = (await _current(client, token, index=index)).json()["item"]["options"]
    target = next(s for s in served if _content_key(s) == _content_key(correct))
    return await _answer(client, token, str(item.id), chosen_option_id=target["id"], time_ms=time_ms)


async def _answer_wrong(client, token, item, time_ms=5000, index=None):
    """Отвечает НЕВЕРНО: любой выданный вариант, чьё содержимое НЕ равно верному."""
    correct = next(o for o in item.options if o["id"] == item.correct_option_id)
    served = (await _current(client, token, index=index)).json()["item"]["options"]
    target = next(s for s in served if _content_key(s) != _content_key(correct))
    return await _answer(client, token, str(item.id), chosen_option_id=target["id"], time_ms=time_ms)


# ──────────────────────────────────────────────────────────────────────────────
# 1. correct_option_id и признак верности ОТСУТСТВУЮТ в трафике клиента
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_correct_option_never_in_client_traffic(async_client, single_assignment, mini_single_test):
    token = single_assignment.token
    r = await async_client.get(f"/api/v1/public/test/{token}/info")
    assert r.status_code == 200, r.text
    assert "correct" not in r.text.lower()

    assert (await _start(async_client, token)).status_code == 200

    r = await _current(async_client, token)
    assert r.status_code == 200, r.text
    body = r.text.lower()
    # ⚠️ ГЛАВНАЯ проверка: ни слова про правильность в теле задания.
    assert "correct" not in body
    data = r.json()
    # Отдано РОВНО одно задание, не банк.
    assert data["item"] is not None
    assert data["total"] == 3
    assert data["index"] == 0
    opts = data["item"]["options"]
    assert len(opts) == 4
    for o in opts:
        assert set(o.keys()) <= {"id", "params", "text"}
        assert "correct" not in o
        assert "is_correct" not in o


@pytest.mark.asyncio
async def test_current_serves_one_item_not_whole_bank(async_client, single_assignment):
    token = single_assignment.token
    await _start(async_client, token)
    r = await _current(async_client, token)
    data = r.json()
    # В ответе одно поле item (не список заданий).
    assert isinstance(data["item"], dict)
    assert "items" not in data
    assert data["item"]["id"] is not None


# ──────────────────────────────────────────────────────────────────────────────
# 2. Задания по одному: нельзя получить N+1 без ответа на N
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_items_served_one_by_one(async_client, single_assignment, mini_single_test):
    token = single_assignment.token
    items = mini_single_test["items"]
    await _start(async_client, token)

    # Текущее — задание 0.
    r = await _current(async_client, token)
    assert r.json()["item"]["id"] == str(items[0].id)

    # Пытаемся ответить на задание 1 (следующее) — недоступно.
    r = await _answer(async_client, token, str(items[1].id), chosen_option_id="o2")
    assert r.status_code == 409
    assert "NOT_CURRENT_ITEM" in r.text

    # Текущее НЕ сдвинулось.
    r = await _current(async_client, token)
    assert r.json()["item"]["id"] == str(items[0].id)

    # Отвечаем на текущее — только теперь появляется следующее.
    r = await _answer(async_client, token, str(items[0].id), chosen_option_id="o2")
    assert r.status_code == 200, r.text
    r = await _current(async_client, token)
    assert r.json()["item"]["id"] == str(items[1].id)
    assert r.json()["index"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# 3. Серверный таймер: ответ после истечения окна НЕ засчитывается
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_server_timer_expired_answer_not_counted(
    async_client, db_session, single_assignment, mini_single_test
):
    token = single_assignment.token
    items = mini_single_test["items"]
    await _start(async_client, token)

    # Отвечаем на задание 0 ВЕРНО (сохраняется по мере).
    r = await _answer_correct(async_client, token, items[0])
    assert r.status_code == 200

    # Сдвигаем started_at в прошлое так, что окно теста истекло (duration=600с).
    attempt = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == single_assignment.id)
    )).scalar_one()
    attempt.started_at = datetime.now(timezone.utc) - timedelta(seconds=600 + 60)
    await db_session.flush()

    # Ответ на задание 1 ПОСЛЕ истечения — с любым (даже «быстрым») клиентским time_ms —
    # НЕ засчитывается: сервер отвечает «время истекло».
    r = await _answer(async_client, token, str(items[1].id), chosen_option_id="o2", time_ms=1)
    assert r.status_code == 410
    assert "TIME_EXPIRED" in r.text

    # Ответ на задание 0 (данный вовремя) СОХРАНЁН.
    saved = (await db_session.execute(
        select(TestAnswer).where(
            TestAnswer.attempt_id == attempt.id, TestAnswer.item_id == items[0].id
        )
    )).scalar_one_or_none()
    assert saved is not None
    assert saved.is_correct is True

    # Ответа на задание 1 НЕТ (не засчитан).
    not_saved = (await db_session.execute(
        select(TestAnswer).where(
            TestAnswer.attempt_id == attempt.id, TestAnswer.item_id == items[1].id
        )
    )).scalar_one_or_none()
    assert not_saved is None

    # Тест завершён финишем-по-таймауту: результат = только зачтённое (1 верный).
    result = (await db_session.execute(
        select(TestResult).where(TestResult.application_id == single_assignment.application_id)
    )).scalar_one()
    assert result.raw_score == 1
    assert result.max_score == 3


@pytest.mark.asyncio
async def test_current_after_expiry_auto_completes(
    async_client, db_session, single_assignment
):
    """GET /current после истечения общего окна → авто-финиш (status completed)."""
    token = single_assignment.token
    await _start(async_client, token)
    attempt = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == single_assignment.id)
    )).scalar_one()
    attempt.started_at = datetime.now(timezone.utc) - timedelta(seconds=700)
    await db_session.flush()

    r = await _current(async_client, token)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["item"] is None


# ──────────────────────────────────────────────────────────────────────────────
# 4. Подсчёт: raw_score / категория / перцентиль скрыт при базе <30
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scoring_and_percentile_hidden_small_base(
    async_client, db_session, single_assignment, mini_single_test
):
    token = single_assignment.token
    items = mini_single_test["items"]
    await _start(async_client, token)

    # Проходим ВЕРНО все 3 (верный = 'o2', читаем из объектов).
    for i, it in enumerate(items):
        cur = (await _current(async_client, token)).json()
        assert cur["item"]["id"] == str(it.id)
        r = await _answer_correct(async_client, token, it)
        assert r.status_code == 200, r.text
        if i < len(items) - 1:
            assert r.json()["status"] == "in_progress"
        else:
            assert r.json()["status"] == "completed"

    result = (await db_session.execute(
        select(TestResult).where(TestResult.application_id == single_assignment.application_id)
    )).scalar_one()
    assert result.raw_score == 3
    assert result.max_score == 3
    assert result.category == "high"          # порог 3=high
    assert result.percentile is None          # база компании < 30 → скрыт

    # Назначение и попытка — completed.
    await db_session.refresh(single_assignment)
    assert single_assignment.status == "completed"


@pytest.mark.asyncio
async def test_percentile_shown_when_base_reaches_30(
    async_client, db_session, admin_user, single_assignment, mini_single_test, application
):
    # Заранее наполняем базу компании 30 завершёнными результатами того же теста.
    test_id = mini_single_test["test"].id
    for _ in range(30):
        db_session.add(TestResult(
            company_id=admin_user.company_id,
            application_id=application.id,   # FK-валидный (тот же application)
            assignment_id=None,
            test_id=test_id,
            raw_score=1, max_score=3,
            block_scores={}, validity_flags=[],
        ))
    await db_session.commit()

    token = single_assignment.token
    items = mini_single_test["items"]
    await _start(async_client, token)
    for it in items:
        await _answer_correct(async_client, token, it)

    result = (await db_session.execute(
        select(TestResult).where(
            TestResult.application_id == single_assignment.application_id,
            TestResult.assignment_id == single_assignment.id,
        )
    )).scalar_one()
    # raw_score=3 против базы из 30 значений по 1 → выше всех → перцентиль 100 (не None).
    assert result.percentile is not None
    assert result.percentile == 100


# ──────────────────────────────────────────────────────────────────────────────
# 5. Флаги достоверности сохраняются при финише
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validity_flags_saved_on_finish(
    async_client, db_session, single_assignment, mini_single_test
):
    """Всё быстро (<15с/матрица) и всегда одна экранная позиция → флаги too_fast + uniform."""
    token = single_assignment.token
    items = mini_single_test["items"]
    await _start(async_client, token)
    for it in items:
        # chosen_index=0 → одна и та же ПОЗИЦИЯ на экране (реконструируется по seed на финише);
        # time_ms=1000 (<15000) → «слишком быстро».
        r = await _answer(async_client, token, str(it.id), chosen_index=0, time_ms=1000)
        assert r.status_code == 200, r.text

    result = (await db_session.execute(
        select(TestResult).where(TestResult.application_id == single_assignment.application_id)
    )).scalar_one()
    assert "too_fast" in result.validity_flags
    assert "uniform_position" in result.validity_flags


# ──────────────────────────────────────────────────────────────────────────────
# 6. Повторное открытие завершённого → completed без формы/баллов
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reopen_completed_no_form_no_scores(
    async_client, single_assignment, mini_single_test
):
    token = single_assignment.token
    items = mini_single_test["items"]
    await _start(async_client, token)
    for it in items:
        await _answer_correct(async_client, token, it)

    # info → completed, без заданий и без баллов.
    r = await async_client.get(f"/api/v1/public/test/{token}/info")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    assert "raw_score" not in r.text and "percentile" not in r.text

    # current → completed, форма НЕ отдаётся.
    r = await _current(async_client, token)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["item"] is None
    assert "correct" not in r.text.lower()

    # start повторно → 409 (тест уже пройден), форму не начинаем заново.
    r = await _start(async_client, token)
    assert r.status_code == 409
    assert "TEST_COMPLETED" in r.text


# ──────────────────────────────────────────────────────────────────────────────
# 7. Токены: чужой → 404, истёкший → 410, без consent → нельзя
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_token_404(async_client):
    r = await async_client.get("/api/v1/public/test/nonexistent_xyz/info")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_expired_token_410_on_actions(
    async_client, db_session, admin_user, application, mini_single_test
):
    a = await _mk_assignment(
        db_session, admin_user.company_id, application.id, application.candidate_id,
        mini_single_test["test"].id, expires_days=-1,   # уже истёк
    )
    # info → 200 со status='expired'
    r = await async_client.get(f"/api/v1/public/test/{a.token}/info")
    assert r.status_code == 200
    assert r.json()["status"] == "expired"
    # start (действие) → 410
    r = await _start(async_client, a.token)
    assert r.status_code == 410


@pytest.mark.asyncio
async def test_start_requires_consent(async_client, single_assignment):
    r = await _start(async_client, single_assignment.token, consent=False)
    assert r.status_code == 403
    assert "CONSENT_REQUIRED" in r.text


# ──────────────────────────────────────────────────────────────────────────────
# 8. Изоляция компаний: токен B отдаёт данные B, не A
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_company_isolation(async_client, db_session, admin_user, single_assignment):
    # Вторая компания со своим тестом/кандидатом/заявкой/токеном.
    c2 = Company(id=uuid.uuid4(), name="Company Two")
    db_session.add(c2)
    await db_session.flush()
    cand2 = Candidate(company_id=c2.id, last_name="Второй", first_name="Кандидат", source="manual")
    from app.models import Vacancy
    v2 = Vacancy(company_id=c2.id, name="Вакансия 2", status="active")
    db_session.add_all([cand2, v2])
    await db_session.flush()
    app2 = Application(company_id=c2.id, candidate_id=cand2.id, vacancy_id=v2.id, stage="interview")
    db_session.add(app2)
    await db_session.flush()
    t2 = Test(company_id=c2.id, key="mini_logic", name="Тест компании 2",
              kind="single", duration_sec=600, randomize_options=True, allow_back=False,
              status="active")
    db_session.add(t2)
    await db_session.flush()
    db_session.add(_matrix_item(c2.id, t2.id, 1))
    await db_session.flush()
    a2 = await _mk_assignment(db_session, c2.id, app2.id, cand2.id, t2.id)

    # Токен компании 2 → данные компании 2 (company из токена, не из «текущего юзера»).
    r = await async_client.get(f"/api/v1/public/test/{a2.token}/info")
    assert r.status_code == 200
    assert r.json()["company_name"] == "Company Two"
    assert r.json()["test_name"] == "Тест компании 2"

    # Токен компании A (админа) → его данные.
    r = await async_client.get(f"/api/v1/public/test/{single_assignment.token}/info")
    assert r.json()["company_name"] == "Test Company"


# ──────────────────────────────────────────────────────────────────────────────
# 9. Привязка к Application: 1 кандидат в 2 вакансиях → 2 независимых прохождения
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_applications_independent(
    async_client, db_session, admin_user, test_candidate, mini_single_test
):
    from app.models import Vacancy
    test_id = mini_single_test["test"].id
    items = mini_single_test["items"]

    v_a = Vacancy(company_id=admin_user.company_id, name="Вакансия A", status="active")
    v_b = Vacancy(company_id=admin_user.company_id, name="Вакансия B", status="active")
    db_session.add_all([v_a, v_b])
    await db_session.flush()
    app_a = Application(company_id=admin_user.company_id, candidate_id=test_candidate.id,
                        vacancy_id=v_a.id, stage="interview")
    app_b = Application(company_id=admin_user.company_id, candidate_id=test_candidate.id,
                        vacancy_id=v_b.id, stage="interview")
    db_session.add_all([app_a, app_b])
    await db_session.flush()
    a_a = await _mk_assignment(db_session, admin_user.company_id, app_a.id, test_candidate.id, test_id)
    a_b = await _mk_assignment(db_session, admin_user.company_id, app_b.id, test_candidate.id, test_id)

    # Прохождение A: все верно. Прохождение B: одно верно, дальше — пропуск по таймауту.
    await _start(async_client, a_a.token)
    for it in items:
        await _answer_correct(async_client, a_a.token, it)

    await _start(async_client, a_b.token)
    await _answer_correct(async_client, a_b.token, items[0])
    # Прочие два — неверно.
    await _answer_wrong(async_client, a_b.token, items[1])
    await _answer_wrong(async_client, a_b.token, items[2])

    res_a = (await db_session.execute(
        select(TestResult).where(TestResult.assignment_id == a_a.id)
    )).scalar_one()
    res_b = (await db_session.execute(
        select(TestResult).where(TestResult.assignment_id == a_b.id)
    )).scalar_one()
    assert res_a.application_id == app_a.id and res_a.raw_score == 3
    assert res_b.application_id == app_b.id and res_b.raw_score == 1
    # Разные попытки (независимость прохождений).
    att_a = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == a_a.id)
    )).scalar_one()
    att_b = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == a_b.id)
    )).scalar_one()
    assert att_a.id != att_b.id


# ──────────────────────────────────────────────────────────────────────────────
# 10. Рандомизация options воспроизводима (один attempt → стабильный порядок)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_options_order_reproducible(async_client, single_assignment):
    token = single_assignment.token
    await _start(async_client, token)
    r1 = await _current(async_client, token)
    r2 = await _current(async_client, token)
    # Эфемерные id — всегда позиционные o1..o4 (по порядку показа); СТАБИЛЬНОСТЬ перемешивания
    # проверяем по СОДЕРЖИМОМУ (params), т.к. именно порядок содержимого тасует секретный seed.
    order1 = [o["params"] for o in r1.json()["item"]["options"]]
    order2 = [o["params"] for o in r2.json()["item"]["options"]]
    assert order1 == order2, "Порядок вариантов должен быть стабилен между запросами"
    assert [o["id"] for o in r1.json()["item"]["options"]] == ["o1", "o2", "o3", "o4"]


# ──────────────────────────────────────────────────────────────────────────────
# 11. Двойной submit / повторный ответ на текущее не двигает индекс дважды
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_double_advance_on_repeat_answer(async_client, single_assignment, mini_single_test):
    token = single_assignment.token
    items = mini_single_test["items"]
    await _start(async_client, token)

    r = await _answer(async_client, token, str(items[0].id), chosen_option_id="o2")
    assert r.status_code == 200
    # Индекс продвинулся на 1.
    assert (await _current(async_client, token)).json()["index"] == 1

    # Повторный ответ на уже пройденное задание 0 (single, без allow_back) — отклонён,
    # индекс НЕ прыгает на 2.
    r = await _answer(async_client, token, str(items[0].id), chosen_option_id="o2")
    assert r.status_code == 409
    assert (await _current(async_client, token)).json()["index"] == 1


@pytest.mark.asyncio
async def test_idempotent_start_keeps_timer(async_client, db_session, single_assignment):
    """Повторный /start не пересоздаёт попытку и не сбрасывает started_at (анти-эксплойт)."""
    token = single_assignment.token
    await _start(async_client, token)
    att1 = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == single_assignment.id)
    )).scalar_one()
    started1 = att1.started_at

    await _start(async_client, token)
    atts = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == single_assignment.id)
    )).scalars().all()
    assert len(atts) == 1                    # не пересоздана
    assert atts[0].started_at == started1    # таймер не сброшен


# ──────────────────────────────────────────────────────────────────────────────
# 12. Blocked-флоу: блоки по одному, свой таймер, block_scores по блокам
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_blocked_flow_and_block_scores(
    async_client, db_session, admin_user, application, mini_blocked_test
):
    items = mini_blocked_test["items"]  # b1:[0,1], b2:[2,3]
    a = await _mk_assignment(
        db_session, admin_user.company_id, application.id, application.candidate_id,
        mini_blocked_test["test"].id,
    )
    token = a.token

    r = await _start(async_client, token)
    assert r.json()["kind"] == "blocked"

    # Блок 1: два задания, отдаются по одному, со своим таймером блока.
    cur = (await _current(async_client, token)).json()
    assert cur["status"] == "in_progress"
    assert cur["block"]["index"] == 0
    assert cur["block"]["time_left_sec"] > 0
    assert cur["item"]["id"] == str(items[0].id)

    r = await _answer_correct(async_client, token, items[0])
    assert r.json()["status"] == "in_progress"
    r = await _answer_correct(async_client, token, items[1])
    assert r.json()["status"] == "awaiting_next_block"

    # Между блоками — вперёд по /block/next; новый таймер блока стартует ЭТИМ вызовом.
    cur = (await _current(async_client, token)).json()
    assert cur["status"] == "awaiting_next_block"
    r = await async_client.post(f"/api/v1/public/test/{token}/block/next")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"
    assert r.json()["block"]["index"] == 1

    cur = (await _current(async_client, token)).json()
    assert cur["block"]["index"] == 1
    assert cur["item"]["id"] == str(items[2].id)

    r = await _answer_correct(async_client, token, items[2])
    assert r.json()["status"] == "in_progress"
    r = await _answer_correct(async_client, token, items[3])
    assert r.json()["status"] == "completed"

    result = (await db_session.execute(
        select(TestResult).where(TestResult.assignment_id == a.id)
    )).scalar_one()
    assert result.raw_score == 4
    assert result.block_scores == {"b1": 2, "b2": 2}


@pytest.mark.asyncio
async def test_block_timer_expired_blocks_answer(
    async_client, db_session, admin_user, application, mini_blocked_test
):
    """Истёкший таймер БЛОКА → ответ не засчитан (410 BLOCK_TIME_EXPIRED), тест не завершён."""
    items = mini_blocked_test["items"]
    a = await _mk_assignment(
        db_session, admin_user.company_id, application.id, application.candidate_id,
        mini_blocked_test["test"].id,
    )
    token = a.token
    await _start(async_client, token)

    attempt = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == a.id)
    )).scalar_one()
    attempt.block_started_at = datetime.now(timezone.utc) - timedelta(seconds=400)  # >300
    await db_session.flush()

    r = await _answer(async_client, token, str(items[0].id), chosen_option_id=items[0].correct_option_id)
    assert r.status_code == 410
    assert "BLOCK_TIME_EXPIRED" in r.text
    # Тест НЕ завершён (первый блок, впереди второй) — назначение всё ещё started.
    await db_session.refresh(a)
    assert a.status == "started"


@pytest.mark.asyncio
async def test_allow_back_overwrite_within_block(
    async_client, db_session, admin_user, application, mini_blocked_test
):
    """allow_back: можно вернуться к пройденному заданию блока и переписать ответ."""
    items = mini_blocked_test["items"]
    a = await _mk_assignment(
        db_session, admin_user.company_id, application.id, application.candidate_id,
        mini_blocked_test["test"].id,
    )
    token = a.token
    await _start(async_client, token)

    # Задание 0 — сначала НЕВЕРНО, продвигаемся.
    await _answer_wrong(async_client, token, items[0])
    # Возврат к заданию 0 (index=0) допустим и переписывает ответ на ВЕРНЫЙ.
    r = await _current(async_client, token, index=0)
    assert r.json()["item"]["id"] == str(items[0].id)
    r = await _answer_correct(async_client, token, items[0], index=0)
    assert r.status_code == 200

    attempt = (await db_session.execute(
        select(TestAttempt).where(TestAttempt.assignment_id == a.id)
    )).scalar_one()
    ans = (await db_session.execute(
        select(TestAnswer).where(
            TestAnswer.attempt_id == attempt.id, TestAnswer.item_id == items[0].id
        )
    )).scalar_one()
    assert ans.is_correct is True   # перезапись сработала
    # Frontier не улетел вперёд (всё ещё на задании 1).
    assert attempt.current_item_index == 1


# ──────────────────────────────────────────────────────────────────────────────
# 13. Rate-limit → 429
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_429(async_client, single_assignment):
    from app.api.v1.public_tests import _rate_store
    import time as _t

    token = single_assignment.token
    xff = "203.0.113.9"
    key = f"{xff}:{token}"
    _rate_store[key] = [_t.monotonic()] * 30
    r = await async_client.get(
        f"/api/v1/public/test/{token}/info", headers={"X-Forwarded-For": xff}
    )
    assert r.status_code == 429
    _rate_store.pop(key, None)


# ──────────────────────────────────────────────────────────────────────────────
# 14. ⚠️ Регресс BLOCKER-1 / MEDIUM-2: верный ответ НЕ выводится из публичного `index`
#     (раньше correct = o{(order_index-1)%8+1}, id вариантов стабильны → клиент вычислял
#      ответ из index. Теперь id вариантов — ЭФЕМЕРНЫЕ позиции показа, а позиция верного —
#      СЕКРЕТНЫЙ per-attempt shuffle). Тесты гоняют РЕАЛЬНЫЙ банк build_logic_items (не мок).
# ──────────────────────────────────────────────────────────────────────────────

def test_correct_answer_not_derivable_from_index():
    """Детерминированный эксплойт по формуле индекса (o{(index%8)+1}) больше НЕ даёт 100%.

    ⚠️ Дискриминирующий: без фикса (реальные id + приём выбора по реальному id) эксплойт давал
    20/20; с фиксом клиент видит лишь эфемерные метки, а верный сидит на секретной позиции.
    """
    from app.seed_tests import build_logic_items
    from app.services import tests_public as svc

    company_id, test_id = uuid.uuid4(), uuid.uuid4()
    items = build_logic_items(company_id, test_id)
    assert len(items) == 20
    # Разные item.id (в проде — из БД); без этого shuffle одинаков и тест слабее.
    for i, it in enumerate(items):
        it.id = uuid.UUID(int=1000 + i)
    seed = svc.seed_from_attempt(uuid.UUID(int=777))

    exploit_hits = 0
    for idx, item in enumerate(items):          # idx = current_item_index (0-based) == публичный index
        disp = svc.displayed_options(item, seed)
        pub = svc.public_options(disp)
        # Клиент видит ТОЛЬКО эфемерные позиционные метки o1..oN и содержимое — без признака верности.
        assert [o["id"] for o in pub] == [f"o{i + 1}" for i in range(len(disp))]
        assert all("correct" not in o for o in pub)
        _, is_corr = svc.resolve_choice(item, disp, f"o{(idx % 8) + 1}", None)
        exploit_hits += int(is_corr)
    assert exploit_hits < len(items), f"эксплойт o(index%8+1) всё ещё детерминирован: {exploit_hits}/20"


def test_resolve_by_shuffled_position_scores_correctly():
    """Легитимный выбор по эфемерной позиции верного варианта → is_correct True; соседняя → False.
    Сервер знает соответствие позиция→реальный вариант по options_seed (клиенту недоступному)."""
    from app.seed_tests import build_logic_items
    from app.services import tests_public as svc

    items = build_logic_items(uuid.uuid4(), uuid.uuid4())
    for i, it in enumerate(items):
        it.id = uuid.UUID(int=2000 + i)
    seed = svc.seed_from_attempt(uuid.UUID(int=42))
    for item in items[:6]:
        disp = svc.displayed_options(item, seed)
        correct_pos = next(i for i, o in enumerate(disp) if o["id"] == item.correct_option_id)
        rid, ok = svc.resolve_choice(item, disp, f"o{correct_pos + 1}", None)
        assert ok and rid == item.correct_option_id
        wrong_pos = (correct_pos + 1) % len(disp)
        _, ok2 = svc.resolve_choice(item, disp, f"o{wrong_pos + 1}", None)
        assert not ok2
