"""Битрикс24-интеграция (бизнес-логика).

Конфиг — в generic-таблице `integrations` (provider='bitrix24'), config JSONB.
URL вебхука содержит секретный код → шифруется Fernet и НИКОГДА не возвращается
наружу (в статусе — только домен портала). `status='connected'` — только после
успешной проверки подключения.
"""

import re
from datetime import datetime, timezone, timedelta, date as date_type
from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Integration, User, Employee
from ....schemas.user import UserCreate
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....core.errors import ValidationError
from ..net_guard import validate_outbound_url
from ...user import create_user
from ...integrations.smtp.service import send_credentials_email
from . import client as b24_client

PROVIDER = "bitrix24"

# https://портал.bitrix24.ru/rest/<user_id>/<secret_code>/
WEBHOOK_RE = re.compile(r"^https://[^/\s]+/rest/\d+/[^/\s]+/?$")


def _portal_from_url(webhook_url: str) -> Optional[str]:
    m = re.match(r"^https?://([^/\s]+)/rest/", webhook_url.strip())
    return m.group(1) if m else None


async def _get_row(session: AsyncSession, company_id: UUID) -> Optional[Integration]:
    result = await session.execute(
        select(Integration).where(
            Integration.provider == PROVIDER,
            Integration.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


def _simplify_user(u: dict) -> dict:
    """B24-пользователь → компактная форма для превью (без чувствительных полей)."""
    active = u.get("ACTIVE")
    # B24 отдаёт ACTIVE как bool или строку 'Y'/'N'
    is_active = active is True or (isinstance(active, str) and active.upper() in ("Y", "TRUE", "1"))
    return {
        "id": str(u.get("ID", "")),
        "name": (u.get("NAME") or "").strip(),
        "last_name": (u.get("LAST_NAME") or "").strip(),
        "position": (u.get("WORK_POSITION") or "").strip() or None,
        "email": (u.get("EMAIL") or "").strip() or None,
        "active": is_active,
    }


def _simplify_user_for_import(u: dict, departments_map: dict[str, str]) -> dict:
    """B24-пользователь → форма для импорта (с информацией об отделе)."""
    active = u.get("ACTIVE")
    is_active = active is True or (isinstance(active, str) and active.upper() in ("Y", "TRUE", "1"))

    # Map department IDs to names
    dept_ids = u.get("UF_DEPARTMENT") or []
    if not isinstance(dept_ids, list):
        dept_ids = [dept_ids] if dept_ids else []

    department_names = []
    for dept_id in dept_ids:
        dept_name = departments_map.get(str(dept_id))
        if dept_name:
            department_names.append(dept_name)

    return {
        "b24_id": str(u.get("ID", "")),
        "name": (u.get("NAME") or "").strip(),
        "last_name": (u.get("LAST_NAME") or "").strip(),
        "position": (u.get("WORK_POSITION") or "").strip() or None,
        "email": (u.get("EMAIL") or "").strip() or None,
        "department_ids": [str(d) for d in dept_ids],
        "department_name": ", ".join(department_names) or None,
        "active": is_active,
    }


def _b24_is_active(active) -> bool:
    """B24 отдаёт ACTIVE как bool или строку 'Y'/'N'/'true'/'1'."""
    return active is True or (isinstance(active, str) and active.upper() in ("Y", "TRUE", "1"))


def _parse_b24_date(raw, fallback: date_type) -> date_type:
    """Парсит дату Б24 (ISO/RFC) устойчиво. При любой ошибке → fallback.

    Б24 отдаёт даты в разных форматах ('2021-05-01T03:00:00+03:00',
    '2021-05-01T03:00:00', '01.05.2021'). Берём только дату.
    """
    if not raw or not isinstance(raw, str):
        return fallback
    raw = raw.strip()
    if not raw:
        return fallback
    # ISO 8601 (с/без таймзоны). fromisoformat в py3.11 принимает суффикс 'Z' не всегда — убираем.
    iso = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso).date()
    except (ValueError, TypeError):
        pass
    # Запасные форматы Б24
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw[:len(fmt) + 4], fmt).date()
        except (ValueError, TypeError):
            continue
    return fallback


async def save_config(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    *,
    webhook_url: str,
) -> Integration:
    """Сохраняет URL входящего вебхука (шифруется). Сбрасывает verified."""
    webhook_url = (webhook_url or "").strip()
    if not WEBHOOK_RE.match(webhook_url):
        raise ValidationError(
            "Неверный формат URL вебхука. Ожидается "
            "https://портал.bitrix24.ru/rest/<id>/<код>/"
        )

    # SSRF-защита: блокируем сохранение URL с внутренними/приватными адресами
    await validate_outbound_url(webhook_url)

    portal = _portal_from_url(webhook_url)
    encrypted_url = encrypt_text(webhook_url)

    new_config = {
        "webhook_url": encrypted_url,  # зашифрован, наружу не отдаётся
        "portal": portal,
        "last_test_at": None,
        "last_test_ok": False,
        "last_test_error": None,
        "user_count": None,
    }

    row = await _get_row(session, company_id)
    if row:
        row.config = new_config
        row.status = "disconnected"
    else:
        row = Integration(
            company_id=company_id,
            provider=PROVIDER,
            status="disconnected",
            config=new_config,
        )
        session.add(row)

    await session.flush()

    await audit(
        session,
        action="bitrix24_config_saved",
        entity_type="integration",
        entity_id=row.id,
        after={"portal": portal},
        actor_user_id=user_id,
        company_id=company_id,
    )

    return row


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """Статус интеграции. URL вебхука/секрет НЕ возвращаются — только домен портала."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        return {
            "configured": False,
            "verified": False,
            "portal": None,
            "user_count": None,
            "last_test_at": None,
            "last_test_ok": False,
            "last_test_error": None,
        }

    c = row.config
    return {
        "configured": True,
        "verified": row.status == "connected" and bool(c.get("last_test_ok")),
        "portal": c.get("portal"),
        "user_count": c.get("user_count"),
        "last_test_at": c.get("last_test_at"),
        "last_test_ok": bool(c.get("last_test_ok")),
        "last_test_error": c.get("last_test_error"),
    }


async def _decrypted_webhook(row: Integration) -> str:
    return decrypt_text(row.config["webhook_url"])


async def test_connection(
    session: AsyncSession, company_id: UUID, user_id: UUID
) -> dict:
    """Реальная проверка: user.get на портале. Фиксирует результат (коммитит сам)."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен — сначала сохраните URL вебхука")

    webhook = await _decrypted_webhook(row)
    now = datetime.now(timezone.utc)

    try:
        data = await b24_client.get_users_page(webhook, start=0)
    except Exception as e:
        cfg = dict(row.config)
        cfg["last_test_at"] = now.isoformat()
        cfg["last_test_ok"] = False
        cfg["last_test_error"] = getattr(e, "message", None) or str(e)
        row.config = cfg
        row.status = "disconnected"
        await session.flush()
        await audit(
            session,
            action="bitrix24_test_failed",
            entity_type="integration",
            entity_id=row.id,
            after={"error": cfg["last_test_error"]},
            actor_user_id=user_id,
            company_id=company_id,
        )
        await session.commit()
        raise

    total = data.get("total")

    cfg = dict(row.config)
    cfg["last_test_at"] = now.isoformat()
    cfg["last_test_ok"] = True
    cfg["last_test_error"] = None
    cfg["user_count"] = total
    row.config = cfg
    row.status = "connected"
    await session.flush()
    await audit(
        session,
        action="bitrix24_test_ok",
        entity_type="integration",
        entity_id=row.id,
        after={"portal": cfg.get("portal"), "user_count": total},
        actor_user_id=user_id,
        company_id=company_id,
    )
    await session.commit()

    return {"portal": cfg.get("portal"), "user_count": total}


async def preview_users(session: AsyncSession, company_id: UUID, limit: int = 20) -> dict:
    """Реальное чтение первой страницы сотрудников с портала (для превью).

    НЕ импортирует в Глафиру — это следующий этап (нужно решение по модели данных,
    куда складывать сотрудников Б24 и как считать «Текучку»).
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    webhook = await _decrypted_webhook(row)
    data = await b24_client.get_users_page(webhook, start=0)
    raw = data.get("result") or []
    users = [_simplify_user(u) for u in raw[:limit]]
    return {"total": data.get("total"), "users": users}


async def list_departments(session: AsyncSession, company_id: UUID) -> list[dict]:
    """Список отделов из Битрикс24."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    webhook = await _decrypted_webhook(row)
    departments = await b24_client.get_departments(webhook)

    # Simplify department structure
    result = []
    for dept in departments:
        result.append({
            "id": str(dept.get("ID", "")),
            "name": str(dept.get("NAME", "")),
            "parent": str(dept.get("PARENT", "")) if dept.get("PARENT") else None,
        })

    return result


async def get_import_candidates(session: AsyncSession, company_id: UUID) -> list[dict]:
    """Пользователи Битрикс24 для импорта (с отделами)."""
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    webhook = await _decrypted_webhook(row)

    # Get departments for mapping
    departments = await b24_client.get_departments(webhook)
    departments_map = {str(dept.get("ID", "")): str(dept.get("NAME", "")) for dept in departments}

    # Get all users
    users = await b24_client.get_all_users(webhook)

    # Convert to import format. Уволенных (ACTIVE=N) НЕ показываем для импорта.
    result = []
    for user in users:
        candidate = _simplify_user_for_import(user, departments_map)
        if candidate["active"]:
            result.append(candidate)

    return result


async def import_users(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    *,
    b24_user_ids: list[str],
    role: str,
    delivery: str = "email"
) -> dict:
    """Импорт пользователей из Битрикс24."""
    if delivery != "email":
        raise ValidationError("Пока поддерживается только доставка по email")

    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    webhook = await _decrypted_webhook(row)

    # Get fresh user data from B24
    all_users = await b24_client.get_all_users(webhook)
    users_by_id = {str(u.get("ID", "")): u for u in all_users}

    created = []
    emailed = []
    shown = []
    skipped = []

    for b24_id in b24_user_ids:
        b24_user = users_by_id.get(str(b24_id))
        if not b24_user:
            skipped.append({
                "name": f"ID {b24_id}",
                "reason": "Пользователь не найден в Битрикс24"
            })
            continue

        name = (b24_user.get("NAME") or "").strip()
        last_name = (b24_user.get("LAST_NAME") or "").strip()
        full_name = f"{name} {last_name}".strip() or f"Пользователь {b24_id}"
        position = (b24_user.get("WORK_POSITION") or "").strip() or None
        email = (b24_user.get("EMAIL") or "").strip()

        if not email:
            skipped.append({
                "name": full_name,
                "reason": "Нет email в Битрикс24"
            })
            continue

        # Check if user already exists (by email)
        existing_result = await session.execute(
            select(User).where(User.email == email)
        )
        existing_user = existing_result.scalar_one_or_none()

        if existing_user:
            skipped.append({
                "name": full_name,
                "reason": f"Пользователь с email {email} уже существует"
            })
            continue

        # Create user
        try:
            user_create = UserCreate(
                email=email,
                full_name=full_name,
                role=role,
                position=position
            )
            user, temp_password = await create_user(session, user_create, company_id, user_id, source="b24")

            created.append({
                "email": email,
                "full_name": full_name
            })

            # Try to send email
            try:
                await send_credentials_email(
                    session, company_id, to=email, full_name=full_name, temp_password=temp_password
                )
                emailed.append(email)
            except Exception:
                # Email failed, but user created - show temp password
                shown.append({
                    "email": email,
                    "temp_password": temp_password,
                    "full_name": full_name
                })

        except Exception as e:
            skipped.append({
                "name": full_name,
                "reason": f"Ошибка создания: {str(e)}"
            })

    # Audit the import action
    await audit(
        session,
        action="bitrix24_import_users",
        entity_type="integration",
        entity_id=row.id,
        after={
            "imported_count": len(created),
            "skipped_count": len(skipped),
            "role": role
        },
        actor_user_id=user_id,
        company_id=company_id,
    )

    return {
        "created": created,
        "emailed": emailed,
        "shown": shown,
        "skipped": skipped
    }


async def import_employees_from_b24(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
) -> dict:
    """Импортирует ВСЕХ сотрудников из Б24 в таблицу `employees` (для расчёта Текучки).

    Идемпотентно (upsert по company_id + external_source='bitrix24' + external_id=ID).
    Импортированные сотрудники НЕ попадают в Пульс (external_source != NULL).

    ⚠️ Б24 НЕ отдаёт точную дату увольнения. Поэтому для уволенных (ACTIVE=N) у
    которых left_at ещё не зафиксирован, ставим left_at = СЕГОДНЯ — это дата
    ОБНАРУЖЕНИЯ увольнения, а не реальная дата ухода. Текучка по таким строкам
    приблизительна. Если left_at уже стоял (увольнение зафиксировали ранее) —
    не перезаписываем.
    """
    row = await _get_row(session, company_id)
    if not row or not row.config or not row.config.get("webhook_url"):
        raise ValidationError("Битрикс24 не настроен")

    webhook = await _decrypted_webhook(row)
    today = date_type.today()

    # Отделы для маппинга ID → имя
    departments = await b24_client.get_departments(webhook)
    departments_map = {str(d.get("ID", "")): str(d.get("NAME", "")) for d in departments}

    all_users = await b24_client.get_all_users(webhook)

    # Существующие импортированные Employee этой компании — по external_id
    existing_rows = (await session.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.external_source == PROVIDER,
        )
    )).scalars().all()
    existing_by_ext_id = {e.external_id: e for e in existing_rows}

    created = 0
    updated = 0
    marked_left = 0
    total = 0

    for u in all_users:
        ext_id = str(u.get("ID", "")).strip()
        if not ext_id:
            continue
        total += 1

        name = (u.get("NAME") or "").strip()
        last_name = (u.get("LAST_NAME") or "").strip()
        full_name = f"{name} {last_name}".strip() or f"Сотрудник {ext_id}"
        position = (u.get("WORK_POSITION") or "").strip() or None

        # Отдел: первый из UF_DEPARTMENT → имя через departments_map
        dept_ids = u.get("UF_DEPARTMENT") or []
        if not isinstance(dept_ids, list):
            dept_ids = [dept_ids] if dept_ids else []
        department = None
        for did in dept_ids:
            dn = departments_map.get(str(did))
            if dn:
                department = dn
                break

        # Дата старта: UF_EMPLOYMENT_DATE → DATE_REGISTER → today
        start_date = _parse_b24_date(
            u.get("UF_EMPLOYMENT_DATE") or u.get("DATE_REGISTER"), today
        )

        is_active = _b24_is_active(u.get("ACTIVE"))

        existing = existing_by_ext_id.get(ext_id)

        if existing:
            # Upsert: обновляем поля профиля
            existing.full_name = full_name
            existing.position = position
            existing.department = department
            existing.start_date = start_date

            if is_active:
                # Снова активен → определяем статус по проходу испытательного срока.
                # left_at НЕ трогаем (если был — оставляем; в Б24 нет точной даты, не реанимируем вслепую).
                if existing.left_at is None:
                    probation_end = start_date + timedelta(days=existing.probation_days)
                    existing.status = "passed" if probation_end <= today else "onboarding"
            else:
                # Уволен в Б24. left_at ставим только если ещё не зафиксирован (см. docstring).
                if existing.left_at is None:
                    existing.left_at = today  # дата ОБНАРУЖЕНИЯ увольнения, не точная
                    marked_left += 1
                existing.status = "left"

            updated += 1
        else:
            if is_active:
                probation_end = start_date + timedelta(days=90)
                status = "passed" if probation_end <= today else "onboarding"
                left_at = None
            else:
                # Уже уволен на момент первого импорта → left_at = today (приблизительно).
                status = "left"
                left_at = today
                marked_left += 1

            employee = Employee(
                company_id=company_id,
                candidate_id=None,
                application_id=None,
                manager_user_id=None,  # Б24-руководителей на наших users надёжно не маппим
                full_name=full_name,
                position=position,
                department=department,
                start_date=start_date,
                status=status,
                left_at=left_at,
                external_source=PROVIDER,
                external_id=ext_id,
            )
            session.add(employee)
            created += 1

    await session.flush()

    await audit(
        session,
        action="bitrix24_import_employees",
        entity_type="integration",
        entity_id=row.id,
        after={
            "created": created,
            "updated": updated,
            "marked_left": marked_left,
            "total": total,
        },
        actor_user_id=user_id,
        company_id=company_id,
    )

    return {
        "created": created,
        "updated": updated,
        "marked_left": marked_left,
        "total": total,
    }


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID) -> None:
    """Отключает (status=disconnected, verified сбрасывается). Конфиг оставляем."""
    row = await _get_row(session, company_id)
    if not row:
        raise ValidationError("Битрикс24 не настроен")

    row.status = "disconnected"
    cfg = dict(row.config) if row.config else {}
    cfg["last_test_ok"] = False
    row.config = cfg

    await session.flush()
    await audit(
        session,
        action="bitrix24_disconnected",
        entity_type="integration",
        entity_id=row.id,
        actor_user_id=user_id,
        company_id=company_id,
    )
