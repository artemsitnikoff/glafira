"""Тесты модуля «Заявки на подбор».

Фикстуры — реальные из conftest (db_session, admin_user, async_client). Роутовые тесты
идут через async_client (реальный HTTP-стек + RBAC-гарды роутера). Логика найма/автозакрытия
проверяется через РЕАЛЬНЫЙ move_application.

Главный блок — ИЗОЛЯЦИЯ роли hiring_manager (см. TestManagerIsolation): менеджер видит
ТОЛЬКО свои заявки и получает 403 на всех прочих data-роутах.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models import (
    User, Company, Client, Vacancy, Candidate, Application,
    AuditLog, HiringRequest, RequestSettings,
)


async def _login(client: AsyncClient, email: str, password: str = "Glafira2026!") -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def hm_user(db_session: AsyncSession, admin_user: User) -> User:
    """Нанимающий менеджер в компании admin_user."""
    u = User(
        company_id=admin_user.company_id,
        email="hiring.manager@example.com",
        password_hash=get_password_hash("Glafira2026!"),
        full_name="Марина Ковалёва",
        role="hiring_manager",
        position="Руководитель отдела продаж",
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def hm_headers(async_client: AsyncClient, hm_user: User) -> dict:
    return await _login(async_client, hm_user.email)


@pytest_asyncio.fixture
async def client_row(db_session: AsyncSession, admin_user: User) -> Client:
    c = Client(company_id=admin_user.company_id, name="ООО Заказчик")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


# ── Переходы ──────────────────────────────────────────────────────────────────
class TestTransitions:
    @pytest.mark.asyncio
    async def test_create_and_take_in_work(self, async_client, auth_headers):
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Менеджер по продажам", "description": "Нужен продажник B2B",
            "positions": 2, "author_name": "Пётр", "author_role": "РОП",
        })
        assert r.status_code == 201, r.text
        req = r.json()
        assert req["status"] == "new" and req["via"] == "manual" and req["num"] >= 1

        m = await async_client.patch(f"/api/v1/requests/{req['id']}/move",
                                     headers=auth_headers, json={"target": "work"})
        assert m.status_code == 200, m.text
        assert m.json()["status"] == "work"

    @pytest.mark.asyncio
    async def test_reject_requires_reason(self, async_client, auth_headers):
        r = await async_client.post("/api/v1/requests", headers=auth_headers,
                                    json={"title": "T", "description": "D"})
        rid = r.json()["id"]
        # Пробел проходит pydantic (min_length=1), но сервис .strip() → пусто → 400
        bad = await async_client.post(f"/api/v1/requests/{rid}/reject",
                                      headers=auth_headers, json={"reason": "   "})
        assert bad.status_code == 400, bad.text
        ok = await async_client.post(f"/api/v1/requests/{rid}/reject",
                                     headers=auth_headers, json={"reason": "Бюджет не согласован"})
        assert ok.status_code == 200
        assert ok.json()["status"] == "rejected"
        # Вернуть в работу
        back = await async_client.post(f"/api/v1/requests/{rid}/restore", headers=auth_headers)
        assert back.status_code == 200
        assert back.json()["status"] == "work"

    @pytest.mark.asyncio
    async def test_question_from_new_moves_to_work(self, async_client, auth_headers):
        r = await async_client.post("/api/v1/requests", headers=auth_headers,
                                    json={"title": "T", "description": "D"})
        rid = r.json()["id"]
        c = await async_client.post(f"/api/v1/requests/{rid}/comments",
                                    headers=auth_headers, json={"body": "Уточните BI-инструмент"})
        assert c.status_code == 200, c.text
        assert c.json()["status"] == "work"

    @pytest.mark.asyncio
    async def test_move_to_terminal_blocked(self, async_client, auth_headers):
        """Терминалы через общий /move запрещены — только своими путями (reject/close)."""
        r = await async_client.post("/api/v1/requests", headers=auth_headers,
                                    json={"title": "T", "description": "D"})
        rid = r.json()["id"]
        for target in ("rejected", "done"):
            m = await async_client.patch(f"/api/v1/requests/{rid}/move",
                                         headers=auth_headers, json={"target": target})
            assert m.status_code == 400, f"{target}: {m.text}"

    @pytest.mark.asyncio
    async def test_move_to_sourcing_without_vacancy_blocked(self, async_client, auth_headers):
        r = await async_client.post("/api/v1/requests", headers=auth_headers,
                                    json={"title": "T", "description": "D"})
        rid = r.json()["id"]
        m = await async_client.patch(f"/api/v1/requests/{rid}/move",
                                     headers=auth_headers, json={"target": "sourcing"})
        assert m.status_code == 409, m.text  # VACANCY_REQUIRED


# ── Создание вакансии из заявки (связь 1:1) ─────────────────────────────────
class TestVacancyFromRequest:
    @pytest.mark.asyncio
    async def test_create_vacancy_links_and_moves_to_sourcing(
        self, async_client, auth_headers, client_row
    ):
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Frontend-разработчик", "description": "React/TS senior", "positions": 2,
            "city": "Москва",
        })
        rid = r.json()["id"]
        # Создаём вакансию мастером с request_id
        v = await async_client.post("/api/v1/vacancies", headers=auth_headers, json={
            "name": "Frontend-разработчик", "client_id": str(client_row.id),
            "positions_count": 2, "request_id": rid,
        })
        assert v.status_code == 201, v.text
        vac = v.json()
        assert vac["request_id"] == rid
        assert vac["request_num"] is not None

        # Заявка → sourcing, связь проставлена
        got = await async_client.get(f"/api/v1/requests/{rid}", headers=auth_headers)
        assert got.status_code == 200
        assert got.json()["status"] == "sourcing"
        assert got.json()["vacancy_id"] == vac["id"]

        # Вторая вакансия на ту же заявку → конфликт (связь 1:1)
        v2 = await async_client.post("/api/v1/vacancies", headers=auth_headers, json={
            "name": "Дубль", "client_id": str(client_row.id), "request_id": rid,
        })
        assert v2.status_code == 409, v2.text


# ── Прогресс найма + автозакрытие (через реальный move_application) ──────────
class TestHiredProgressAutoclose:
    async def _setup(self, db_session, company_id, positions=2, autoclose=True):
        req = HiringRequest(company_id=company_id, num=900, title="T", description="D",
                            positions=positions, status="sourcing", via="manual")
        db_session.add(req)
        await db_session.flush()
        vac = Vacancy(company_id=company_id, name="V", status="active",
                      positions_count=positions, request_id=req.id)
        db_session.add(vac)
        await db_session.flush()
        req.vacancy_id = vac.id
        st = RequestSettings(company_id=company_id, autoclose_on=autoclose)
        db_session.add(st)
        apps = []
        for i in range(positions):
            cand = Candidate(company_id=company_id, last_name=f"К{i}", first_name="И", source="manual")
            db_session.add(cand)
            await db_session.flush()
            app = Application(company_id=company_id, candidate_id=cand.id,
                              vacancy_id=vac.id, stage="response")
            db_session.add(app)
            apps.append(app)
        await db_session.commit()
        return req, vac, apps

    @pytest.mark.asyncio
    async def test_hired_progress_and_autoclose(self, db_session, admin_user):
        from app.services.application import move_application
        from app.services.hiring_request import compute_hired
        from app.schemas.application import MoveRequest

        req, vac, apps = await self._setup(db_session, admin_user.company_id, positions=2)

        # 1-й нанят → прогресс 1/2, заявка ещё НЕ закрыта
        await move_application(db_session, apps[0].id, MoveRequest(to_stage="hired"),
                              admin_user.company_id, admin_user.id)
        await db_session.commit()
        assert await compute_hired(db_session, admin_user.company_id, vac.id) == 1
        await db_session.refresh(req)
        assert req.status == "sourcing"

        # 2-й нанят → 2/2 → автозакрытие
        await move_application(db_session, apps[1].id, MoveRequest(to_stage="hired"),
                              admin_user.company_id, admin_user.id)
        await db_session.commit()
        await db_session.refresh(req)
        assert req.status == "done"
        assert req.closed_note and "2 из 2" in req.closed_note

    @pytest.mark.asyncio
    async def test_autoclose_off_keeps_open(self, db_session, admin_user):
        from app.services.application import move_application
        from app.schemas.application import MoveRequest

        req, vac, apps = await self._setup(db_session, admin_user.company_id,
                                           positions=1, autoclose=False)
        await move_application(db_session, apps[0].id, MoveRequest(to_stage="hired"),
                              admin_user.company_id, admin_user.id)
        await db_session.commit()
        await db_session.refresh(req)
        assert req.status == "sourcing"  # не закрылась при autoclose_on=false

    @pytest.mark.asyncio
    async def test_delete_vacancy_keeps_request(self, db_session, admin_user):
        req, vac, apps = await self._setup(db_session, admin_user.company_id, positions=1)
        # В проде вакансия АРХИВИРУЕТСЯ, а не удаляется; hard-delete вакансии с откликами
        # невозможен (applications.vacancy_id NOT NULL, без ondelete). Убираем отклики,
        # затем проверяем SET NULL на связи заявка↔вакансия при удалении вакансии.
        for a in apps:
            await db_session.delete(a)
        await db_session.flush()
        await db_session.delete(vac)
        await db_session.commit()
        # Заявка жива, связь обнулена (ondelete SET NULL). ⚠️ SET NULL сработал на уровне
        # БД, но при expire_on_commit=False ORM-инстанс req в identity-map держит старый
        # vacancy_id — принудительно перечитываем из БД (refresh), иначе увидим stale.
        survivor = await db_session.get(HiringRequest, req.id)
        assert survivor is not None
        await db_session.refresh(survivor)
        assert survivor.vacancy_id is None


# ── Воронка заявок ────────────────────────────────────────────────────────────
class TestFunnel:
    @pytest.mark.asyncio
    async def test_custom_stage_and_protected(self, async_client, auth_headers):
        # добавить кастомный этап
        add = await async_client.post("/api/v1/requests/funnel-stages",
                                      headers=auth_headers, json={"label": "На согласовании"})
        assert add.status_code == 200, add.text
        flow = add.json()
        keys = [s["key"] for s in flow]
        assert "new" in keys and "sourcing" in keys
        assert any(s["custom"] for s in flow)
        # кастомный этап вставлен МЕЖДУ work и sourcing
        assert keys.index("work") < keys.index([s["key"] for s in flow if s["custom"]][0]) < keys.index("sourcing")

        # изменить фиксированный этап → 400
        bad = await async_client.patch("/api/v1/requests/funnel-stages/new",
                                       headers=auth_headers, json={"label": "Хм"})
        assert bad.status_code == 400
        # удалить фиксированный → 400
        badd = await async_client.delete("/api/v1/requests/funnel-stages/sourcing", headers=auth_headers)
        assert badd.status_code == 400


# ── ГЛАВНОЕ: изоляция роли hiring_manager ────────────────────────────────────
class TestManagerIsolation:
    @pytest.mark.asyncio
    async def test_manager_sees_only_own_requests(self, async_client, auth_headers, hm_headers, hm_user):
        # менеджер подаёт свою (via=cabinet, author=он)
        mine = await async_client.post("/api/v1/requests", headers=hm_headers,
                                       json={"title": "Моя", "description": "D"})
        assert mine.status_code == 201, mine.text
        assert mine.json()["via"] == "cabinet"
        # рекрутер создаёт чужую
        other = await async_client.post("/api/v1/requests", headers=auth_headers,
                                        json={"title": "Чужая", "description": "D"})
        other_id = other.json()["id"]

        # список менеджера — только своя
        lst = await async_client.get("/api/v1/requests", headers=hm_headers)
        assert lst.status_code == 200
        titles = [i["title"] for i in lst.json()["items"]]
        assert "Моя" in titles and "Чужая" not in titles

        # чужая по прямому id → 404 (как будто не существует)
        get_other = await async_client.get(f"/api/v1/requests/{other_id}", headers=hm_headers)
        assert get_other.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_cannot_manage_own_request(self, async_client, hm_headers):
        mine = await async_client.post("/api/v1/requests", headers=hm_headers,
                                       json={"title": "Моя", "description": "D"})
        rid = mine.json()["id"]
        # менеджер НЕ может двигать/отклонять
        m = await async_client.patch(f"/api/v1/requests/{rid}/move",
                                     headers=hm_headers, json={"target": "work"})
        assert m.status_code == 403, m.text
        rj = await async_client.post(f"/api/v1/requests/{rid}/reject",
                                     headers=hm_headers, json={"reason": "x"})
        assert rj.status_code == 403
        # но может писать в тред своей заявки
        c = await async_client.post(f"/api/v1/requests/{rid}/comments",
                                    headers=hm_headers, json={"body": "вопрос"})
        assert c.status_code == 200
        assert c.json()["comments"][-1]["side"] == "manager"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", [
        "/api/v1/candidates",
        "/api/v1/vacancies",
        "/api/v1/vacancies/sidebar",
        "/api/v1/analytics/overview",
        "/api/v1/settings/reject-reasons",
        "/api/v1/pulse/employees",
        "/api/v1/smart/access",
        "/api/v1/home/events",
        "/api/v1/message-templates",
    ])
    async def test_manager_forbidden_everywhere_else(self, async_client, hm_headers, path):
        resp = await async_client.get(path, headers=hm_headers)
        assert resp.status_code == 403, f"{path} → {resp.status_code} (ожидался 403): {resp.text}"

    @pytest.mark.asyncio
    async def test_assistant_manager_also_author_scoped(self, async_client, auth_headers, manager_user):
        """Роль 'manager' (ассистент) тоже author-scoped в заявках: не видит/не двигает чужие
        (закрытие least-privilege gap — фикс-форвард по ревью)."""
        # рекрутер создаёт заявку
        other = await async_client.post("/api/v1/requests", headers=auth_headers,
                                        json={"title": "Чужая", "description": "D"})
        other_id = other.json()["id"]
        mgr_headers = await _login(async_client, manager_user.email)
        # ассистент-manager не видит чужую в списке и по id
        lst = await async_client.get("/api/v1/requests", headers=mgr_headers)
        assert lst.status_code == 200
        assert "Чужая" not in [i["title"] for i in lst.json()["items"]]
        direct = await async_client.get(f"/api/v1/requests/{other_id}", headers=mgr_headers)
        assert direct.status_code == 404
        # и не может двигать
        mv = await async_client.patch(f"/api/v1/requests/{other_id}/move",
                                      headers=mgr_headers, json={"target": "work"})
        assert mv.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_manager_can_read_own_me(self, async_client, hm_headers):
        # /auth/me не должен быть закрыт — иначе менеджер не залогинится
        me = await async_client.get("/api/v1/auth/me", headers=hm_headers)
        assert me.status_code == 200
        assert me.json()["role"] == "hiring_manager"


# ── Мультитенантность ─────────────────────────────────────────────────────────
class TestCompanyIsolation:
    @pytest.mark.asyncio
    async def test_request_not_visible_across_companies(
        self, async_client, db_session, auth_headers, admin_user
    ):
        # Заявка в компании A
        a = await async_client.post("/api/v1/requests", headers=auth_headers,
                                    json={"title": "A-req", "description": "D"})
        a_id = a.json()["id"]

        # Компания B + её админ
        comp_b = Company(id=uuid.uuid4(), name="Company B")
        db_session.add(comp_b)
        await db_session.flush()
        admin_b = User(company_id=comp_b.id, email="b.admin@example.com",
                       password_hash=get_password_hash("Glafira2026!"),
                       full_name="B Admin", role="admin", is_active=True)
        db_session.add(admin_b)
        await db_session.commit()
        b_headers = await _login(async_client, admin_b.email)

        # B не видит заявку A ни в списке, ни по id
        lst = await async_client.get("/api/v1/requests", headers=b_headers)
        assert lst.status_code == 200
        assert a_id not in [i["id"] for i in lst.json()["items"]]
        direct = await async_client.get(f"/api/v1/requests/{a_id}", headers=b_headers)
        assert direct.status_code == 404


# ── Публичная форма ───────────────────────────────────────────────────────────
class TestPublicForm:
    @pytest.mark.asyncio
    async def test_submit_creates_form_request(self, async_client, auth_headers, admin_user, db_session):
        # admin создаёт ссылку и ВКЛЮЧАЕТ приём (ротация сама приём не включает)
        rot = await async_client.post("/api/v1/requests/form-link/rotate", headers=auth_headers)
        assert rot.status_code == 200, rot.text
        url = rot.json()["url"]
        token = url.rsplit("/", 1)[-1]
        en = await async_client.patch("/api/v1/requests/settings", headers=auth_headers,
                                      json={"form_enabled": True})
        assert en.status_code == 200, en.text

        # публичный GET info
        info = await async_client.get(f"/api/v1/public/request-form/{token}")
        assert info.status_code == 200
        assert info.json()["company_name"] == "Test Company"

        # публичный сабмит
        sub = await async_client.post(f"/api/v1/public/request-form/{token}", json={
            "title": "С формы", "description": "Нужен оператор", "author_name": "Дмитрий",
            "author_contact": "@ershov",
        })
        assert sub.status_code == 200, sub.text
        assert sub.json()["ok"] is True and sub.json()["num"] is not None

        # заявка появилась via=form у рекрутера
        lst = await async_client.get("/api/v1/requests", headers=auth_headers)
        forms = [i for i in lst.json()["items"] if i["via"] == "form"]
        assert forms and forms[0]["title"] == "С формы"

    @pytest.mark.asyncio
    async def test_wrong_and_rotated_token_404(self, async_client, auth_headers):
        rot = await async_client.post("/api/v1/requests/form-link/rotate", headers=auth_headers)
        old_token = rot.json()["url"].rsplit("/", 1)[-1]
        # неверный токен
        bad = await async_client.get("/api/v1/public/request-form/nope-nope-nope")
        assert bad.status_code == 404
        # ротация инвалидирует старую ссылку
        await async_client.post("/api/v1/requests/form-link/rotate", headers=auth_headers)
        dead = await async_client.get(f"/api/v1/public/request-form/{old_token}")
        assert dead.status_code == 404

    @pytest.mark.asyncio
    async def test_honeypot_silently_drops(self, async_client, auth_headers):
        rot = await async_client.post("/api/v1/requests/form-link/rotate", headers=auth_headers)
        token = rot.json()["url"].rsplit("/", 1)[-1]
        await async_client.patch("/api/v1/requests/settings", headers=auth_headers,
                                 json={"form_enabled": True})  # ротация приём не включает
        # honeypot заполнен → ok, но заявка НЕ создана
        sub = await async_client.post(f"/api/v1/public/request-form/{token}", json={
            "title": "Спам", "description": "бот", "website": "http://spam.example",
        })
        assert sub.status_code == 200
        assert sub.json()["num"] is None
        lst = await async_client.get("/api/v1/requests", headers=auth_headers)
        assert "Спам" not in [i["title"] for i in lst.json()["items"]]


# ── Ссылка формы: СВОЯ у каждого инстанса и существует СРАЗУ ─────────────────
class TestFormLinkPerInstance:
    @pytest.mark.asyncio
    async def test_form_link_exists_even_when_disabled(self, async_client, auth_headers):
        """GET /form-link ВСЕГДА отдаёт непустой url: ensure_form_token создаёт токен при
        первом обращении, НЕ включая приём. enabled=False, пока форма не активирована."""
        r = await async_client.get("/api/v1/requests/form-link", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is False              # приём по умолчанию выключен
        assert body["url"] and "/apply/" in body["url"]  # но ссылка на инстанс уже есть

    @pytest.mark.asyncio
    async def test_form_link_available_to_recruiter(self, async_client, regular_user):
        """Ссылка доступна рекрутёру (require_recruiter_or_admin), не только админу."""
        rec_headers = await _login(async_client, regular_user.email)
        r = await async_client.get("/api/v1/requests/form-link", headers=rec_headers)
        assert r.status_code == 200, r.text
        assert r.json()["url"] and "/apply/" in r.json()["url"]

    @pytest.mark.asyncio
    async def test_rotate_does_not_enable_form(self, async_client, auth_headers):
        """Ротация НЕ включает приём молча (иначе UI-тумблер «выключено» врал бы — §0).
        Приёмом управляет только тумблер form_enabled."""
        # приём выключен (дефолт) → ротация меняет url, но enabled остаётся False
        before = await async_client.get("/api/v1/requests/form-link", headers=auth_headers)
        assert before.json()["enabled"] is False
        rot = await async_client.post("/api/v1/requests/form-link/rotate", headers=auth_headers)
        assert rot.status_code == 200, rot.text
        assert rot.json()["enabled"] is False           # приём НЕ включился сам
        assert rot.json()["url"] != before.json()["url"]  # но ссылка новая

    @pytest.mark.asyncio
    async def test_form_link_stable_across_calls(self, async_client, auth_headers):
        """Повторный GET без ротации отдаёт ТУ ЖЕ ссылку (токен не пересоздаётся)."""
        first = await async_client.get("/api/v1/requests/form-link", headers=auth_headers)
        second = await async_client.get("/api/v1/requests/form-link", headers=auth_headers)
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["url"] == second.json()["url"]

    @pytest.mark.asyncio
    async def test_form_token_differs_per_company(self, async_client, db_session, auth_headers):
        """У каждой компании — СВОЯ ссылка: токен A ≠ токен B (изоляция инстансов)."""
        a = await async_client.get("/api/v1/requests/form-link", headers=auth_headers)
        assert a.status_code == 200, a.text
        token_a = a.json()["url"].rsplit("/", 1)[-1]

        # Компания B + её админ (образец TestCompanyIsolation)
        comp_b = Company(id=uuid.uuid4(), name="Company B (form-link)")
        db_session.add(comp_b)
        await db_session.flush()
        admin_b = User(company_id=comp_b.id, email="b.formlink.admin@example.com",
                       password_hash=get_password_hash("Glafira2026!"),
                       full_name="B Admin", role="admin", is_active=True)
        db_session.add(admin_b)
        await db_session.commit()
        b_headers = await _login(async_client, admin_b.email)

        b = await async_client.get("/api/v1/requests/form-link", headers=b_headers)
        assert b.status_code == 200, b.text
        token_b = b.json()["url"].rsplit("/", 1)[-1]

        assert token_a and token_b and token_a != token_b


# ── Заказчик заявки — выбор из пользователей Глафиры (v1.1.4) ────────────────
class TestAuthorUserLink:
    """POST /requests с author_user_id: привязка заявки к сотруднику компании.

    Ключевое — ИЗОЛЯЦИЯ (§2.3): привязать можно ТОЛЬКО активного юзера СВОЕЙ компании,
    иначе рекрутер арендатора A подсунул бы заявку в «Мои заявки» юзеру арендатора B.
    """

    @pytest.mark.asyncio
    async def test_link_own_company_user_overrides_text(
        self, async_client, auth_headers, hm_user
    ):
        """ФИО/должность берутся ИЗ ЗАПИСИ юзера, присланный текст игнорируется."""
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Аналитик", "description": "Нужен аналитик в отдел продаж",
            "author_user_id": str(hm_user.id),
            # заведомо неверный текст — сервер обязан его проигнорировать
            "author_name": "ПОДДЕЛКА", "author_role": "ПОДДЕЛКА",
            "author_contact": "+7 999 000-00-00",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["author_user_id"] == str(hm_user.id)
        assert body["author_name"] == hm_user.full_name
        assert body["author_role"] == hm_user.position
        # Вносил всё равно рекрутер → via остаётся manual, не подменяется на cabinet
        assert body["via"] == "manual"
        # Контакт из формы сохраняется как есть
        assert body["author_contact"] == "+7 999 000-00-00"

    @pytest.mark.asyncio
    async def test_linked_user_sees_request_in_his_list(
        self, async_client, auth_headers, hm_user, hm_headers
    ):
        """Смысл фичи: привязанный заказчик видит заявку в «Моих заявках»."""
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Логист", "description": "Нужен логист",
            "author_user_id": str(hm_user.id),
        })
        assert r.status_code == 201, r.text
        rid = r.json()["id"]

        mine = await async_client.get("/api/v1/requests", headers=hm_headers)
        assert mine.status_code == 200, mine.text
        assert rid in [i["id"] for i in mine.json()["items"]]

    @pytest.mark.asyncio
    async def test_foreign_company_user_rejected(
        self, async_client, db_session, auth_headers
    ):
        """⚠️ Юзер ДРУГОГО арендатора → fail-closed 400, заявка НЕ создана."""
        comp_b = Company(id=uuid.uuid4(), name="Company B (author-link)")
        db_session.add(comp_b)
        await db_session.flush()
        user_b = User(
            company_id=comp_b.id, email="b.author.link@example.com",
            password_hash=get_password_hash("Glafira2026!"),
            full_name="Чужой Сотрудник", role="hiring_manager",
            position="Директор B", is_active=True,
        )
        db_session.add(user_b)
        await db_session.commit()

        before = await async_client.get("/api/v1/requests", headers=auth_headers)
        total_before = before.json()["total"]

        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Утечка", "description": "Попытка привязать чужого юзера",
            "author_user_id": str(user_b.id),
        })
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"

        after = await async_client.get("/api/v1/requests", headers=auth_headers)
        assert after.json()["total"] == total_before   # заявка не создалась

    @pytest.mark.asyncio
    async def test_inactive_user_rejected(self, async_client, db_session, admin_user, auth_headers):
        """Заблокированный сотрудник своей компании → тоже отказ."""
        dead = User(
            company_id=admin_user.company_id, email="fired.manager@example.com",
            password_hash=get_password_hash("Glafira2026!"),
            full_name="Уволенный Менеджер", role="hiring_manager",
            position="Экс-РОП", is_active=False,
        )
        db_session.add(dead)
        await db_session.commit()

        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Заявка", "description": "Описание",
            "author_user_id": str(dead.id),
        })
        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_unknown_user_id_rejected(self, async_client, auth_headers):
        """Несуществующий id → отказ, а не молчаливый None."""
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Заявка", "description": "Описание",
            "author_user_id": str(uuid.uuid4()),
        })
        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_without_author_user_id_keeps_text_behaviour(self, async_client, auth_headers):
        """Обратная совместимость: без author_user_id — прежнее поведение с текстом."""
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Кладовщик", "description": "Нужен кладовщик",
            "author_name": "Пётр Иванов", "author_role": "Начальник склада",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["author_user_id"] is None
        assert body["author_name"] == "Пётр Иванов"
        assert body["author_role"] == "Начальник склада"
        assert body["via"] == "manual"

    @pytest.mark.asyncio
    async def test_link_recorded_in_audit_log(
        self, async_client, db_session, auth_headers, admin_user, hm_user
    ):
        """§2.2: привязка к сотруднику — изменяющее решение о ВИДИМОСТИ заявки → audit_log.

        Читаем ИМЕННО changes['after']['author_user_id'] той записи, что создал этот POST
        (audit хранит до/после в JSONB-колонке `changes`, атрибута .after нет).
        Тест дискриминирующий: он завязан на конкретный ключ в `after`, а не на факт
        существования записи — уберут из create_request строки, кладущие author_user_id
        в after, и assert упадёт (парный негативный тест ниже доказывает, что ключ там
        не «всегда есть»).
        """
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Технолог", "description": "Нужен технолог на производство",
            "author_user_id": str(hm_user.id),
        })
        assert r.status_code == 201, r.text
        rid = uuid.UUID(r.json()["id"])

        rec = (await db_session.execute(
            select(AuditLog).where(
                AuditLog.company_id == admin_user.company_id,
                AuditLog.entity_type == "request",
                AuditLog.entity_id == rid,
                AuditLog.action == "create",
            )
        )).scalar_one()

        assert rec.changes is not None
        after = rec.changes["after"]
        assert after.get("author_user_id") == str(hm_user.id), (
            f"привязка заказчика не попала в audit_log: after={after}"
        )
        # Актор — тот рекрутер, который привязал (не привязанный менеджер), и своя компания.
        assert rec.actor_type == "human"
        assert rec.actor_user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_audit_without_link_has_no_author_user_id(
        self, async_client, db_session, auth_headers, admin_user
    ):
        """Парный негативный: без привязки ключа в `after` НЕТ (иначе прошлый тест был бы
        вечнозелёным — проходил бы и на константе «ключ всегда есть»)."""
        r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
            "title": "Кладовщик", "description": "Нужен кладовщик",
            "author_name": "Пётр Иванов", "author_role": "Начальник склада",
        })
        assert r.status_code == 201, r.text
        rid = uuid.UUID(r.json()["id"])

        rec = (await db_session.execute(
            select(AuditLog).where(
                AuditLog.company_id == admin_user.company_id,
                AuditLog.entity_type == "request",
                AuditLog.entity_id == rid,
                AuditLog.action == "create",
            )
        )).scalar_one()

        assert rec.changes["after"]["status"] == "new"     # запись создания всё же есть
        assert "author_user_id" not in rec.changes["after"]

    @pytest.mark.asyncio
    async def test_cabinet_ignores_author_user_id(
        self, async_client, hm_headers, hm_user, admin_user
    ):
        """via=cabinet: автор — сам подающий; подсунутый чужой id не действует."""
        r = await async_client.post("/api/v1/requests", headers=hm_headers, json={
            "title": "Своя заявка", "description": "Подаю от себя",
            "author_user_id": str(admin_user.id),
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["via"] == "cabinet"
        assert body["author_user_id"] == str(hm_user.id)
        assert body["author_name"] == hm_user.full_name


# ── Уведомление заказчику о смене этапа (покрытие ВСЕХ переходов) ────────────
@pytest_asyncio.fixture
async def linked_request_id(async_client: AsyncClient, auth_headers: dict, hm_user: User) -> str:
    """Заявка со статусом 'new', привязанная к сотруднику-заказчику (есть кому писать)."""
    r = await async_client.post("/api/v1/requests", headers=auth_headers, json={
        "title": "Технолог", "description": "Нужен технолог на производство",
        "positions": 1, "author_user_id": str(hm_user.id),
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestManagerNotifications:
    """Письмо заказчику должно уходить на ВСЕХ сменах статуса его заявки.

    Тумблер в настройках обещает безусловно («…письмо на email при изменении статуса
    его заявки»), а вызовов _notify_manager_stage_change было четыре — переходы
    sourcing (создание вакансии), restore (возврат из отказа) и автоперевод по вопросу
    оставались немыми.

    ⚠️ ТОЧКА ПАТЧА. hiring_request.py импортирует send_email ЛОКАЛЬНО, в теле
    _notify_manager_stage_change (`from .integrations.smtp.service import send_email`),
    поэтому модульного имени `app.services.hiring_request.send_email` НЕ существует —
    патч по нему ничего бы не перехватил. Имя резолвится в момент вызова как атрибут
    модуля smtp.service, его и патчим (это и есть «место импорта» для отложенного import).
    """

    @staticmethod
    def _patch_send():
        return patch("app.services.integrations.smtp.service.send_email",
                     new_callable=AsyncMock)

    @pytest.mark.asyncio
    async def test_vacancy_created_notifies_about_sourcing(
        self, async_client, auth_headers, client_row, hm_user, linked_request_id
    ):
        """Главный пропуск: подбор реально начался, а заказчик об этом не узнавал."""
        with self._patch_send() as mock_send:
            v = await async_client.post("/api/v1/vacancies", headers=auth_headers, json={
                "name": "Технолог", "client_id": str(client_row.id),
                "positions_count": 1, "request_id": linked_request_id,
            })
        assert v.status_code == 201, v.text

        got = await async_client.get(f"/api/v1/requests/{linked_request_id}", headers=auth_headers)
        assert got.json()["status"] == "sourcing"   # переход реально произошёл

        mock_send.assert_awaited_once()
        kwargs = mock_send.await_args.kwargs
        assert kwargs["to"] == hm_user.email
        assert "В подборе" in kwargs["subject"]     # ярлык из справочника этапов
        # Брендированный шаблон, а не голый plaintext (жёсткое правило проекта по письмам)
        assert kwargs.get("body_html") and "<" in kwargs["body_html"]

    @pytest.mark.asyncio
    async def test_sourcing_notification_respects_toggle_off(
        self, async_client, auth_headers, client_row, linked_request_id
    ):
        """Новый вызов уважает тумблер: notify_manager_on_stage=false → письма нет."""
        off = await async_client.patch("/api/v1/requests/settings", headers=auth_headers,
                                       json={"notify_manager_on_stage": False})
        assert off.status_code == 200, off.text
        with self._patch_send() as mock_send:
            v = await async_client.post("/api/v1/vacancies", headers=auth_headers, json={
                "name": "Технолог", "client_id": str(client_row.id),
                "positions_count": 1, "request_id": linked_request_id,
            })
        assert v.status_code == 201, v.text
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_restore_notifies_about_work(
        self, async_client, auth_headers, hm_user, linked_request_id
    ):
        """Возврат отклонённой заявки в работу: заказчик уже получил «Отклонена»."""
        rj = await async_client.post(f"/api/v1/requests/{linked_request_id}/reject",
                                     headers=auth_headers, json={"reason": "Бюджет заморожен"})
        assert rj.status_code == 200, rj.text
        with self._patch_send() as mock_send:
            back = await async_client.post(f"/api/v1/requests/{linked_request_id}/restore",
                                           headers=auth_headers)
        assert back.status_code == 200, back.text
        assert back.json()["status"] == "work"

        mock_send.assert_awaited_once()
        kwargs = mock_send.await_args.kwargs
        assert kwargs["to"] == hm_user.email
        assert "В работе" in kwargs["subject"]

    @pytest.mark.asyncio
    async def test_question_moves_to_work_notifies(
        self, async_client, auth_headers, hm_user, linked_request_id
    ):
        """Автоперевод «Новая»→«В работе» по первому вопросу рекрутёра."""
        with self._patch_send() as mock_send:
            c = await async_client.post(f"/api/v1/requests/{linked_request_id}/comments",
                                        headers=auth_headers, json={"body": "Уточните грейд"})
        assert c.status_code == 200, c.text
        assert c.json()["status"] == "work"

        mock_send.assert_awaited_once()
        kwargs = mock_send.await_args.kwargs
        assert kwargs["to"] == hm_user.email
        assert "В работе" in kwargs["subject"]

    @pytest.mark.asyncio
    async def test_comment_on_already_work_request_sends_nothing(
        self, async_client, auth_headers, linked_request_id
    ):
        """Без смены статуса письма нет: второй вопрос по заявке «В работе» — молча."""
        first = await async_client.post(f"/api/v1/requests/{linked_request_id}/comments",
                                        headers=auth_headers, json={"body": "Первый вопрос"})
        assert first.json()["status"] == "work"
        with self._patch_send() as mock_send:
            second = await async_client.post(f"/api/v1/requests/{linked_request_id}/comments",
                                             headers=auth_headers, json={"body": "Второй вопрос"})
        assert second.status_code == 200, second.text
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_second_email_when_moving_to_current_stage(
        self, async_client, auth_headers, client_row, linked_request_id
    ):
        """Задвоения нет: после привязки вакансии заявка уже 'sourcing', и повторный
        /move sourcing уходит в ранний return move_request (target == req.status)."""
        v = await async_client.post("/api/v1/vacancies", headers=auth_headers, json={
            "name": "Технолог", "client_id": str(client_row.id),
            "positions_count": 1, "request_id": linked_request_id,
        })
        assert v.status_code == 201, v.text
        with self._patch_send() as mock_send:
            m = await async_client.patch(f"/api/v1/requests/{linked_request_id}/move",
                                         headers=auth_headers, json={"target": "sourcing"})
        assert m.status_code == 200, m.text
        assert m.json()["status"] == "sourcing"
        mock_send.assert_not_awaited()
