"""Тесты суперадмин-сервиса (изолированный CRUD тенантов).

Стиль как в репозитории: async + httpx ASGITransport, БД через _session_local_returning
(патч AsyncSessionLocal по месту использования). config суперадмина читается на импорте,
поэтому патчим сам объект config. Sync-тесты авторизации НЕ тянут async-фикстуру db_session.
"""
from contextlib import asynccontextmanager

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models import Company, User, GlafiraSettings
from app.provision_company import ProvisionError
from app.services.settings.crypto import decrypt_text

import superadmin.service as super_service
from superadmin.config import config as super_config
from superadmin.auth import auth_service
from superadmin.service import company_service
from superadmin.main import app as superadmin_app
from superadmin.test_results import parse_test_results

_FERNET = Fernet.generate_key().decode()


def _session_local_returning(db_session):
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


@pytest.fixture(autouse=True)
def _super_env(monkeypatch):
    """FERNET + креды суперадмина (объект config — тот же, что в auth.py/service.py)."""
    monkeypatch.setattr("app.config.settings.FERNET_KEY", _FERNET)
    monkeypatch.setattr(super_config, "SUPERADMIN_USER", "admin")
    monkeypatch.setattr(super_config, "SUPERADMIN_PASSWORD_HASH", get_password_hash("testpass"))
    monkeypatch.setattr(super_config, "SUPERADMIN_JWT_SECRET", "test-secret")


@pytest.fixture
def super_db(monkeypatch, db_session):
    """БД суперадмин-сервиса → тестовая сессия (AsyncSessionLocal используется напрямую)."""
    monkeypatch.setattr(super_service, "AsyncSessionLocal", _session_local_returning(db_session))
    return db_session


# ─────────────────────────── авторизация (unit, sync) ───────────────────────────

def test_verify_credentials_wrong_password():
    assert auth_service.verify_credentials("admin", "wrong") is False


def test_verify_credentials_correct():
    assert auth_service.verify_credentials("admin", "testpass") is True


def test_token_roundtrip_and_garbage():
    token = auth_service.create_token()
    assert auth_service.verify_token(token) == "admin"
    assert auth_service.verify_token("garbage.token.value") is None


def test_not_configured_blocks_login(monkeypatch):
    monkeypatch.setattr(super_config, "SUPERADMIN_PASSWORD_HASH", None)
    assert auth_service.verify_credentials("admin", "testpass") is False


# ─────────────────────────── авторизация (HTTP guard) ───────────────────────────

async def test_dashboard_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=superadmin_app), base_url="http://test") as client:
        resp = await client.get("/super/")  # без cookie
    assert resp.status_code == 303
    assert "/super/login" in resp.headers.get("location", "")


async def test_protected_post_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=superadmin_app), base_url="http://test") as client:
        resp = await client.post("/super/companies/new", data={
            "name": "X", "admin_email": "a@b.c", "admin_full_name": "A", "admin_password": "p",
        })
    assert resp.status_code == 401


async def test_login_correct_sets_cookie():
    async with AsyncClient(transport=ASGITransport(app=superadmin_app), base_url="http://test") as client:
        resp = await client.post("/super/login", data={"username": "admin", "password": "testpass"})
    assert resp.status_code == 303
    assert "super_session" in resp.headers.get("set-cookie", "")


async def test_login_wrong_no_cookie():
    async with AsyncClient(transport=ASGITransport(app=superadmin_app), base_url="http://test") as client:
        resp = await client.post("/super/login", data={"username": "admin", "password": "nope"})
    assert resp.status_code == 200
    assert "super_session" not in resp.headers.get("set-cookie", "")


# ─────────────────────────── CRUD (через сервис, БД=db_session) ───────────────────────────

async def test_create_company_provisions_with_explicit_company_id(super_db):
    db_session = super_db
    await company_service.create_company(
        name="Acme", admin_email="acme@x.io", admin_password="pw123456",
        admin_full_name="Acme Admin", openrouter_api_key="sk-or-v1-secretkey123",
    )
    comp = (await db_session.execute(select(Company).where(Company.name == "Acme"))).scalar_one()
    admin = (await db_session.execute(select(User).where(User.email == "acme@x.io"))).scalar_one()
    # ЯВНЫЙ company_id — админ в своей компании, НЕ в дефолтной
    assert admin.company_id == comp.id
    # ключ зашифрован Fernet, расшифровывается в оригинал
    gs = (await db_session.execute(
        select(GlafiraSettings).where(GlafiraSettings.company_id == comp.id)
    )).scalar_one()
    assert gs.openrouter_api_key is not None
    assert gs.openrouter_api_key != "sk-or-v1-secretkey123"
    assert decrypt_text(gs.openrouter_api_key) == "sk-or-v1-secretkey123"


async def test_create_company_duplicate_email_raises(super_db):
    await company_service.create_company(
        name="C1", admin_email="dup@x.io", admin_password="pw123456", admin_full_name="A",
    )
    with pytest.raises(ProvisionError):
        await company_service.create_company(
            name="C2", admin_email="dup@x.io", admin_password="pw123456", admin_full_name="B",
        )


async def test_list_companies_no_plain_key(super_db):
    await company_service.create_company(
        name="Keyed", admin_email="keyed@x.io", admin_password="pw123456",
        admin_full_name="A", openrouter_api_key="sk-or-secret999",
    )
    companies = await company_service.list_companies()
    target = next(c for c in companies if c.name == "Keyed")
    assert target.has_openrouter_key is True
    # CompanyInfo не несёт плейн-ключ ни в одном атрибуте
    assert "secret999" not in str(vars(target))


async def test_get_company_settings_masks_key(super_db):
    db_session = super_db
    await company_service.create_company(
        name="Mask", admin_email="mask@x.io", admin_password="pw123456",
        admin_full_name="A", openrouter_api_key="sk-or-abcd1234",
    )
    comp = (await db_session.execute(select(Company).where(Company.name == "Mask"))).scalar_one()
    settings_dict = await company_service.get_company_settings(comp.id)
    display = settings_dict["openrouter_key_display"]
    assert display.startswith("••••")
    assert display.endswith("1234")           # last4
    assert "sk-or-abcd1234" not in display     # не плейн


async def test_update_company_replaces_key(super_db):
    db_session = super_db
    await company_service.create_company(
        name="Upd", admin_email="upd@x.io", admin_password="pw123456", admin_full_name="A",
    )
    comp = (await db_session.execute(select(Company).where(Company.name == "Upd"))).scalar_one()
    ok = await company_service.update_company(comp.id, name="Upd2", openrouter_api_key="sk-or-newkey789")
    assert ok is True
    gs = (await db_session.execute(
        select(GlafiraSettings).where(GlafiraSettings.company_id == comp.id)
    )).scalar_one()
    assert decrypt_text(gs.openrouter_api_key) == "sk-or-newkey789"


# ─────────────────────────── junit-парсер (unit, sync) ───────────────────────────

class TestResultsParsing:
    def test_missing_file(self, tmp_path):
        assert parse_test_results(str(tmp_path / "nope.xml")) == {"exists": False}

    def test_parses_counts_and_failed_names(self, tmp_path):
        xml = (
            '<testsuite tests="5" failures="1" errors="1" skipped="1" time="2.5" '
            'timestamp="2026-06-14T00:00:00">'
            '<testcase classname="t.A" name="ok"/>'
            '<testcase classname="t.A" name="bad"><failure>boom</failure></testcase>'
            '<testcase classname="t.B" name="err"><error>oops</error></testcase>'
            '</testsuite>'
        )
        p = tmp_path / "r.xml"
        p.write_text(xml)
        r = parse_test_results(str(p))
        assert r["exists"] is True
        assert r["total"] == 5
        assert r["failed"] == 2
        assert r["skipped"] == 1
        assert r["passed"] == 2
        assert "t.A.bad" in r["failed_names"]
        assert "t.B.err" in r["failed_names"]

    def test_invalid_xml(self, tmp_path):
        p = tmp_path / "bad.xml"
        p.write_text("not xml <<<")
        assert parse_test_results(str(p)) == {"exists": False}
