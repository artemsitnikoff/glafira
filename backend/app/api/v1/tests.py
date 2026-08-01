"""Рекрутёрские (authenticated) эндпоинты модуля «Тесты».

Назначение теста кандидату (привязка к Application), переотправка/отмена, чтение
результатов рекрутёром (is_correct/ответы показывать МОЖНО — это авторизованный
сотрудник) и управление тестами компании (список/деталь/настройки).

RBAC: hiring_manager отсечён на уровне router.py (_deny_hm). Внутри — менеджер видит
только заявки своих вакансий (is_user_assigned_to_vacancy); справочник тестов и его
настройки — admin/recruiter (чтение) / admin (правка).

⚠️ Публичная безопасность фазы 2 не затрагивается: correct_option_id остаётся server-only
в публичных схемах; здесь рекрутёру отдаём верность ответов сознательно.
"""
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...core.errors import ForbiddenError, NotFoundError
from ...core.permissions import is_user_assigned_to_vacancy
from ...database import get_db
from ...deps import get_current_company_id, get_current_user
from ...models import (
    Application,
    Test,
    TestAnswer,
    TestAssignment,
    TestAttempt,
    TestBlock,
    TestItem,
    TestResult,
    User,
)
from ...schemas.tests import (
    TestAnswerRow,
    TestAssignmentOut,
    TestAssignRequest,
    TestBlockDetail,
    TestDetail,
    TestListItem,
    TestResultOut,
    TestUpdate,
)
from ...services import tests_scoring
from ...services.audit import audit
from ...services.tests_assign import assign_test, cancel_test, remind_test

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Хелперы
# ──────────────────────────────────────────────────────────────────────────────
async def _get_application_vacancy_id(
    session: AsyncSession, application_id: UUID, company_id: UUID
) -> UUID:
    """vacancy_id заявки (company-scoped). NotFoundError, если заявка не найдена/чужая."""
    row = (
        await session.execute(
            select(Application.vacancy_id).where(
                Application.id == application_id,
                Application.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Заявка")
    return row


async def _authorize_application(
    session: AsyncSession, current_user: User, application_id: UUID, company_id: UUID
) -> UUID:
    """Валидирует, что заявка есть в компании (иначе 404), и что менеджер к ней допущен
    (иначе 403). admin/recruiter — доступ ко всем заявкам компании. Возвращает vacancy_id."""
    vacancy_id = await _get_application_vacancy_id(session, application_id, company_id)
    if current_user.role == "manager":
        if not await is_user_assigned_to_vacancy(
            session, current_user.id, vacancy_id, company_id
        ):
            raise ForbiddenError("Нет доступа к данной заявке")
    return vacancy_id


def _category_label(thresholds, category_key) -> str | None:
    if not thresholds or not category_key:
        return None
    for band in thresholds:
        if isinstance(band, dict) and band.get("key") == category_key:
            return band.get("label")
    return None


def _validity_messages(flags) -> list[str]:
    return [
        tests_scoring.FLAG_MESSAGES[f]
        for f in (flags or [])
        if f in tests_scoring.FLAG_MESSAGES
    ]


def _option_content(opt: dict | None) -> dict | None:
    """Отображаемое наполнение варианта: {"params", "text"}. None — вариант не найден.

    Для matrix у варианта заполнен params (text=None), для text — наоборот. ⚠️ Только для
    ПРИВАТНОГО эндпоинта: разбор с правильным ответом отдаётся авторизованному рекрутёру.
    """
    if not isinstance(opt, dict):
        return None
    return {"params": opt.get("params"), "text": opt.get("text")}


async def _basic_assignment_out(
    session: AsyncSession, assignment: TestAssignment, company_id: UUID
) -> TestAssignmentOut:
    """TestAssignmentOut без результата (для assign/remind/cancel). Рефреш — чтобы
    подтянуть server_default created_at у только что созданной записи."""
    await session.refresh(assignment)
    trow = (
        await session.execute(
            select(Test.name, Test.kind).where(
                Test.id == assignment.test_id, Test.company_id == company_id
            )
        )
    ).first()
    url = (
        f"{settings.FRONTEND_BASE_URL}/test/{assignment.token}"
        if assignment.token
        else None
    )
    return TestAssignmentOut(
        id=assignment.id,
        test_id=assignment.test_id,
        test_name=trow.name if trow else "",
        test_kind=trow.kind if trow else "",
        status=assignment.status,
        channel=assignment.channel,
        url=url,
        expires_at=assignment.expires_at,
        created_at=assignment.created_at,
        result=None,
    )


async def _test_detail(
    session: AsyncSession, test_id: UUID, company_id: UUID
) -> TestDetail:
    test = (
        await session.execute(
            select(Test).where(Test.id == test_id, Test.company_id == company_id)
        )
    ).scalar_one_or_none()
    if test is None:
        raise NotFoundError("Тест")
    blocks = (
        await session.execute(
            select(TestBlock)
            .where(TestBlock.test_id == test_id, TestBlock.company_id == company_id)
            .order_by(TestBlock.order_index)
        )
    ).scalars().all()
    item_count = (
        await session.execute(
            select(func.count(TestItem.id)).where(
                TestItem.test_id == test_id, TestItem.company_id == company_id
            )
        )
    ).scalar_one()
    assigned_count = (
        await session.execute(
            select(func.count(TestAssignment.id)).where(
                TestAssignment.test_id == test_id,
                TestAssignment.company_id == company_id,
            )
        )
    ).scalar_one()
    return TestDetail(
        id=test.id,
        key=test.key,
        name=test.name,
        kind=test.kind,
        duration_sec=test.duration_sec,
        randomize_options=test.randomize_options,
        allow_back=test.allow_back,
        category_thresholds=test.category_thresholds,
        auto_reject_below=test.auto_reject_below,
        status=test.status,
        item_count=item_count,
        assigned_count=assigned_count,
        blocks=[
            TestBlockDetail(
                id=b.id,
                key=b.key,
                title=b.title,
                order_index=b.order_index,
                duration_sec=b.duration_sec,
                item_count=b.item_count,
            )
            for b in blocks
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Назначение теста (привязано к Application). assign объявлен РАНЬШЕ {assignment_id}/*.
# ──────────────────────────────────────────────────────────────────────────────
@router.post(
    "/applications/{application_id}/tests/assign",
    response_model=TestAssignmentOut,
    status_code=201,
)
async def assign_test_endpoint(
    application_id: UUID,
    data: TestAssignRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Назначить тест кандидату по заявке. Согласие ПдН здесь НЕ требуется (кандидат
    подписывает чекбоксом на публичной странице при старте прохождения)."""
    await _authorize_application(session, current_user, application_id, company_id)
    assignment = await assign_test(
        session,
        application_id=application_id,
        company_id=company_id,
        test_id=data.test_id,
        ttl_days=data.ttl_days,
        channel=data.channel,
        message=data.message,
        created_by=current_user.id,
    )
    await session.commit()
    return await _basic_assignment_out(session, assignment, company_id)


@router.post(
    "/applications/{application_id}/tests/{assignment_id}/remind",
    response_model=TestAssignmentOut,
)
async def remind_test_endpoint(
    application_id: UUID,
    assignment_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Переотправить ссылку (тот же токен) по активному назначению."""
    await _authorize_application(session, current_user, application_id, company_id)
    assignment = await remind_test(
        session,
        application_id=application_id,
        assignment_id=assignment_id,
        company_id=company_id,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return await _basic_assignment_out(session, assignment, company_id)


@router.post(
    "/applications/{application_id}/tests/{assignment_id}/cancel",
    response_model=TestAssignmentOut,
)
async def cancel_test_endpoint(
    application_id: UUID,
    assignment_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Отменить назначение теста (пройденный отменить нельзя — 409)."""
    await _authorize_application(session, current_user, application_id, company_id)
    assignment = await cancel_test(
        session,
        application_id=application_id,
        assignment_id=assignment_id,
        company_id=company_id,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return await _basic_assignment_out(session, assignment, company_id)


@router.get(
    "/applications/{application_id}/tests",
    response_model=list[TestAssignmentOut],
)
async def list_application_tests(
    application_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Назначения теста по заявке + результаты для completed (рекрутёру — с is_correct).

    Без N+1: назначения+тесты одним джойном; результаты/попытки/ответы/order_index —
    отдельными пакетными запросами по заявке.
    """
    await _authorize_application(session, current_user, application_id, company_id)

    assignment_rows = (
        await session.execute(
            select(TestAssignment, Test)
            .join(Test, TestAssignment.test_id == Test.id)
            .where(
                TestAssignment.application_id == application_id,
                TestAssignment.company_id == company_id,
            )
            .order_by(TestAssignment.created_at.desc())
        )
    ).all()

    # Результаты заявки (для completed). result.assignment_id может быть NULL (SET NULL).
    results = (
        await session.execute(
            select(TestResult).where(
                TestResult.application_id == application_id,
                TestResult.company_id == company_id,
            )
        )
    ).scalars().all()
    result_by_assignment = {
        r.assignment_id: r for r in results if r.assignment_id is not None
    }

    # Попытки заявки → latest per assignment (для сбора ответов).
    attempts = (
        await session.execute(
            select(TestAttempt).where(
                TestAttempt.application_id == application_id,
                TestAttempt.company_id == company_id,
            )
        )
    ).scalars().all()
    attempt_by_assignment: dict[UUID, TestAttempt] = {}
    for at in attempts:
        prev = attempt_by_assignment.get(at.assignment_id)
        if prev is None or (
            at.created_at and prev.created_at and at.created_at > prev.created_at
        ):
            attempt_by_assignment[at.assignment_id] = at

    # Ответы по попыткам (одним запросом).
    answers_by_attempt: dict[UUID, list[TestAnswer]] = defaultdict(list)
    attempt_ids = [at.id for at in attempts]
    if attempt_ids:
        ans_rows = (
            await session.execute(
                select(TestAnswer).where(TestAnswer.attempt_id.in_(attempt_ids))
            )
        ).scalars().all()
        for a in ans_rows:
            answers_by_attempt[a.attempt_id].append(a)

    # Полные задания по ОТВЕЧЕННЫМ item_ids — одним запросом (без N+1). Нужны для разбора
    # сессии: kind/body/options/correct_option_id (последний — только на этом приватном
    # эндпоинте, рекрутёру). company_id — defense-in-depth (item_ids уже транзитивно
    # company-scoped через attempts/answers, но фильтр не ослабляет доступ).
    item_ids = {a.item_id for al in answers_by_attempt.values() for a in al}
    items_by_id: dict[UUID, object] = {}  # значение — Row(id, order_index, kind, body, options, correct_option_id)
    if item_ids:
        item_rows = (
            await session.execute(
                select(
                    TestItem.id,
                    TestItem.order_index,
                    TestItem.kind,
                    TestItem.body,
                    TestItem.options,
                    TestItem.correct_option_id,
                ).where(
                    TestItem.id.in_(item_ids),
                    TestItem.company_id == company_id,
                )
            )
        ).all()
        items_by_id = {r.id: r for r in item_rows}

    out: list[TestAssignmentOut] = []
    for assignment, test in assignment_rows:
        url = (
            f"{settings.FRONTEND_BASE_URL}/test/{assignment.token}"
            if assignment.token
            else None
        )
        result_out = None
        if assignment.status == "completed":
            res = result_by_assignment.get(assignment.id)
            if res is not None:
                answer_rows: list[TestAnswerRow] = []
                at = attempt_by_assignment.get(assignment.id)
                if at is not None:
                    for a in answers_by_attempt.get(at.id, []):
                        item = items_by_id.get(a.item_id)
                        options = (getattr(item, "options", None) or []) if item is not None else []
                        by_opt = {o.get("id"): o for o in options if isinstance(o, dict)}
                        # Матч прямой: chosen_option_id/correct_option_id — РЕАЛЬНЫЕ seed-id
                        # вариантов (o1..o8), item.options хранят их же (публичный флоу резолвит
                        # эфемерную метку в реальный id перед персистом TestAnswer.chosen_option_id).
                        chosen_opt = (
                            by_opt.get(a.chosen_option_id)
                            if a.chosen_option_id is not None
                            else None
                        )
                        correct_opt = (
                            by_opt.get(item.correct_option_id) if item is not None else None
                        )
                        answer_rows.append(TestAnswerRow(
                            index=item.order_index if item is not None else 0,
                            item_id=a.item_id,
                            item_kind=item.kind if item is not None else "",
                            body=(getattr(item, "body", None) or {}) if item is not None else {},
                            chosen_option_id=a.chosen_option_id,
                            chosen=_option_content(chosen_opt),
                            correct=_option_content(correct_opt) or {"params": None, "text": None},
                            is_correct=a.is_correct,
                            time_ms=a.time_ms,
                        ))
                    answer_rows.sort(key=lambda r: r.index)
                result_out = TestResultOut(
                    raw_score=res.raw_score,
                    max_score=res.max_score,
                    block_scores=res.block_scores or {},
                    category=res.category,
                    category_label=_category_label(test.category_thresholds, res.category),
                    percentile=res.percentile,
                    validity_flags=res.validity_flags or [],
                    validity_messages=_validity_messages(res.validity_flags),
                    duration_sec=res.duration_sec,
                    completed_at=res.completed_at,
                    answers=answer_rows,
                )
        out.append(TestAssignmentOut(
            id=assignment.id,
            test_id=assignment.test_id,
            test_name=test.name,
            test_kind=test.kind,
            status=assignment.status,
            channel=assignment.channel,
            url=url,
            expires_at=assignment.expires_at,
            created_at=assignment.created_at,
            result=result_out,
        ))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Справочник тестов компании
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/tests", response_model=list[TestListItem])
async def list_tests(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    if current_user.role not in ("admin", "recruiter"):
        raise ForbiddenError("Недостаточно прав")

    tests = (
        await session.execute(
            select(Test).where(Test.company_id == company_id).order_by(Test.name)
        )
    ).scalars().all()

    item_counts = dict(
        (
            await session.execute(
                select(TestItem.test_id, func.count(TestItem.id))
                .where(TestItem.company_id == company_id)
                .group_by(TestItem.test_id)
            )
        ).all()
    )
    assigned_counts = dict(
        (
            await session.execute(
                select(TestAssignment.test_id, func.count(TestAssignment.id))
                .where(TestAssignment.company_id == company_id)
                .group_by(TestAssignment.test_id)
            )
        ).all()
    )

    return [
        TestListItem(
            id=t.id,
            key=t.key,
            name=t.name,
            kind=t.kind,
            status=t.status,
            item_count=item_counts.get(t.id, 0),
            assigned_count=assigned_counts.get(t.id, 0),
        )
        for t in tests
    ]


@router.get("/tests/{test_id}", response_model=TestDetail)
async def get_test_detail(
    test_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    if current_user.role not in ("admin", "recruiter"):
        raise ForbiddenError("Недостаточно прав")
    return await _test_detail(session, test_id, company_id)


@router.patch("/tests/{test_id}", response_model=TestDetail)
async def update_test(
    test_id: UUID,
    data: TestUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
):
    """Правка настроек теста (только admin). Обновление по model_fields_set — чтобы
    auto_reject_below можно было очистить в None (явно переданный null)."""
    if current_user.role != "admin":
        raise ForbiddenError("Недостаточно прав")

    test = (
        await session.execute(
            select(Test).where(Test.id == test_id, Test.company_id == company_id)
        )
    ).scalar_one_or_none()
    if test is None:
        raise NotFoundError("Тест")

    fields = data.model_fields_set
    changed: dict = {}
    for f in ("category_thresholds", "auto_reject_below", "randomize_options", "allow_back", "status"):
        if f in fields:
            setattr(test, f, getattr(data, f))
            changed[f] = getattr(data, f)

    if "blocks" in fields and data.blocks is not None:
        block_ids = [b.id for b in data.blocks]
        by_id: dict[UUID, TestBlock] = {}
        if block_ids:
            blocks = (
                await session.execute(
                    select(TestBlock).where(
                        TestBlock.id.in_(block_ids),
                        TestBlock.test_id == test_id,
                        TestBlock.company_id == company_id,
                    )
                )
            ).scalars().all()
            by_id = {b.id: b for b in blocks}
        updated_blocks: dict[str, int] = {}
        for upd in data.blocks:
            b = by_id.get(upd.id)
            if b is not None:
                b.duration_sec = upd.duration_sec
                updated_blocks[str(upd.id)] = upd.duration_sec
        if updated_blocks:
            changed["blocks"] = updated_blocks

    await audit(
        session,
        action="test_updated",
        entity_type="test",
        entity_id=test_id,
        after=changed,
        actor_user_id=current_user.id,
        actor_type="human",
        company_id=company_id,
    )
    await session.commit()
    return await _test_detail(session, test_id, company_id)
