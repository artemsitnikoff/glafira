"""Отправка письма-оффера кандидату на этапе «Оффер».

Тело оффера генерит Глафира (LLM) из вакансии — рекрутёр правит и отправляет.
Верх (приветствие) и низ (подпись) письма — из настроек компании
(GlafiraSettings.offer_email_header/footer); пусто → дефолт из кода. Сервер —
источник правды по обрамлению: header/footer берутся из настроек, НЕ из клиента.

Письмо уходит ТОЛЬКО через брендированный шаблон (render_simple_email). Всё
динамическое экранируется html.escape перед вставкой в HTML.
"""

import asyncio
import html
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import OpenRouterNotConfiguredError, ValidationError
from ..models import Message, Vacancy
from .application import get_application
from .audit import audit
from .company_display import resolve_company_display_name
from .glafira.offer import _fallback_offer_body, generate_offer_body
from .integrations.smtp.service import send_email
from .integrations.smtp.templates import render_simple_email
from .settings.glafira import (
    get_company_llm_model,
    get_company_openrouter_key,
    get_glafira_settings,
)

logger = logging.getLogger(__name__)

OFFER_STAGE = "offer"

# Дефолты обрамления (когда в настройках компании пусто). Очистка поля в настройках
# возвращает эти значения — нейтральный профессиональный тон.
DEFAULT_OFFER_HEADER = "Здравствуйте!"
DEFAULT_OFFER_FOOTER = (
    "Будем рады видеть вас в нашей команде. "
    "Если появятся вопросы — просто ответьте на это письмо."
)

# Потолок ожидания генерации тела оффера LLM. Это ИНТЕРАКТИВНЫЙ вызов — рекрутёр ждёт
# перед открытым попапом, поэтому окно короткое: успешная генерация короткого оффера
# укладывается в несколько секунд, а при медленном/сбойном OpenRouter лучше быстро
# отдать детерминированный фолбэк-шаблон, чем крутить спиннер. (Раньше было 50с — при
# read-таймауте httpx 120с и ретраях это читалось как «висит».) Ретраи внутри окна
# остаются — они отыгрывают транзиентный сбой; не укладываемся в окно → фолбэк.
_GENERATE_TIMEOUT_SEC = 15


def _effective_header_footer(settings_obj) -> tuple[str, str]:
    """Эффективные приветствие/подпись: настройка компании либо дефолт из кода."""
    header = (settings_obj.offer_email_header or "").strip() or DEFAULT_OFFER_HEADER
    footer = (settings_obj.offer_email_footer or "").strip() or DEFAULT_OFFER_FOOTER
    return header, footer


async def _load_vacancy(session: AsyncSession, vacancy_id: UUID, company_id: UUID) -> Vacancy:
    """Вакансия заявки (company-scoped) — нужна для темы письма и фактов оффера."""
    vacancy = (
        await session.execute(
            select(Vacancy).where(
                Vacancy.id == vacancy_id,
                Vacancy.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    if vacancy is None:
        raise ValidationError("У заявки не найдена вакансия для формирования оффера")
    return vacancy


async def _resolve_offer_llm(
    session: AsyncSession, company_id: UUID
) -> tuple[str | None, str | None]:
    """Ключ + модель компании для генерации. Нет ключа → (None, model): сработает фолбэк."""
    try:
        api_key: str | None = await get_company_openrouter_key(session, company_id)
    except OpenRouterNotConfiguredError:
        api_key = None
    model = await get_company_llm_model(session, company_id)
    return api_key, model


async def build_offer_preview(
    session: AsyncSession, *, application_id: UUID, company_id: UUID
) -> dict:
    """Данные для попапа «Отправить оффер»: сгенерированное тело + эффективные header/footer.

    Ничего НЕ мутирует по бизнес-смыслу (генерация не пишет в БД) — коммит не нужен.
    header/footer отдаются read-only, чтобы фронт показал, чем сервер обрамит письмо.
    """
    application = await get_application(session, application_id, company_id)
    if application.stage != OFFER_STAGE:
        raise ValidationError("Оффер доступен только на этапе «Оффер»")
    if application.vacancy_id is None:
        raise ValidationError("У заявки не найдена вакансия для формирования оффера")

    candidate = application.candidate
    vacancy = await _load_vacancy(session, application.vacancy_id, company_id)
    company_name = await resolve_company_display_name(session, company_id, vacancy)
    api_key, model = await _resolve_offer_llm(session, company_id)

    try:
        body = await asyncio.wait_for(
            generate_offer_body(
                vacancy=vacancy,
                candidate_name=candidate.first_name,
                company_name=company_name,
                api_key=api_key,
                model=model,
            ),
            timeout=_GENERATE_TIMEOUT_SEC,
        )
    except Exception as e:  # таймаут генерации → best-effort фолбэк, не 500/502
        logger.warning("build_offer_preview: генерация тела оффера не удалась (%s), фолбэк", e)
        body = _fallback_offer_body(vacancy, candidate.first_name)

    settings_obj = await get_glafira_settings(session, company_id)
    header, footer = _effective_header_footer(settings_obj)

    return {"body": body, "header": header, "footer": footer}


async def send_offer(
    session: AsyncSession,
    *,
    application_id: UUID,
    company_id: UUID,
    actor_user_id: UUID,
    body: str,
) -> None:
    """Собрать и отправить письмо-оффер кандидату.

    Обрамление (header/footer) берётся из НАСТРОЕК компании — клиент подменить его
    не может (передаёт только тело). Отправка идёт ПЕРЕД записью Message/audit: сбой
    SMTP → ValidationError наружу, «отправлено» в карточке не появляется.
    """
    application = await get_application(session, application_id, company_id)
    if application.stage != OFFER_STAGE:
        raise ValidationError("Оффер доступен только на этапе «Оффер»")

    candidate = application.candidate
    if not candidate.email:
        raise ValidationError("У кандидата не указан email для отправки оффера")
    if application.vacancy_id is None:
        raise ValidationError("У заявки не найдена вакансия для формирования оффера")

    vacancy = await _load_vacancy(session, application.vacancy_id, company_id)
    company_name = await resolve_company_display_name(session, company_id, vacancy)

    settings_obj = await get_glafira_settings(session, company_id)
    header, footer = _effective_header_footer(settings_obj)

    full_text = f"{header}\n\n{body.strip()}\n\n{footer}"

    # Всё динамическое — экранируем ДО вставки в HTML (тело/обрамление могут содержать
    # правки рекрутёра и данные из настроек).
    safe_full = html.escape(full_text).replace("\n", "<br>")
    body_html = render_simple_email(
        heading="Предложение о работе",
        body_html=(
            f'<p style="margin:0;font-size:15px;line-height:1.6;color:#1A1F29;">{safe_full}</p>'
        ),
        preheader=(
            f"Предложение о работе — {company_name}" if company_name else "Предложение о работе"
        ),
        company_name=company_name,
    )
    subject = f"Оффер по вакансии «{vacancy.name}»" + (
        f" — {company_name}" if company_name else ""
    )

    # send_email кидает ValidationError, если SMTP не настроен → пусть дойдёт до клиента
    # честной 400, а не превратится в фейковое «отправлено».
    await send_email(
        session,
        company_id,
        to=candidate.email,
        subject=subject,
        body_text=full_text,
        body_html=body_html,
    )

    now = datetime.now(timezone.utc)
    # Оффер виден в табе «Чат» карточки как исходящее письмо. Тело — полный текст письма
    # (то, что реально ушло кандидату).
    session.add(
        Message(
            company_id=company_id,
            candidate_id=application.candidate_id,
            application_id=application.id,
            channel="email",
            direction="out",
            sender_type="recruiter",
            sender_user_id=actor_user_id,
            body=full_text,
            sent_at=now,
            created_at=now,
        )
    )

    # §2.2: каждое изменяющее действие → audit_log. PII (email/тело) НЕ кладём.
    await audit(
        session,
        action="send_offer",
        entity_type="application",
        entity_id=application.id,
        before=None,
        after={"channel": "email", "to_present": True},
        actor_user_id=actor_user_id,
        company_id=company_id,
        actor_type="human",
    )
