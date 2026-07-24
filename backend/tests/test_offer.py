"""Тесты фичи «Отправить оффер» (этап «Оффер»).

Дискриминирующие проверки (в проекте тесты регулярно писались «мимо поля»):
- LLM (call_text) и SMTP (send_email) мокаются ПО МЕСТУ ИМПОРТА:
  * call_text импортируется в app/services/glafira/offer.py как `from .client import call_text`
    → патчим `app.services.glafira.offer.call_text`;
  * send_email импортируется в app/services/offer.py как `from ...smtp.service import send_email`
    → патчим `app.services.offer.send_email`;
  * get_company_openrouter_key связано в app/services/offer.py тем же способом
    → патчим `app.services.offer.get_company_openrouter_key` (autouse-дефолт conftest
    патчит ДРУГОЙ модуль — app.services.settings.glafira — и на связанное имя offer.py
    НЕ влияет; поэтому без ключа offer штатно уходит в детерминированный фолбэк).

Фикстуры — реальные из conftest (db_session, admin_user, auth_headers, manager_*).
Чтение Message/AuditLog после запроса — из того же db_session (async_client ходит через
override get_db → та же сессия; route коммитит савпоинтом, строки видны выборкой).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.core.security import get_password_hash
from app.models import Application, AuditLog, Candidate, Client, Message, User, Vacancy
from app.services.offer import DEFAULT_OFFER_FOOTER, DEFAULT_OFFER_HEADER


async def _headers_for_role(
    async_client: AsyncClient, db: AsyncSession, company_id, role: str, email: str
) -> dict:
    """Создать пользователя роли `role` в компании и вернуть его auth-заголовки."""
    db.add(User(
        company_id=company_id, email=email,
        password_hash=get_password_hash("Glafira2026!"),
        full_name=f"{role} user", role=role, is_active=True,
    ))
    await db.commit()
    resp = await async_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Glafira2026!"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── helpers ──────────────────────────────────────────────────────────────────

async def _setup_offer_app(
    db: AsyncSession,
    company_id,
    *,
    stage: str = "offer",
    email: str | None = "cand@example.com",
) -> Application:
    """Заказчик + вакансия (с фактами) + кандидат + заявка на указанном этапе."""
    client = Client(company_id=company_id, name="ООО Заказчик")
    db.add(client)
    await db.flush()

    vacancy = Vacancy(
        company_id=company_id,
        name="Python-разработчик",
        city="Москва",
        employment_type="полная занятость",
        salary_from=150000,
        salary_to=250000,
        client_id=client.id,
        status="active",
    )
    db.add(vacancy)
    await db.flush()

    candidate = Candidate(
        company_id=company_id,
        last_name="Петров",
        first_name="Иван",
        source="manual",
        email=email,
    )
    db.add(candidate)
    await db.flush()

    application = Application(
        company_id=company_id,
        candidate_id=candidate.id,
        vacancy_id=vacancy.id,
        stage=stage,
    )
    db.add(application)
    await db.flush()
    return application


# ── 1. generate: фолбэк без ключа OpenRouter ─────────────────────────────────

@pytest.mark.asyncio
async def test_generate_offer_fallback_without_key(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Нет ключа компании → тело из фолбэка (факты вакансии), header/footer = дефолты.

    Дискриминирующе: call_text НЕ вызывается вовсе (assert_not_awaited) — доказывает, что
    без ключа в LLM не ходим; body содержит «Python-разработчик» — доказывает, что это
    осмысленный фолбэк ИЗ вакансии, а не пустая строка/статичная заглушка.
    """
    from app.services.glafira import offer as glafira_offer

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    with patch.object(
        glafira_offer,
        "call_text",
        AsyncMock(side_effect=AssertionError("LLM не должен вызываться без ключа")),
    ) as mock_llm:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/generate",
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    mock_llm.assert_not_awaited()
    assert data["body"].strip(), "тело оффера не должно быть пустым"
    assert "Python-разработчик" in data["body"], "фолбэк обязан опираться на факты вакансии"
    assert data["header"] == DEFAULT_OFFER_HEADER
    assert data["footer"] == DEFAULT_OFFER_FOOTER


# ── 1b. generate: путь LLM, когда ключ есть ──────────────────────────────────

@pytest.mark.asyncio
async def test_generate_offer_uses_llm_when_key_present(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Ключ есть → тело берётся из ответа LLM; промпт несёт факты вакансии.

    Дискриминирующе: тело в ответе РАВНО канонному ответу call_text (а не фолбэку);
    в user-промпт ушло «Python-разработчик», в system-промпт — про оффер (не «мимо поля»).
    """
    from app.services import offer as offer_svc
    from app.services.glafira import offer as glafira_offer

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    canned = "Иван, рады пригласить вас в нашу команду на позицию Python-разработчика!"
    with patch.object(offer_svc, "get_company_openrouter_key", AsyncMock(return_value="live-key")), \
         patch.object(glafira_offer, "call_text", AsyncMock(return_value=canned)) as mock_llm:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/generate",
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["body"] == canned
    mock_llm.assert_awaited_once()
    kwargs = mock_llm.await_args.kwargs
    assert "Python-разработчик" in kwargs["user"], "факты вакансии не попали в промпт"
    assert "оффер" in kwargs["system"].lower(), "system-промпт не про оффер"


# ── 2 / 7. Гейт этапа (по stage_key 'offer') ─────────────────────────────────

@pytest.mark.asyncio
async def test_generate_offer_rejected_off_stage(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """generate НЕ на этапе offer → 400 VALIDATION_ERROR (не 200)."""
    application = await _setup_offer_app(db_session, admin_user.company_id, stage="interview")
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/applications/{application.id}/offer/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Оффер" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_send_offer_rejected_off_stage(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """send НЕ на этапе offer → 400; письмо не уходит (send_email не вызывается)."""
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id, stage="recruiter")
    await db_session.commit()

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Рады предложить вам работу."},
        )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Оффер" in resp.json()["error"]["message"]
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_offer_ok_on_offer_stage(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """На этапе offer гейт пропускает (200) — доказывает, что ключ гейта = stage=='offer'."""
    application = await _setup_offer_app(db_session, admin_user.company_id, stage="offer")
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/applications/{application.id}/offer/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


# ── 3. send без email кандидата ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_offer_without_candidate_email(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Нет email у кандидата → 400; письмо не уходит.

    Дискриминирующе: send_email не вызван (если бы проверки не было, mocked send_email
    отработал бы и вернул 200).
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id, email=None)
    await db_session.commit()

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Рады предложить вам работу."},
        )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "email" in resp.json()["error"]["message"].lower()
    mock_send.assert_not_awaited()


# ── 4. send успешный: письмо + Message + audit ───────────────────────────────

@pytest.mark.asyncio
async def test_send_offer_success_writes_message_and_audit(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Успех: send_email ровно 1 раз с брендированным HTML; Message(out/email); audit send_offer.

    Дискриминирующе:
    - body_html прогнан через брендированный шаблон (есть <!DOCTYPE html> и заголовок
      «Предложение о работе»), а body_text — плоский (без <!DOCTYPE) → доказывает, что
      письмо НЕ ушло голым plaintext;
    - в БД появилась строка Message(direction='out', channel='email') с телом оффера;
    - в audit_log есть запись action='send_offer' с entity_id заявки — убери audit, тест краснеет;
    - при пустых настройках в тело попали ДЕФОЛТНЫЕ header/footer.
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    sent_body = "Рады предложить вам работу в нашей команде."
    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": sent_body},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"

    mock_send.assert_awaited_once()
    kwargs = mock_send.await_args.kwargs
    # Брендированный HTML, а не голый plaintext
    assert "<!DOCTYPE html>" in kwargs["body_html"]
    assert "Предложение о работе" in kwargs["body_html"]
    assert "<!DOCTYPE" not in kwargs["body_text"]
    # Тело содержит и текст рекрутёра, и дефолтное обрамление
    assert sent_body in kwargs["body_text"]
    assert DEFAULT_OFFER_HEADER in kwargs["body_text"]
    assert DEFAULT_OFFER_FOOTER in kwargs["body_text"]
    # Тема с вакансией
    assert "Python-разработчик" in kwargs["subject"]
    assert kwargs["to"] == "cand@example.com"
    # Без файла вложений нет (обратная совместимость с обычным оффером)
    assert kwargs.get("attachments") is None

    # Message в БД
    msg = (
        await db_session.execute(
            select(Message).where(Message.application_id == application.id)
        )
    ).scalar_one_or_none()
    assert msg is not None, "оффер не записан как сообщение (не виден в Чате)"
    assert msg.direction == "out"
    assert msg.channel == "email"
    assert msg.sender_type == "recruiter"
    assert sent_body in msg.body
    assert DEFAULT_OFFER_HEADER in msg.body

    # audit send_offer
    audit_row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "send_offer",
                AuditLog.entity_id == application.id,
            )
        )
    ).scalar_one_or_none()
    assert audit_row is not None, "нет записи audit_log action='send_offer' (§2.2)"
    assert audit_row.entity_type == "application"
    assert audit_row.actor_type == "human"


# ── 5. send: header/footer из настроек попадают в письмо ──────────────────────

@pytest.mark.asyncio
async def test_send_offer_uses_settings_header_footer(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Заданные в настройках приветствие/подпись реально обрамляют письмо (не дефолты).

    Дискриминирующе: в body_text есть кастомные строки И нет дефолтного «Здравствуйте!»
    — доказывает, что обрамление берётся из настроек, а сервер применяет именно их.
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    custom_header = "Дорогой кандидат, у нас отличные новости."
    custom_footer = "С наилучшими пожеланиями, HR-команда."
    patch_resp = await async_client.patch(
        "/api/v1/settings/glafira",
        headers=auth_headers,
        json={"offer_email_header": custom_header, "offer_email_footer": custom_footer},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    # Настройка реально доехала до схемы ответа (Part A wiring)
    assert patch_resp.json()["offer_email_header"] == custom_header

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Готовы сделать вам предложение."},
        )

    assert resp.status_code == 200, resp.text
    body_text = mock_send.await_args.kwargs["body_text"]
    assert custom_header in body_text
    assert custom_footer in body_text
    assert DEFAULT_OFFER_HEADER not in body_text, "дефолтное приветствие должно быть заменено"


# ── 6. RBAC: manager запрещён на обоих эндпоинтах ────────────────────────────

@pytest.mark.asyncio
async def test_offer_endpoints_forbidden_for_manager(
    async_client: AsyncClient,
    manager_headers: dict,
    db_session: AsyncSession,
    admin_user: User,
):
    """Роль manager → 403 и на generate, и на send (hiring_manager отсечён на роутере)."""
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    gen = await async_client.post(
        f"/api/v1/applications/{application.id}/offer/generate",
        headers=manager_headers,
    )
    assert gen.status_code == 403, gen.text
    assert gen.json()["error"]["code"] == "FORBIDDEN"

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        snd = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=manager_headers,
            data={"body": "Оффер"},
        )
    assert snd.status_code == 403, snd.text
    assert snd.json()["error"]["code"] == "FORBIDDEN"
    mock_send.assert_not_awaited()


# ── Валидация тела: пустой/пробельный body → 400 ─────────────────────────────
# NB: эндпоинт перешёл на multipart/form-data → прежняя Pydantic-валидация тела
# (min_length/field_validator) не применяется; тело проверяется вручную в роуте →
# честная 400 (ValidationError). ЕДИНЫЙ подход: и пустое, и пробельное = 400.

@pytest.mark.asyncio
async def test_send_offer_empty_body_400(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Пустое тело оффера → 400 (ручная проверка в роуте), а не отправка пустого письма.

    Дискриминирующе: field присутствует (body=""), Form(...) его пропускает, а гейт
    `if not body.strip()` даёт 400 VALIDATION_ERROR. Без гейта ушло бы пустое письмо (200).
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": ""},
        )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_offer_blank_body_400(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Тело из одних пробелов → 400; письмо не уходит.

    Дискриминирующе: «   \\n  » прошло бы наивную проверку «поле не пустое» (len>0),
    а гейт `if not body.strip()` ловит пробельный центр → 400, send_email не вызван.
    Без гейта ушёл бы оффер с пустым телом (200 + send_email вызван) — тест краснеет.
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "   \n  "},
        )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_offer_smtp_failure_no_fake_sent(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Сбой SMTP → 400 и НИКАКОГО фейкового «отправлено» (§0).

    Дискриминирующе: send_email кидает ValidationError (как при ненастроенном SMTP).
    Инвариант фичи — отправка ДО записи Message/audit: при сбое в БД не должно появиться
    ни Message (иначе оффер «виден в Чате», хотя не ушёл), ни audit_log send_offer.
    Регресс, переставляющий запись перед отправкой ИЛИ глотающий ошибку с возвратом
    status='sent', этот тест краснит — раньше такого теста не было вовсе.
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    with patch.object(
        offer_svc, "send_email",
        new=AsyncMock(side_effect=ValidationError("SMTP не настроен")),
    ) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Рады предложить вам работу."},
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    mock_send.assert_awaited_once()

    # Никакого фейкового «отправлено»: ни сообщения в Чате, ни записи в аудите.
    msg = (
        await db_session.execute(
            select(Message).where(Message.application_id == application.id)
        )
    ).scalar_one_or_none()
    assert msg is None, "при сбое SMTP оффер НЕ должен появиться как сообщение"

    audit_row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "send_offer",
                AuditLog.entity_id == application.id,
            )
        )
    ).scalar_one_or_none()
    assert audit_row is None, "при сбое SMTP не должно быть audit send_offer"


@pytest.mark.asyncio
async def test_offer_allowed_for_recruiter(
    async_client: AsyncClient, db_session: AsyncSession, admin_user: User
):
    """Рекрутёр (не admin) — основной пользователь фичи — оффер слать МОЖЕТ (не 403).

    Дискриминирующе: если гейт ужесточить до admin-only, рекрутёр словил бы 403, и все
    admin-тесты остались бы зелёными — этот ловит именно такую регрессию.
    """
    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()
    rec_headers = await _headers_for_role(
        async_client, db_session, admin_user.company_id, "recruiter", "recruiter.offer@example.com"
    )

    resp = await async_client.post(
        f"/api/v1/applications/{application.id}/offer/generate",
        headers=rec_headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_offer_forbidden_for_hiring_manager(
    async_client: AsyncClient, db_session: AsyncSession, admin_user: User
):
    """Роль hiring_manager отсечена на роутере (_deny_hm) → 403 на обоих эндпоинтах.

    Дискриминирующе: manager блокируется ДРУГИМ путём (инлайн-проверкой в эндпоинте),
    поэтому manager-тест не доказал бы изоляцию hiring_manager. Если оффер-роуты
    смонтировать без _deny_hm, hiring_manager прошёл бы — этот тест краснеет.
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()
    hm_headers = await _headers_for_role(
        async_client, db_session, admin_user.company_id, "hiring_manager", "hm.offer@example.com"
    )

    gen = await async_client.post(
        f"/api/v1/applications/{application.id}/offer/generate",
        headers=hm_headers,
    )
    assert gen.status_code == 403, gen.text

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        snd = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=hm_headers,
            data={"body": "Оффер"},
        )
    assert snd.status_code == 403, snd.text
    mock_send.assert_not_awaited()


# ── Вложение к письму-офферу ─────────────────────────────────────────────────
# Валидное вложение → уходит с письмом; сбойные (большой/чужой тип) → 400 и письмо
# не уходит; имя файла санитайзится. (Кейс «без файла → attachments=None» уже
# покрыт test_send_offer_success_writes_message_and_audit — он шлёт data без files
# и проверяет kwargs.get("attachments") is None → это и есть проверка (b).)

@pytest.mark.asyncio
async def test_send_offer_with_attachment(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Файл приложен → уходит вложением; в Чат-Message появляется пометка о файле.

    Дискриминирующе: attachments в аргументах send_email = ровно один элемент с ИМЕННО
    этими байтами, именем и разобранным из content_type MIME (application/pdf) — доказывает,
    что файл реально дошёл до письма, а не «принят схемой и молча потерян» (антипаттерн §0).
    Пометка «📎 Вложение: offer.pdf» в Message.body — доказывает след в Чате.
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    file_bytes = b"%PDF-1.4 fake offer content"
    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Рады предложить вам работу."},
            files={"file": ("offer.pdf", file_bytes, "application/pdf")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"

    mock_send.assert_awaited_once()
    attachments = mock_send.await_args.kwargs["attachments"]
    assert attachments is not None and len(attachments) == 1
    att = attachments[0]
    assert att["filename"] == "offer.pdf"
    assert att["content"] == file_bytes
    assert att["maintype"] == "application"
    assert att["subtype"] == "pdf"

    # В Чате остаётся след, что оффер ушёл с файлом (сам файл не персистим).
    msg = (
        await db_session.execute(
            select(Message).where(Message.application_id == application.id)
        )
    ).scalar_one_or_none()
    assert msg is not None
    assert "📎 Вложение: offer.pdf" in msg.body


@pytest.mark.asyncio
async def test_send_offer_file_too_large_400(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Файл больше 10 МБ → 400; письмо НЕ уходит (send_email не вызван).

    Дискриминирующе: кап проверяется ДО отправки → assert_not_awaited доказывает, что
    великий файл не улетел кандидату. Без капа send_email вызвался бы (200).
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    too_big = b"x" * (10 * 1024 * 1024 + 1)  # 10 МБ + 1 байт
    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Рады предложить вам работу."},
            files={"file": ("big.pdf", too_big, "application/pdf")},
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_offer_disallowed_extension_400(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Недопустимое расширение (.exe) → 400; письмо не уходит.

    Дискриминирующе: белый список отбивает исполняемый файл ДО отправки (send_email не
    вызван). Если бы валидации типа не было, .exe улетел бы кандидату вложением.
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Рады предложить вам работу."},
            files={"file": ("evil.exe", b"MZ\x90\x00fake", "application/octet-stream")},
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_offer_attachment_filename_path_stripped(
    async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession, admin_user: User
):
    """Имя файла с путём → в письмо уходит только basename (защита от пути в имени).

    Дискриминирующе: сырой «../../etc/evil.pdf» без санитайзации попал бы в
    Content-Disposition как есть; проверяем, что в attachments осталось «evil.pdf» без «/».
    (Стрип управляющих символов/переводов строки проверяется отдельным юнит-тестом ниже —
    HTTP-клиент сам вычищает newline из заголовков, поэтому через эндпоинт его не протащить.)
    """
    from app.services import offer as offer_svc

    application = await _setup_offer_app(db_session, admin_user.company_id)
    await db_session.commit()

    with patch.object(offer_svc, "send_email", new=AsyncMock()) as mock_send:
        resp = await async_client.post(
            f"/api/v1/applications/{application.id}/offer/send",
            headers=auth_headers,
            data={"body": "Рады предложить вам работу."},
            files={"file": ("../../etc/evil.pdf", b"%PDF fake", "application/pdf")},
        )

    assert resp.status_code == 200, resp.text
    att = mock_send.await_args.kwargs["attachments"][0]
    assert att["filename"] == "evil.pdf"
    assert "/" not in att["filename"] and "\\" not in att["filename"]


def test_sanitize_attachment_filename_unit():
    """Юнит: basename без путей (оба разделителя) и без control-символов/переводов строк.

    Дискриминирующе: «../../evil\\n.pdf» → «evil.pdf» доказывает, что и путь, и '\\n'
    (ord 10 < 32) вычищены — это тот кейс инъекции заголовка, который через HTTP-слой
    не воспроизвести (httpx санитайзит newline в заголовке сам). Пустое/None → «attachment».
    """
    from app.api.v1.applications import _sanitize_attachment_filename

    assert _sanitize_attachment_filename("../../evil\n.pdf") == "evil.pdf"
    assert _sanitize_attachment_filename(r"C:\Users\x\report.docx") == "report.docx"
    assert _sanitize_attachment_filename("plain.pdf") == "plain.pdf"
    assert _sanitize_attachment_filename("") == "attachment"
    assert _sanitize_attachment_filename(None) == "attachment"
    # Слишком длинное имя обрезается до 150 символов
    assert len(_sanitize_attachment_filename("a" * 300 + ".pdf")) <= 150
