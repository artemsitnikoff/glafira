import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.errors import NotFoundError, AlreadySignedError
from ..models import Application, Candidate, Consent, Message
from ..schemas.consent import ConsentOut, ConsentRequest, ConsentRequestResult
from ..services.audit import audit
from ..services.company_display import resolve_company_display_name

logger = logging.getLogger(__name__)

# Срок жизни публичной ссылки подписания.
_CONSENT_LINK_TTL_DAYS = 14

# ⚠️ ДЕФОЛТНЫЙ текст согласия на обработку ПдН (152-ФЗ). Это заглушка «по умолчанию» —
# ПОДЛЕЖИТ ПРАВКЕ ЮРИСТОМ ЗАКАЗЧИКА; позже вынесем в настройку компании. Снимок текста
# сохраняется в consents.consent_text в момент запроса, чтобы кандидат подписывал именно
# то, что видел, даже если шаблон потом изменят.
_CONSENT_TEXT_TEMPLATE = (
    "Согласие на обработку персональных данных. "
    "Я, {name}, действуя своей волей и в своём интересе, даю согласие {company} "
    "на обработку моих персональных данных (ФИО, контактные данные, сведения из резюме, "
    "а также данные из открытых источников) в целях рассмотрения моей кандидатуры и "
    "связанных с этим проверок. Обработка включает сбор, запись, систематизацию, "
    "хранение, использование, проверку и удаление. Согласие действует до достижения целей "
    "обработки либо его отзыва; отзыв — письменным обращением в компанию. "
    "Согласие подписано в электронной форме."
)


def build_consent_text(candidate_full_name: str, company_display_name: str) -> str:
    """Снимок текста согласия на обработку ПдН с подставленными ФИО и компанией.

    ⚠️ Дефолт — см. `_CONSENT_TEXT_TEMPLATE`: юридически подлежит правке юристом заказчика.
    """
    name = (candidate_full_name or "").strip() or "кандидат"
    company = (company_display_name or "").strip() or "компании"
    return _CONSENT_TEXT_TEMPLATE.format(name=name, company=company)


def _consent_invite_text(candidate_full_name: str, company_display: str, link: str) -> str:
    """Плоский текст приглашения подписать согласие (для чат-каналов / фолбэка письма)."""
    greeting = (candidate_full_name or "").strip() or "Здравствуйте"
    co = f" для компании «{company_display}»" if company_display else ""
    return (
        f"Здравствуйте, {greeting}!\n\n"
        f"Для рассмотрения вашей кандидатуры{co} нам нужно ваше согласие на обработку "
        f"персональных данных. Пожалуйста, ознакомьтесь и подпишите его по ссылке:\n{link}\n\n"
        f"Ссылка действительна {_CONSENT_LINK_TTL_DAYS} дней."
    )


async def get_candidate_consent(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID
) -> ConsentOut | None:
    """Get latest consent for candidate"""
    # Verify candidate exists and belongs to company
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    result = await session.execute(
        select(Consent)
        .where(Consent.candidate_id == candidate_id)
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()

    return ConsentOut.model_validate(consent) if consent else None


async def _next_consent_number(session: AsyncSession, company_id: UUID) -> str:
    """Следующий номер согласия PD-NNN/YY под advisory-lock на компанию."""
    lock_key = f"consent_number:{company_id}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": lock_key}
    )

    current_year = datetime.now(timezone.utc).year
    year_suffix = str(current_year)[-2:]

    seq_result = await session.execute(
        text(
            "SELECT COALESCE(MAX(CAST(SPLIT_PART(SPLIT_PART(number, '-', 2), '/', 1) AS INTEGER)), 0) + 1 "
            "FROM consents "
            "WHERE company_id = :company_id AND number LIKE :pattern"
        ),
        {"company_id": company_id, "pattern": f"PD-%/{year_suffix}"},
    )
    seq = seq_result.scalar_one()
    return f"PD-{seq:03d}/{year_suffix}"


async def _auto_consent_channel(
    session: AsyncSession, candidate: Candidate, company_id: UUID
) -> str | None:
    """Автовыбор канала доставки ссылки: email → telegram → hh. None — канала нет."""
    if candidate.email:
        return "email"

    # Telegram: есть username (из messengers или кэша), tg_user_id, либо телефон.
    try:
        from ..services.integrations.telegram import service as tg_service
        tg_username = tg_service.extract_telegram_username(candidate.messengers or [])
    except Exception:  # noqa: BLE001 — не роняем выбор канала из-за импорта/парсинга
        tg_username = None
    extra = candidate.extra or {}
    if tg_username or extra.get("tg_username") or extra.get("tg_user_id") or candidate.phone:
        return "telegram"

    # hh: у кандидата есть диалог на hh (отклик с hh_chat_id).
    hh_app = (await session.execute(
        select(Application.id).where(
            Application.candidate_id == candidate.id,
            Application.company_id == company_id,
            Application.hh_chat_id.isnot(None),
        ).limit(1)
    )).scalar_one_or_none()
    if hh_app:
        return "hh"

    return None


def _render_consent_email(candidate_full_name: str, company_display: str, link: str) -> tuple[str, str]:
    """(body_text, body_html) брендированного письма-приглашения подписать согласие."""
    import html as _html
    from ..services.integrations.smtp.templates import render_simple_email

    body_text = _consent_invite_text(candidate_full_name, company_display, link)

    greeting = _html.escape((candidate_full_name or "").strip() or "Здравствуйте")
    _co = _html.escape(company_display or "")
    _url = _html.escape(link)
    _co_html = (
        f' для компании <strong style="color:#0F1620;font-weight:600;">«{_co}»</strong>'
        if _co else ''
    )
    inner = (
        f'<p style="margin:0 0 14px;">Для рассмотрения вашей кандидатуры{_co_html} нам '
        f'нужно ваше согласие на обработку персональных данных. Пожалуйста, ознакомьтесь '
        f'с текстом и подпишите его по кнопке ниже.</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:22px 0 6px;"><tr>'
        f'<td style="border-radius:8px;background:#2A8AF0;"><a href="{_url}" target="_blank" '
        f'style="display:inline-block;font-family:\'Inter\',Arial,sans-serif;font-size:15px;'
        f'font-weight:600;color:#FFFFFF;padding:13px 26px;border-radius:8px;">Подписать согласие</a></td>'
        f'</tr></table>'
        f'<p style="margin:14px 0 0;font-size:13px;color:#5B6573;">'
        f'Ссылка действительна {_CONSENT_LINK_TTL_DAYS} дней.</p>'
    )
    body_html = render_simple_email(
        f"Здравствуйте, {greeting}!" if greeting != "Здравствуйте" else "Здравствуйте!",
        inner,
        preheader="Согласие на обработку персональных данных",
        company_name=company_display,
    )
    return body_text, body_html


async def _deliver_consent_link(
    session: AsyncSession,
    *,
    candidate: Candidate,
    company_id: UUID,
    actor_user_id: UUID,
    channel: str,
    link: str,
    company_display: str,
) -> tuple[bool, str | None, str | None]:
    """Реальная доставка ссылки согласия кандидату. (delivered, channel, error).

    email — брендированное письмо (render_simple_email + send_email) + запись Message.
    telegram/hh — через message.send_message (реальная отправка + запись Message).
    Никакого фейка: канал недоступен/сбой → delivered=False с честной причиной.
    """
    invite = _consent_invite_text(candidate.full_name, company_display, link)

    if channel == "email":
        if not candidate.email:
            return False, "email", "У кандидата нет email"
        from ..services.integrations.smtp.service import send_email
        body_text, body_html = _render_consent_email(candidate.full_name, company_display, link)
        subject = (
            f"Согласие на обработку данных — {company_display}"
            if company_display else "Согласие на обработку персональных данных"
        )
        await send_email(
            session,
            company_id,
            to=candidate.email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        # Реальная запись в ленту чата — только ПОСЛЕ успешной отправки (не раньше).
        now = datetime.now(timezone.utc)
        session.add(Message(
            company_id=company_id,
            candidate_id=candidate.id,
            channel="email",
            direction="out",
            sender_type="recruiter",
            sender_user_id=actor_user_id,
            body=invite,
            sent_at=now,
            created_at=now,
        ))
        await session.flush()
        return True, "email", None

    if channel in ("telegram", "hh"):
        from ..services.message import send_message
        from ..schemas.message import MessageCreate
        await send_message(
            session,
            candidate.id,
            MessageCreate(channel=channel, body=invite),
            company_id,
            actor_user_id,
        )
        return True, channel, None

    # sms/max/whatsapp и прочее — реальной доставки нет.
    return False, channel, f"Канал «{channel}» не поддерживает автоматическую доставку ссылки"


async def request_consent(
    session: AsyncSession,
    candidate_id: UUID,
    request_data: ConsentRequest,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentRequestResult:
    """Запросить согласие кандидата: создать запись + доставить публичную ссылку подписания.

    Генерирует токен/срок/снимок текста, строит ссылку {FRONTEND_BASE_URL}/consent/{token}
    и доставляет её кандидату по каналу (явный request_data.channel или авто email→tg→hh).
    Доставка честная: сбой канала → delivered=False (согласие всё равно создано, ссылка
    возвращается рекрутёру для ручной пересылки).
    """
    # Verify candidate exists
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    candidate = candidate_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Кандидат")

    # Название компании для текста согласия и письма (заказчик вакансии тут неизвестен —
    # согласие уровня кандидата, фолбэк на компанию-арендатора).
    company_display = await resolve_company_display_name(session, company_id, None)

    number = await _next_consent_number(session, company_id)

    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=_CONSENT_LINK_TTL_DAYS)
    consent_text = build_consent_text(candidate.full_name, company_display)

    # Канал: явный выбор рекрутёра приоритетнее, иначе авто.
    chosen_channel = request_data.channel or await _auto_consent_channel(
        session, candidate, company_id
    )

    consent = Consent(
        company_id=company_id,
        candidate_id=candidate_id,
        number=number,
        status="pending",
        channel=chosen_channel,
        token=token,
        expires_at=expires_at,
        consent_text=consent_text,
        requested_at=now,
        created_at=now,
    )
    session.add(consent)
    await session.flush()

    link = f"{settings.FRONTEND_BASE_URL}/consent/{token}"

    # Доставка ссылки. Сбой канала/недоступность НЕ роняет запрос и НЕ врёт «отправлено».
    delivered = False
    delivery_channel: str | None = None
    delivery_error: str | None = None
    if chosen_channel is None:
        delivery_error = "У кандидата нет доступного канала для доставки (email/Telegram/hh)"
    else:
        try:
            delivered, delivery_channel, delivery_error = await _deliver_consent_link(
                session,
                candidate=candidate,
                company_id=company_id,
                actor_user_id=actor_user_id,
                channel=chosen_channel,
                link=link,
                company_display=company_display,
            )
        except Exception as e:  # noqa: BLE001 — доставка не должна ронять создание согласия
            delivered = False
            delivery_channel = chosen_channel
            delivery_error = str(e)[:300]
            logger.warning(
                "[consent] доставка ссылки не удалась candidate=%s channel=%s: %s",
                candidate_id, chosen_channel, e,
            )

    # Audit
    await audit(
        session,
        action="request_consent",
        entity_type="consent",
        entity_id=consent.id,
        after={
            "number": number,
            "status": "pending",
            "channel": chosen_channel,
            "delivered": delivered,
            "delivery_channel": delivery_channel,
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()

    base = ConsentOut.model_validate(consent)
    return ConsentRequestResult(
        **base.model_dump(),
        link=link,
        delivered=delivered,
        delivery_channel=delivery_channel,
        delivery_error=delivery_error,
    )


async def sign_consent(
    session: AsyncSession,
    consent_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentOut:
    """Sign consent"""
    # Get consent
    result = await session.execute(
        select(Consent)
        .join(Candidate, Consent.candidate_id == Candidate.id)
        .where(
            Consent.id == consent_id,
            Candidate.company_id == company_id
        )
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise NotFoundError("Согласие")

    if consent.status == "signed":
        raise AlreadySignedError()

    # Update consent
    now = datetime.now(timezone.utc)
    consent.status = "signed"
    consent.signed_at = now

    # Audit
    await audit(
        session,
        action="sign_consent",
        entity_type="consent",
        entity_id=consent.id,
        before={"status": "pending"},
        after={"status": "signed", "signed_at": now.isoformat()},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return ConsentOut.model_validate(consent)


async def confirm_consent_signed_by_recruiter(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentOut:
    """Рекрутёр под свою ответственность отмечает согласие подписанным (бумага и т.п.).

    Если есть ожидающее согласие — подписывает его; если согласия нет (или отозвано) —
    создаёт уже подписанным (channel='offline'). Идемпотентно: уже подписано → вернуть как есть.
    Сообщение кандидату НЕ шлётся (в отличие от request_consent).
    """
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    candidate = candidate_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Кандидат")

    # Последнее согласие любого статуса
    result = await session.execute(
        select(Consent)
        .where(Consent.candidate_id == candidate_id)
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    # Уже подписано — идемпотентно
    if consent and consent.status == "signed":
        return ConsentOut.model_validate(consent)

    # Снимок текста для документа-доказательства (если ещё не сохранён).
    company_display = await resolve_company_display_name(session, company_id, None)
    default_text = build_consent_text(candidate.full_name, company_display)

    if consent and consent.status == "pending":
        before = {"status": "pending"}
        consent.status = "signed"
        consent.signed_at = now
        consent.signed_by = "recruiter"
        if not consent.consent_text:
            consent.consent_text = default_text
    else:
        # Нет согласия (или отозвано) — создаём уже подписанным
        number = await _next_consent_number(session, company_id)
        consent = Consent(
            company_id=company_id,
            candidate_id=candidate_id,
            number=number,
            status="signed",
            channel="offline",
            signed_at=now,
            signed_by="recruiter",
            consent_text=default_text,
            requested_at=now,
            created_at=now,
        )
        session.add(consent)
        await session.flush()
        before = None

    await audit(
        session,
        action="confirm_consent_signed",
        entity_type="consent",
        entity_id=consent.id,
        before=before,
        after={"status": "signed", "signed_at": now.isoformat(), "by": "recruiter"},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return ConsentOut.model_validate(consent)


async def sign_consent_by_candidate(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> ConsentOut:
    """Sign latest pending consent for candidate"""
    # Verify candidate exists and belongs to company
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    candidate = candidate_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Кандидат")

    # Get latest pending consent
    result = await session.execute(
        select(Consent)
        .where(
            Consent.candidate_id == candidate_id,
            Consent.status == 'pending'
        )
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise NotFoundError("Нет ожидающего подписания согласия")

    # Update consent
    now = datetime.now(timezone.utc)
    consent.status = "signed"
    consent.signed_at = now
    consent.signed_by = "candidate"

    # Audit
    await audit(
        session,
        action="sign_consent_by_candidate",
        entity_type="consent",
        entity_id=consent.id,
        before={"status": "pending"},
        after={"status": "signed", "signed_at": now.isoformat()},
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    await session.flush()
    return ConsentOut.model_validate(consent)
