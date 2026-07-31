"""Тесты фичи «Вакансии: мои/остальные + разводящая» (бек-часть).

Проверяем два прокинутых в существующие ответы блока данных:
  1. GET /vacancies/sidebar → item несёт responsible_user_id (группировка Мои/Остальные).
  2. GET /vacancies (list) → каждый item несёт candidates_count / new_count / hired
     для карточек разводящей.

Ключевое: агрегаты РЕАЛЬНЫЕ (считаются GROUP BY по applications, company-scoped),
а не мок/константа — тесты дискриминирующие (значение меняется от реального
состояния этапов заявок). RBAC не изменён: рекрутёр/админ видят ВСЕ вакансии
компании, менеджер — только назначенные, hiring_manager отбит на роутере.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import get_password_hash
from app.models import Application, Candidate, User, Vacancy

pytestmark = pytest.mark.asyncio


async def _make_candidate(db: AsyncSession, company_id, **overrides) -> Candidate:
    defaults = dict(
        company_id=company_id,
        last_name="Кандидатов",
        first_name="Кандидат",
        source="manual",
    )
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    db.add(candidate)
    await db.flush()
    return candidate


async def _make_app(
    db: AsyncSession, *, company_id, vacancy_id, stage: str
) -> Application:
    """Заявка кандидата на вакансии в заданном этапе (для агрегатов)."""
    candidate = await _make_candidate(db, company_id)
    application = Application(
        company_id=company_id,
        candidate_id=candidate.id,
        vacancy_id=vacancy_id,
        stage=stage,
    )
    db.add(application)
    await db.flush()
    return application


async def _create_vacancy(
    client: AsyncClient, headers: dict, *, name: str, client_id: str, team: list[str] | None = None
) -> dict:
    payload = {"name": name, "client_id": client_id}
    if team is not None:
        payload["team"] = team
    resp = await client.post("/api/v1/vacancies", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _find(items: list[dict], vacancy_id: str) -> dict | None:
    return next((it for it in items if it["id"] == vacancy_id), None)


# ---------------------------------------------------------------------------
# ПРАВКА 2 — агрегаты в списке вакансий
# ---------------------------------------------------------------------------


async def test_list_carries_responsible_and_aggregates(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
    default_client: str,
):
    """Каждый item списка несёт responsible_user + candidates_count/new_count/hired.

    candidates_count = заявки с stage != 'rejected';
    new_count = stage in ('response','added'); hired = stage == 'hired'.
    """
    company_id = admin_user.company_id
    vac = await _create_vacancy(
        async_client, auth_headers, name="Аналитик данных",
        client_id=default_client, team=[str(admin_user.id)],
    )
    vac_id = vac["id"]

    # response (новая + в работе), added (новая + в работе), interview (в работе,
    # НЕ новая), rejected (НЕ в работе, исключается из candidates_count).
    await _make_app(db_session, company_id=company_id, vacancy_id=vac_id, stage="response")
    await _make_app(db_session, company_id=company_id, vacancy_id=vac_id, stage="added")
    await _make_app(db_session, company_id=company_id, vacancy_id=vac_id, stage="interview")
    await _make_app(db_session, company_id=company_id, vacancy_id=vac_id, stage="rejected")
    await db_session.commit()

    resp = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    item = _find(resp.json()["items"], vac_id)
    assert item is not None, "созданная вакансия должна быть в списке"

    # responsible_user (объект) уже был в VacancyDetail — не должен пропасть.
    assert item["responsible_user"] is not None
    assert item["responsible_user"]["id"] == str(admin_user.id)
    assert item["responsible_user_id"] == str(admin_user.id)

    # Агрегаты разводящей.
    assert item["candidates_count"] == 3, "rejected исключён из в работе"
    assert item["new_count"] == 2, "response + added"
    assert item["hired"] == 0


async def test_list_aggregates_zero_when_no_applications(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    default_client: str,
):
    """Вакансия без заявок → счётчики 0/0/0 (не None, не падение)."""
    vac = await _create_vacancy(
        async_client, auth_headers, name="Без заявок", client_id=default_client,
    )
    resp = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    item = _find(resp.json()["items"], vac["id"])
    assert item is not None
    assert item["candidates_count"] == 0
    assert item["new_count"] == 0
    assert item["hired"] == 0


async def test_list_hired_counter_is_real(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
    default_client: str,
):
    """Дискриминирующий тест hired: реальный перевод кандидата в 'hired' поднимает
    счётчик с 0 до 1 (не константа/мок). candidates_count при этом не падает —
    hired не входит в 'rejected'."""
    company_id = admin_user.company_id
    vac = await _create_vacancy(
        async_client, auth_headers, name="Тимлид", client_id=default_client,
    )
    vac_id = vac["id"]
    app = await _make_app(
        db_session, company_id=company_id, vacancy_id=vac_id, stage="interview"
    )
    await db_session.commit()

    # До перевода: hired == 0.
    resp = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    item = _find(resp.json()["items"], vac_id)
    assert item["hired"] == 0
    assert item["candidates_count"] == 1

    # Реальный перевод в 'hired' через боевой эндпоинт (создаёт Employee и т.п.).
    move = await async_client.post(
        f"/api/v1/applications/{app.id}/move",
        headers=auth_headers,
        json={"to_stage": "hired"},
    )
    assert move.status_code == 200, move.text
    assert move.json()["new_stage"] == "hired"

    # После перевода: hired вырос до 1, кандидат всё ещё «в работе» (не rejected).
    resp2 = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    item2 = _find(resp2.json()["items"], vac_id)
    assert item2["hired"] == 1, "hired должен отражать реальный этап заявки"
    assert item2["candidates_count"] == 1


async def test_list_hired_is_per_vacancy_not_constant(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
    default_client: str,
):
    """hired считается ПО КАЖДОЙ вакансии отдельно: вакансия с наймом → 1,
    соседняя без найма → 0 (константа дала бы одинаково)."""
    company_id = admin_user.company_id
    vac_hired = await _create_vacancy(
        async_client, auth_headers, name="С наймом", client_id=default_client,
    )
    vac_empty = await _create_vacancy(
        async_client, auth_headers, name="Без найма", client_id=default_client,
    )
    await _make_app(
        db_session, company_id=company_id, vacancy_id=vac_hired["id"], stage="hired"
    )
    await _make_app(
        db_session, company_id=company_id, vacancy_id=vac_empty["id"], stage="response"
    )
    await db_session.commit()

    resp = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    items = resp.json()["items"]
    assert _find(items, vac_hired["id"])["hired"] == 1
    assert _find(items, vac_empty["id"])["hired"] == 0


async def test_list_company_isolation(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
    default_client: str,
    second_company,
):
    """Список и агрегаты строго company-scoped: вакансия чужой компании не видна,
    её заявки не попадают в счётчики нашей вакансии."""
    my_company_id = admin_user.company_id
    my_vac = await _create_vacancy(
        async_client, auth_headers, name="Наша вакансия", client_id=default_client,
    )
    await _make_app(
        db_session, company_id=my_company_id, vacancy_id=my_vac["id"], stage="response"
    )

    # Чужая компания: своя вакансия + заявка (напрямую ORM).
    other_vac = Vacancy(
        company_id=second_company.id, name="Чужая вакансия", status="active",
    )
    db_session.add(other_vac)
    await db_session.flush()
    await _make_app(
        db_session, company_id=second_company.id, vacancy_id=other_vac.id, stage="hired"
    )
    await db_session.commit()

    resp = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = {it["id"] for it in items}
    assert str(other_vac.id) not in ids, "чужая вакансия не должна быть в списке"
    mine = _find(items, my_vac["id"])
    assert mine is not None
    assert mine["candidates_count"] == 1  # только наша заявка, чужая не подмешалась
    assert mine["hired"] == 0


async def test_list_recruiter_sees_all_company_vacancies(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    regular_user: User,
    default_client: str,
):
    """RBAC не изменён: рекрутёр видит ВСЕ вакансии компании, включая те, где он
    не в команде (группировка «мои/остальные» — только UX на фронте)."""
    vac_admin = await _create_vacancy(
        async_client, auth_headers, name="Вакансия админа",
        client_id=default_client, team=[str(admin_user.id)],
    )
    vac_none = await _create_vacancy(
        async_client, auth_headers, name="Вакансия без ответственного",
        client_id=default_client,
    )

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": regular_user.email, "password": "Glafira2026!"},
    )
    assert login.status_code == 200, login.text
    rec_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await async_client.get("/api/v1/vacancies", headers=rec_headers)
    assert resp.status_code == 200, resp.text
    ids = {it["id"] for it in resp.json()["items"]}
    # Обе вакансии видны рекрутёру, хотя он не назначен ни на одну.
    assert vac_admin["id"] in ids
    assert vac_none["id"] in ids


async def test_list_manager_sees_only_assigned(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    manager_user: User,
    manager_headers: dict[str, str],
    default_client: str,
):
    """RBAC для менеджера цел: видит только назначенные вакансии (фильтр не сломан
    добавлением агрегатов)."""
    assigned = await _create_vacancy(
        async_client, auth_headers, name="Назначена менеджеру",
        client_id=default_client, team=[str(manager_user.id)],
    )
    not_assigned = await _create_vacancy(
        async_client, auth_headers, name="Не назначена менеджеру",
        client_id=default_client, team=[str(admin_user.id)],
    )

    resp = await async_client.get("/api/v1/vacancies", headers=manager_headers)
    assert resp.status_code == 200, resp.text
    ids = {it["id"] for it in resp.json()["items"]}
    assert assigned["id"] in ids
    assert not_assigned["id"] not in ids


async def test_list_hiring_manager_forbidden(
    async_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """hiring_manager отбит на роутере вакансий (deny-by-default) → 403."""
    hm = User(
        company_id=admin_user.company_id,
        email="hm.vacancies@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Нанимающий Менеджер",
        role="hiring_manager",
        is_active=True,
    )
    db_session.add(hm)
    await db_session.commit()

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": hm.email, "password": "Glafira2026!"},
    )
    assert login.status_code == 200, login.text
    hm_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await async_client.get("/api/v1/vacancies", headers=hm_headers)
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# ПРАВКА 1 — sidebar responsible_user_id
# ---------------------------------------------------------------------------


async def test_sidebar_carries_responsible_user_id(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    default_client: str,
):
    """Каждый item сайдбара несёт responsible_user_id → возможна группировка
    «Мои / Остальные»: одна вакансия с ответственным (== админ), другая без."""
    mine = await _create_vacancy(
        async_client, auth_headers, name="Моя (сайдбар)",
        client_id=default_client, team=[str(admin_user.id)],
    )
    other = await _create_vacancy(
        async_client, auth_headers, name="Ничья (сайдбар)", client_id=default_client,
    )

    resp = await async_client.get("/api/v1/vacancies/sidebar", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    mine_item = _find(items, mine["id"])
    other_item = _find(items, other["id"])
    assert mine_item is not None and other_item is not None

    # Поле присутствует в контракте у КАЖДОГО item.
    assert "responsible_user_id" in mine_item
    assert "responsible_user_id" in other_item

    assert mine_item["responsible_user_id"] == str(admin_user.id)
    assert other_item["responsible_user_id"] is None

    # Группировка возможна: есть хотя бы один «мой» и один «остальной».
    mine_ids = [it["id"] for it in items if it["responsible_user_id"] == str(admin_user.id)]
    rest_ids = [it["id"] for it in items if it["responsible_user_id"] is None]
    assert mine["id"] in mine_ids
    assert other["id"] in rest_ids


# ---------------------------------------------------------------------------
# «Мои» = ответственный ИЛИ участник команды (is_mine)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_is_mine_true_for_team_member_not_responsible(
    async_client: AsyncClient,
    auth_headers: dict,
    admin_user,
    regular_user,
    default_client: str,
):
    """«Мои» шире, чем ответственный: вакансия с team=[regular, admin] → ответственный
    = regular_user (team[0]), а admin — участник команды, но НЕ ответственный.
    is_mine для admin должен быть True (он в команде) И в списке, И в сайдбаре.

    Дискриминирующе: если бы is_mine считался только по responsible_user_id, для admin
    он был бы False (ответственный — regular_user) — и командная вакансия не попала бы
    в «Мои». Именно эту жалобу фикс и закрывает.
    """
    vac = await _create_vacancy(
        async_client, auth_headers, name="Командная вакансия",
        client_id=default_client, team=[str(regular_user.id), str(admin_user.id)],
    )

    # Список (разводящая)
    resp = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    item = _find(resp.json()["items"], vac["id"])
    assert item is not None
    assert item["responsible_user_id"] == str(regular_user.id)  # ответственный — НЕ admin
    assert item["is_mine"] is True                              # но admin в команде → «моя»

    # Сайдбар
    sb = await async_client.get("/api/v1/vacancies/sidebar", headers=auth_headers)
    assert sb.status_code == 200, sb.text
    sb_item = _find(sb.json()["items"], vac["id"])
    assert sb_item is not None
    assert sb_item["responsible_user_id"] == str(regular_user.id)
    assert sb_item["is_mine"] is True


@pytest.mark.asyncio
async def test_is_mine_false_when_not_responsible_and_not_in_team(
    async_client: AsyncClient,
    auth_headers: dict,
    admin_user,
    regular_user,
    default_client: str,
):
    """Вакансия, где admin ни ответственный, ни в команде → is_mine=False (в «Остальных»)."""
    vac = await _create_vacancy(
        async_client, auth_headers, name="Чужая вакансия",
        client_id=default_client, team=[str(regular_user.id)],
    )
    resp = await async_client.get("/api/v1/vacancies", headers=auth_headers)
    item = _find(resp.json()["items"], vac["id"])
    assert item is not None
    assert item["is_mine"] is False

    sb = await async_client.get("/api/v1/vacancies/sidebar", headers=auth_headers)
    sb_item = _find(sb.json()["items"], vac["id"])
    assert sb_item is not None
    assert sb_item["is_mine"] is False
