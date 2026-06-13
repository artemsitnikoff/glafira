"""Тесты импорта сотрудников из Битрикс24 → Employee и расчёта Текучки по источнику.

REST-клиент (get_all_users / get_departments) ВСЕГДА замокан — без сети.
Проверяем реальную логику upsert в Employee, маппинг полей, идемпотентность,
а также gate turnover_source ('none' пуст / 'bitrix24' фильтрует).
"""

from datetime import date, timedelta

import pytest
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.services.integrations.bitrix24 import service as b24_service
from app.services.analytics.turnover import build_turnover
from app.services.analytics.common import AnalyticsFilters
from app.models import Employee, GlafiraSettings

WEBHOOK = "https://demo.bitrix24.ru/rest/1/abc123secretcode/"
USERS_TARGET = "app.services.integrations.bitrix24.service.b24_client.get_all_users"
DEPTS_TARGET = "app.services.integrations.bitrix24.service.b24_client.get_departments"


@pytest.fixture
def fernet_key(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.FERNET_KEY", test_key)
    return test_key


async def _save_b24(db_session, user):
    return await b24_service.save_config(
        db_session, user.company_id, user.id, webhook_url=WEBHOOK
    )


def _patch_b24(users, departments=None):
    """Патчит get_all_users и get_departments одновременно."""
    return patch.multiple(
        "app.services.integrations.bitrix24.service.b24_client",
        get_all_users=AsyncMock(return_value=users),
        get_departments=AsyncMock(return_value=departments or []),
    )


# ---------------------------------------------------------------------------
# import_employees_from_b24
# ---------------------------------------------------------------------------

async def test_import_creates_active_and_inactive(db_session, admin_user, fernet_key):
    await _save_b24(db_session, admin_user)

    long_ago = (date.today() - timedelta(days=400)).isoformat()
    users = [
        {"ID": 10, "NAME": "Анна", "LAST_NAME": "Седова", "WORK_POSITION": "HR",
         "ACTIVE": "Y", "UF_EMPLOYMENT_DATE": long_ago, "UF_DEPARTMENT": [1]},
        {"ID": 11, "NAME": "Пётр", "LAST_NAME": "Иванов", "ACTIVE": "N",
         "UF_EMPLOYMENT_DATE": long_ago, "UF_DEPARTMENT": []},
    ]
    departments = [{"ID": 1, "NAME": "Отдел кадров"}]

    with _patch_b24(users, departments):
        result = await b24_service.import_employees_from_b24(
            db_session, admin_user.company_id, admin_user.id
        )

    assert result["total"] == 2
    assert result["created"] == 2
    assert result["updated"] == 0
    assert result["marked_left"] == 1  # уволенный получил left_at

    rows = (await db_session.execute(
        select(Employee).where(Employee.company_id == admin_user.company_id).order_by(Employee.external_id)
    )).scalars().all()
    assert len(rows) == 2

    active = next(e for e in rows if e.external_id == "10")
    assert active.external_source == "bitrix24"
    assert active.candidate_id is None
    assert active.application_id is None
    assert active.manager_user_id is None
    assert active.full_name == "Анна Седова"
    assert active.position == "HR"
    assert active.department == "Отдел кадров"
    assert active.left_at is None
    assert active.status == "passed"  # старт 400 дней назад → испытательный пройден

    inactive = next(e for e in rows if e.external_id == "11")
    assert inactive.status == "left"
    assert inactive.left_at == date.today()  # приблизительная дата обнаружения
    assert inactive.department is None


async def test_import_is_idempotent(db_session, admin_user, fernet_key):
    await _save_b24(db_session, admin_user)

    users = [
        {"ID": 20, "NAME": "Мария", "LAST_NAME": "Петрова", "ACTIVE": "Y",
         "UF_EMPLOYMENT_DATE": "2020-01-01", "UF_DEPARTMENT": []},
    ]

    with _patch_b24(users):
        first = await b24_service.import_employees_from_b24(
            db_session, admin_user.company_id, admin_user.id
        )
    assert first["created"] == 1

    # Re-run with updated position → update, NOT a second row
    users[0]["WORK_POSITION"] = "Менеджер"
    with _patch_b24(users):
        second = await b24_service.import_employees_from_b24(
            db_session, admin_user.company_id, admin_user.id
        )
    assert second["created"] == 0
    assert second["updated"] == 1

    rows = (await db_session.execute(
        select(Employee).where(Employee.external_id == "20")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].position == "Менеджер"


async def test_import_start_date_fallback_to_today(db_session, admin_user, fernet_key):
    await _save_b24(db_session, admin_user)
    users = [
        {"ID": 30, "NAME": "Без", "LAST_NAME": "Даты", "ACTIVE": "Y", "UF_DEPARTMENT": []},
    ]
    with _patch_b24(users):
        await b24_service.import_employees_from_b24(
            db_session, admin_user.company_id, admin_user.id
        )

    row = (await db_session.execute(
        select(Employee).where(Employee.external_id == "30")
    )).scalar_one()
    assert row.start_date == date.today()
    assert row.status == "onboarding"  # старт сегодня → испытательный не пройден


async def test_import_not_configured_raises(db_session, admin_user, fernet_key):
    from app.core.errors import ValidationError
    with pytest.raises(ValidationError):
        await b24_service.import_employees_from_b24(
            db_session, admin_user.company_id, admin_user.id
        )


# ---------------------------------------------------------------------------
# turnover_source gate
# ---------------------------------------------------------------------------

def _filters():
    return AnalyticsFilters(
        period="quarter", date_from=None, date_to=None,  # 90 дней (валидный ANALYTICS_PERIOD)
        vacancy_ids=[], recruiter_ids=[], compare=False,
    )


async def _set_turnover_source(db_session, company_id, source):
    settings_obj = GlafiraSettings(company_id=company_id, turnover_source=source)
    db_session.add(settings_obj)
    await db_session.flush()


async def test_turnover_source_none_returns_empty(db_session, admin_user):
    await _set_turnover_source(db_session, admin_user.company_id, "none")

    resp = await build_turnover(db_session, _filters(), admin_user.company_id)
    assert resp.report == "turnover"
    assert resp.charts == []
    assert resp.tables == []


async def test_turnover_source_bitrix24_filters_to_external(db_session, admin_user):
    await _set_turnover_source(db_session, admin_user.company_id, "bitrix24")

    long_ago = date.today() - timedelta(days=400)

    # B24-imported employee: started 400d ago, still working → retained at day=30.
    b24_emp = Employee(
        company_id=admin_user.company_id,
        candidate_id=None,
        full_name="Б24 Сотрудник",
        start_date=long_ago,
        status="onboarding",
        external_source="bitrix24",
        external_id="100",
    )
    # ATS-native employee (external_source=None): started 400d ago but LEFT after 5 days.
    # If the bitrix24 gate did NOT filter, survival at day=30 would drop to 50%.
    # Filter must exclude it → survival stays 100% (only B24 counted).
    ats_emp = Employee(
        company_id=admin_user.company_id,
        candidate_id=None,  # native employees normally have candidate, but null is allowed now
        full_name="ATS Сотрудник",
        start_date=long_ago,
        status="left",
        left_at=long_ago + timedelta(days=5),
        external_source=None,
        external_id=None,
    )
    db_session.add_all([b24_emp, ats_emp])
    await db_session.flush()

    resp = await build_turnover(db_session, _filters(), admin_user.company_id)

    # Charts present (source connected). Survival curve must reflect ONLY the B24
    # employee — the ATS one (left early) is filtered out by external_source.
    assert len(resp.charts) == 2
    survival = next(c for c in resp.charts if c.type == "survival")
    points = survival.data["points"]
    # At day=30: only B24 employee eligible+retained → 100% (ATS excluded, else it'd be 50%).
    pt30 = next(p for p in points if p["day"] == 30)
    assert pt30["retained_pct"] == 100.0
