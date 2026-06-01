"""Тесты импорта пользователей из Битрикс24.

REST-клиент (get_departments/get_all_users) и SMTP (send_email) ЗАМОКАНЫ — без сети.
Цели патча: client.* (сервис зовёт b24_client.X) и service.send_email (импортирован
в namespace сервиса — патчим там, где используется).
"""

import pytest
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.models import Integration, User
from app.services.settings.crypto import encrypt_text
from app.services.integrations.bitrix24 import service as b24
from app.services.integrations.bitrix24.service import _simplify_user_for_import
from app.core.security import get_password_hash
from app.core.errors import ValidationError

DEPT_GET = "app.services.integrations.bitrix24.client.get_departments"
USERS_GET = "app.services.integrations.bitrix24.client.get_all_users"
SEND_EMAIL = "app.services.integrations.bitrix24.service.send_credentials_email"

WEBHOOK = "https://demo.bitrix24.ru/rest/1/abc123code/"

B24_DEPTS = [
    {"ID": "1", "NAME": "Отдел продаж", "PARENT": None},
    {"ID": "2", "NAME": "IT отдел", "PARENT": None},
]
B24_USERS = [
    {"ID": "10", "NAME": "Иван", "LAST_NAME": "Иванов", "EMAIL": "ivan@example.com",
     "WORK_POSITION": "Менеджер", "ACTIVE": True, "UF_DEPARTMENT": ["1"]},
    {"ID": "20", "NAME": "Пётр", "LAST_NAME": "Петров", "EMAIL": "petr@example.com",
     "WORK_POSITION": "Разработчик", "ACTIVE": "Y", "UF_DEPARTMENT": ["2"]},
    {"ID": "30", "NAME": "Мария", "LAST_NAME": "Сидорова", "EMAIL": "",
     "WORK_POSITION": "Дизайнер", "ACTIVE": True, "UF_DEPARTMENT": []},
    {"ID": "40", "NAME": "Уволенный", "LAST_NAME": "Сотрудник", "EMAIL": "fired@example.com",
     "WORK_POSITION": "Бывший", "ACTIVE": "N", "UF_DEPARTMENT": ["1"]},
]


@pytest.fixture
def fernet_key(monkeypatch):
    monkeypatch.setattr("app.config.settings.FERNET_KEY", Fernet.generate_key().decode())


async def _integration(db_session, company_id):
    row = Integration(
        company_id=company_id,
        provider="bitrix24",
        status="connected",
        config={
            "webhook_url": encrypt_text(WEBHOOK),
            "portal": "demo.bitrix24.ru",
            "last_test_ok": True,
            "last_test_at": None,
            "last_test_error": None,
            "user_count": 3,
        },
    )
    db_session.add(row)
    await db_session.flush()
    return row


# --------------------------- чистая функция ---------------------------

def test_simplify_user_for_import():
    u = {"ID": "10", "NAME": "Иван", "LAST_NAME": "Иванов", "EMAIL": "ivan@example.com",
         "WORK_POSITION": "Менеджер", "ACTIVE": True, "UF_DEPARTMENT": ["1", "2"]}
    r = _simplify_user_for_import(u, {"1": "Продажи", "2": "Маркетинг"})
    assert r == {
        "b24_id": "10", "name": "Иван", "last_name": "Иванов", "position": "Менеджер",
        "email": "ivan@example.com", "department_ids": ["1", "2"],
        "department_name": "Продажи, Маркетинг", "active": True,
    }


# --------------------------- отделы ---------------------------

async def test_list_departments(db_session, admin_user, fernet_key):
    await _integration(db_session, admin_user.company_id)
    with patch(DEPT_GET, new=AsyncMock(return_value=B24_DEPTS)):
        depts = await b24.list_departments(db_session, admin_user.company_id)
    assert len(depts) == 2
    assert depts[0] == {"id": "1", "name": "Отдел продаж", "parent": None}


async def test_list_departments_not_configured(db_session, admin_user, fernet_key):
    with pytest.raises(ValidationError):
        await b24.list_departments(db_session, admin_user.company_id)


# --------------------------- кандидаты на импорт ---------------------------

async def test_get_import_candidates(db_session, admin_user, fernet_key):
    await _integration(db_session, admin_user.company_id)
    with patch(DEPT_GET, new=AsyncMock(return_value=B24_DEPTS)), \
         patch(USERS_GET, new=AsyncMock(return_value=B24_USERS)):
        cands = await b24.get_import_candidates(db_session, admin_user.company_id)
    # уволенный (id 40, ACTIVE=N) исключён → остаются 3 активных
    assert len(cands) == 3
    assert all(c["b24_id"] != "40" for c in cands)
    assert cands[0]["b24_id"] == "10"
    assert cands[0]["department_name"] == "Отдел продаж"
    assert cands[2]["email"] is None  # Мария без email


# --------------------------- импорт ---------------------------

async def test_import_success_emails(db_session, admin_user, fernet_key):
    await _integration(db_session, admin_user.company_id)
    send = AsyncMock()
    with patch(USERS_GET, new=AsyncMock(return_value=B24_USERS)), patch(SEND_EMAIL, new=send):
        res = await b24.import_users(
            db_session, admin_user.company_id, admin_user.id,
            b24_user_ids=["10", "20"], role="recruiter",
        )
    assert len(res["created"]) == 2
    assert sorted(res["emailed"]) == ["ivan@example.com", "petr@example.com"]
    assert res["shown"] == [] and res["skipped"] == []
    assert send.await_count == 2
    # реально создан в БД
    exists = (await db_session.execute(select(User).where(User.email == "ivan@example.com"))).scalar_one_or_none()
    assert exists is not None and exists.role == "recruiter"


async def test_import_email_failure_falls_back_to_shown(db_session, admin_user, fernet_key):
    await _integration(db_session, admin_user.company_id)
    with patch(USERS_GET, new=AsyncMock(return_value=B24_USERS)), \
         patch(SEND_EMAIL, new=AsyncMock(side_effect=Exception("smtp down"))):
        res = await b24.import_users(
            db_session, admin_user.company_id, admin_user.id,
            b24_user_ids=["10"], role="recruiter",
        )
    assert len(res["created"]) == 1 and res["emailed"] == []
    assert len(res["shown"]) == 1 and "temp_password" in res["shown"][0]


async def test_import_skip_no_email(db_session, admin_user, fernet_key):
    await _integration(db_session, admin_user.company_id)
    with patch(USERS_GET, new=AsyncMock(return_value=B24_USERS)), patch(SEND_EMAIL, new=AsyncMock()):
        res = await b24.import_users(
            db_session, admin_user.company_id, admin_user.id,
            b24_user_ids=["30"], role="recruiter",
        )
    assert res["created"] == [] and len(res["skipped"]) == 1
    assert "email" in res["skipped"][0]["reason"].lower()


async def test_import_skip_existing_email(db_session, admin_user, fernet_key):
    await _integration(db_session, admin_user.company_id)
    db_session.add(User(
        company_id=admin_user.company_id, email="ivan@example.com",
        password_hash=get_password_hash("x"), full_name="Уже Есть", role="recruiter",
    ))
    await db_session.flush()
    with patch(USERS_GET, new=AsyncMock(return_value=B24_USERS)), patch(SEND_EMAIL, new=AsyncMock()):
        res = await b24.import_users(
            db_session, admin_user.company_id, admin_user.id,
            b24_user_ids=["10"], role="recruiter",
        )
    assert res["created"] == [] and len(res["skipped"]) == 1
    assert "существует" in res["skipped"][0]["reason"]


async def test_import_skip_not_found(db_session, admin_user, fernet_key):
    await _integration(db_session, admin_user.company_id)
    with patch(USERS_GET, new=AsyncMock(return_value=B24_USERS)), patch(SEND_EMAIL, new=AsyncMock()):
        res = await b24.import_users(
            db_session, admin_user.company_id, admin_user.id,
            b24_user_ids=["999"], role="recruiter",
        )
    assert res["created"] == [] and len(res["skipped"]) == 1
    assert "не найден" in res["skipped"][0]["reason"]
