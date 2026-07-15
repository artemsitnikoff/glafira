"""Тесты «Глафира называет компанию вакансии» (заказчик → фолбэк на арендатора).

Покрывает:
- хелпер resolve_company_display_name (клиент / NULL-фолбэк / изоляция company_id);
- подстановку компании в сообщение уточняющих вопросов (auto_qa);
- письмо-приглашение на интервью (вакансия И компания в теме/тексте/HTML);
- каркас писем (шапка/подпись) с компанией и без неё (служебные письма);
- обязательность заказчика в POST /vacancies и PATCH /vacancies/{id};
- hh-импорт вакансий БЕЗ клиента продолжает работать (валидация только в роуте).

Фикстуры — реальные из conftest (db_session, admin_user, auth_headers, other_company).
Моки — по МЕСТУ ИМПОРТА (app.services.glafira.interview_schedule.send_email и т.п.).
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Application, Candidate, Client, Company, Integration, InterviewLink,
    User, Vacancy, VacancyStage, VacancyTeam,
)
from app.services.company_display import resolve_company_display_name
from app.services.glafira.auto_qa import _compose_questions_message
from app.services.integrations.smtp.templates import render_simple_email, render_credentials_email


# ── helpers ──────────────────────────────────────────────────────────────────

async def _make_client(db: AsyncSession, company_id, name: str) -> Client:
    cl = Client(company_id=company_id, name=name)
    db.add(cl)
    await db.flush()
    return cl


async def _make_vacancy(db: AsyncSession, company_id, *, client_id=None, name="Python-разработчик") -> Vacancy:
    vac = Vacancy(company_id=company_id, name=name, client_id=client_id, status="active")
    db.add(vac)
    await db.flush()
    return vac


# ── A. Хелпер ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_returns_client_name_when_vacancy_has_client(
    db_session: AsyncSession, admin_user: User
):
    """У вакансии есть заказчик → его название (а не арендатора)."""
    cid = admin_user.company_id
    client = await _make_client(db_session, cid, "ООО Диджитал Клаудс")
    vacancy = await _make_vacancy(db_session, cid, client_id=client.id)

    name = await resolve_company_display_name(db_session, cid, vacancy)
    assert name == "ООО Диджитал Клаудс"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_tenant_when_client_is_null(
    db_session: AsyncSession, admin_user: User
):
    """client_id = NULL → название компании-арендатора (Настройки→Общие). Не пусто."""
    cid = admin_user.company_id
    vacancy = await _make_vacancy(db_session, cid, client_id=None)

    name = await resolve_company_display_name(db_session, cid, vacancy)
    assert name == "Test Company"  # имя компании из фикстуры admin_user


@pytest.mark.asyncio
async def test_resolve_falls_back_to_tenant_when_no_vacancy(
    db_session: AsyncSession, admin_user: User
):
    """vacancy=None (служебный/общий контекст) → компания-арендатор."""
    name = await resolve_company_display_name(db_session, admin_user.company_id, None)
    assert name == "Test Company"


@pytest.mark.asyncio
async def test_resolve_does_not_leak_foreign_client(
    db_session: AsyncSession, admin_user: User, other_company: Company
):
    """Клиент ЧУЖОЙ компании не резолвится (company-scoped) → фолбэк на арендатора.

    Защищает мультитенантность: имя клиента другого арендатора не должно утечь
    в текст, который Глафира пишет кандидату.
    """
    cid = admin_user.company_id
    foreign_client = await _make_client(db_session, other_company.id, "Чужой Заказчик")
    # Вакансия НАШЕЙ компании, но client_id указывает на чужого клиента.
    vacancy = await _make_vacancy(db_session, cid, client_id=foreign_client.id)

    name = await resolve_company_display_name(db_session, cid, vacancy)
    assert name != "Чужой Заказчик"
    assert name == "Test Company"


@pytest.mark.asyncio
async def test_resolve_never_touches_lazy_client_relationship(
    db_session: AsyncSession, admin_user: User
):
    """Хелпер не обращается к vacancy.client (lazy=select → MissingGreenlet).

    Подкладываем объект, у которого доступ к .client взрывается: хелпер обязан
    читать только client_id (обычная колонка).
    """
    cid = admin_user.company_id
    client = await _make_client(db_session, cid, "ООО Заказчик")

    class _VacancyStub:
        client_id = client.id

        @property
        def client(self):  # pragma: no cover — не должно вызываться
            raise AssertionError("Хелпер обратился к vacancy.client — это MissingGreenlet в проде")

    name = await resolve_company_display_name(db_session, cid, _VacancyStub())
    assert name == "ООО Заказчик"


# ── B. Каркас писем ──────────────────────────────────────────────────────────

def test_email_shell_with_company_in_header_and_signature():
    html = render_simple_email("Здравствуйте!", "<p>тело</p>", company_name="ООО Диджитал Клаудс")
    assert "· ООО Диджитал Клаудс" in html
    assert "Глафира — подбор персонала «ООО Диджитал Клаудс»" in html
    assert "Команда Глафира Рекрутёр" not in html


def test_email_shell_without_company_stays_branded():
    """Служебные письма (компания не передана) — прежний обезличенный бренд."""
    html = render_simple_email("Тест", "<p>тело</p>")
    assert "&nbsp;Рекрутёр" in html
    assert "Команда Глафира Рекрутёр" in html


def test_credentials_email_has_no_customer_company():
    """Письмо «Доступ к аккаунту» — служебное, компанию-заказчика НЕ получает."""
    html = render_credentials_email("Иван Иванов", "ivan@example.com", "secret")
    assert "Команда Глафира Рекрутёр" in html
    assert "подбор персонала" not in html


def test_company_name_is_html_escaped_in_email():
    """Название компании — данные из БД, в HTML идёт экранированным."""
    html = render_simple_email("H", "<p>b</p>", company_name='ООО "Рога" <script>alert(1)</script>')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── C. auto_qa — знакомство с компанией ──────────────────────────────────────

def test_auto_qa_message_names_company_and_vacancy():
    candidate = Candidate(first_name="Иван", last_name="Петров", middle_name=None)
    vacancy = Vacancy(name="Python-разработчик")
    body = _compose_questions_message(
        candidate, vacancy, ["Какой у вас опыт с Django?"], "ООО Диджитал Клаудс"
    )
    assert "Меня зовут Глафира, я ассистент по подбору в компании «ООО Диджитал Клаудс»." in body
    assert "«Python-разработчик»" in body
    assert "Какой у вас опыт с Django?" in body


def test_auto_qa_message_degrades_without_company():
    """Пустая компания → без «дырки» в кавычках (обезличенное знакомство)."""
    candidate = Candidate(first_name="Иван", last_name="Петров", middle_name=None)
    vacancy = Vacancy(name="Python-разработчик")
    body = _compose_questions_message(candidate, vacancy, ["Вопрос?"], "")
    assert "Меня зовут Глафира, я ассистент по подбору." in body
    assert "в компании «»" not in body


# ── D. Письмо-приглашение на интервью (П.5) ──────────────────────────────────

@pytest.mark.asyncio
async def test_interview_invite_email_names_vacancy_and_company(
    db_session: AsyncSession, admin_user: User
):
    """Письмо «выберите время» содержит И вакансию, И компанию — в теме, тексте и HTML."""
    from app.services.glafira import interview_schedule

    cid = admin_user.company_id
    admin_user.b24_user_id = 42
    client = await _make_client(db_session, cid, "ООО Диджитал Клаудс")
    vacancy = await _make_vacancy(db_session, cid, client_id=client.id)
    vacancy.auto_interview = True
    vacancy.auto_interview_stage = "interview"
    db_session.add(VacancyTeam(
        company_id=cid, vacancy_id=vacancy.id, user_id=admin_user.id, is_responsible=True,
    ))
    candidate = Candidate(
        company_id=cid, first_name="Иван", last_name="Петров",
        email="ivan@example.com", source="hh",
    )
    db_session.add(candidate)
    await db_session.flush()
    db_session.add(Application(
        company_id=cid, candidate_id=candidate.id, vacancy_id=vacancy.id, stage="interview",
    ))
    db_session.add(Integration(
        company_id=cid, provider="bitrix24", config={"webhook_url": "enc"},
    ))
    await db_session.flush()

    with patch.object(interview_schedule, "send_email", new=AsyncMock()) as mock_send:
        stats = await interview_schedule.send_interview_links(db_session, cid)

    assert stats["sent"] == 1, stats
    mock_send.assert_awaited_once()
    kwargs = mock_send.await_args.kwargs

    assert "Python-разработчик" in kwargs["subject"]
    assert "ООО Диджитал Клаудс" in kwargs["subject"]
    # Плоский фолбэк
    assert "«ООО Диджитал Клаудс»" in kwargs["body_text"]
    assert "«Python-разработчик»" in kwargs["body_text"]
    # Брендированный HTML: компания и в теле, и в шапке/подписи каркаса
    assert "ООО Диджитал Клаудс" in kwargs["body_html"]
    assert "Глафира — подбор персонала «ООО Диджитал Клаудс»" in kwargs["body_html"]


@pytest.mark.asyncio
async def test_interview_invite_email_uses_tenant_name_without_client(
    db_session: AsyncSession, admin_user: User
):
    """Вакансия без заказчика → в письме компания-арендатор, а не пустое место."""
    from app.services.glafira import interview_schedule

    cid = admin_user.company_id
    admin_user.b24_user_id = 42
    vacancy = await _make_vacancy(db_session, cid, client_id=None)
    vacancy.auto_interview = True
    vacancy.auto_interview_stage = "interview"
    db_session.add(VacancyTeam(
        company_id=cid, vacancy_id=vacancy.id, user_id=admin_user.id, is_responsible=True,
    ))
    candidate = Candidate(
        company_id=cid, first_name="Иван", last_name="Петров",
        email="ivan@example.com", source="hh",
    )
    db_session.add(candidate)
    await db_session.flush()
    db_session.add(Application(
        company_id=cid, candidate_id=candidate.id, vacancy_id=vacancy.id, stage="interview",
    ))
    db_session.add(Integration(
        company_id=cid, provider="bitrix24", config={"webhook_url": "enc"},
    ))
    await db_session.flush()

    with patch.object(interview_schedule, "send_email", new=AsyncMock()) as mock_send:
        stats = await interview_schedule.send_interview_links(db_session, cid)

    assert stats["sent"] == 1, stats
    kwargs = mock_send.await_args.kwargs
    assert "Test Company" in kwargs["body_text"]
    assert "«»" not in kwargs["body_text"]


# ── E. Обязательность заказчика (только в HTTP-роутах) ───────────────────────

@pytest.mark.asyncio
async def test_create_vacancy_without_client_returns_400(
    async_client: AsyncClient, auth_headers: dict
):
    """POST /vacancies без заказчика → 400 (бизнес-ошибка), не 422."""
    resp = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Вакансия без заказчика"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "заказчик" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_create_vacancy_with_client_succeeds(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    client = await _make_client(db_session, admin_user.company_id, "ООО Заказчик")
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/vacancies",
        headers=auth_headers,
        json={"name": "Вакансия с заказчиком", "client_id": str(client.id)},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["client_name"] == "ООО Заказчик"


@pytest.mark.asyncio
async def test_patch_vacancy_explicit_null_client_returns_400(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """PATCH с ЯВНЫМ client_id=null → 400 (заказчика нельзя снять)."""
    client = await _make_client(db_session, admin_user.company_id, "ООО Заказчик")
    vacancy = await _make_vacancy(db_session, admin_user.company_id, client_id=client.id)
    await db_session.commit()

    resp = await async_client.patch(
        f"/api/v1/vacancies/{vacancy.id}",
        headers=auth_headers,
        json={"client_id": None},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_patch_vacancy_without_client_field_still_works(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Старая вакансия БЕЗ заказчика редактируется, пока client_id не прислан явно."""
    vacancy = await _make_vacancy(db_session, admin_user.company_id, client_id=None)
    await db_session.commit()

    resp = await async_client.patch(
        f"/api/v1/vacancies/{vacancy.id}",
        headers=auth_headers,
        json={"name": "Переименована"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Переименована"


@pytest.mark.asyncio
async def test_hh_vacancy_import_without_client_still_works(
    db_session: AsyncSession, admin_user: User
):
    """⚠️ hh-импорт зовёт create_vacancy НАПРЯМУЮ, без заказчика — ломаться не должен.

    Валидация обязательности живёт ТОЛЬКО в HTTP-роуте POST /vacancies.
    """
    from app.schemas.vacancy import VacancyCreate
    from app.services.vacancy import create_vacancy

    vacancy = await create_vacancy(
        db_session,
        VacancyCreate(name="Вакансия с hh", team=[admin_user.id]),
        admin_user.company_id,
        admin_user.id,
    )
    assert vacancy.id is not None
    assert vacancy.client_id is None
