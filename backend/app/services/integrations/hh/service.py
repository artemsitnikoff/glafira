"""Сервис для работы с hh.ru интеграцией"""

import secrets
from datetime import datetime, timezone, timedelta, date
from uuid import UUID
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import (
    HhIntegration, HhOauthState, Vacancy, Application, Candidate,
    CandidateExperience, CandidateSkill, CandidateEducation, Message,
)
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....services.chat_log import log_chat
from ....core.errors import ValidationError, NotFoundError
from . import client as hh_client

import logging

logger = logging.getLogger(__name__)


def _hh_phone(contacts) -> Optional[str]:
    """Телефон из контактов hh-резюме (если hh их не скрыл)."""
    for c in contacts or []:
        if (c.get("type") or {}).get("id") in ("cell", "home", "work"):
            v = c.get("value")
            if isinstance(v, dict):
                return v.get("formatted") or v.get("number")
            if isinstance(v, str):
                return v
    return None


def _hh_email(contacts) -> Optional[str]:
    """Email из контактов hh-резюме (если не скрыт)."""
    for c in contacts or []:
        if (c.get("type") or {}).get("id") == "email":
            v = c.get("value")
            if isinstance(v, str):
                return v
    return None


def _hh_period(start, end) -> Optional[str]:
    """Период работы строкой из start/end (формат hh 'YYYY-MM-DD' | None)."""
    if not start and not end:
        return None
    s = (start or "")[:7] if start else "?"
    e = (end or "")[:7] if end else "по наст. время"
    return f"{s} — {e}"


async def get_integration(session: AsyncSession, company_id: UUID) -> Optional[HhIntegration]:
    """Получает интеграцию hh.ru для компании"""
    result = await session.execute(
        select(HhIntegration).where(HhIntegration.company_id == company_id)
    )
    return result.scalar_one_or_none()


async def save_config(session: AsyncSession, company_id: UUID, user_id: UUID, client_id: str, client_secret: str, redirect_uri: str) -> HhIntegration:
    """
    Сохраняет конфигурацию hh.ru для компании

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя
        client_id: ID приложения hh.ru
        client_secret: секрет приложения hh.ru
        redirect_uri: redirect URI приложения hh.ru

    Returns:
        HhIntegration: созданная/обновленная интеграция

    Raises:
        ValidationError: при пустых credentials
    """
    # Валидация
    if not client_id or not client_secret or not redirect_uri:
        raise ValidationError("Все поля обязательны: client_id, client_secret, redirect_uri")

    # Проверяем существующую интеграцию
    existing = await get_integration(session, company_id)

    # Шифруем client_secret
    encrypted_secret = encrypt_text(client_secret)

    if existing:
        # Обновляем существующую конфигурацию
        old_client_id = existing.client_id
        existing.client_id = client_id
        existing.client_secret = encrypted_secret
        existing.redirect_uri = redirect_uri

        # Если client_id изменился, обнуляем токены (токены от другого приложения)
        if old_client_id != client_id:
            existing.access_token = None
            existing.refresh_token = None
            existing.expires_at = None
            existing.hh_employer_id = None

        integration = existing
    else:
        # Создаем новую
        integration = HhIntegration(
            company_id=company_id,
            client_id=client_id,
            client_secret=encrypted_secret,
            redirect_uri=redirect_uri
        )
        session.add(integration)

    await session.commit()

    # Записываем в аудит
    await audit(
        session,
        action="hh_config_saved",
        entity_type="hh_integration",
        entity_id=integration.id,
        after={
            "client_id": client_id,
            "redirect_uri": redirect_uri
        },
        actor_user_id=user_id,
        company_id=company_id
    )
    await session.commit()

    return integration


async def start_oauth(session: AsyncSession, company_id: UUID, user_id: UUID) -> str:
    """
    Начинает OAuth flow, создает state запись и возвращает authorize URL

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя

    Returns:
        str: URL для редиректа в браузер

    Raises:
        ValidationError: при отсутствии конфигурации
    """
    # Читаем конфигурацию из БД
    integration = await get_integration(session, company_id)
    if not integration or not integration.client_id or not integration.redirect_uri:
        raise ValidationError("Сначала сохраните настройки hh.ru")

    # Генерируем уникальный state
    state = secrets.token_urlsafe(32)

    # Создаем запись state (expires через 10 минут)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    oauth_state = HhOauthState(
        state=state,
        company_id=company_id,
        user_id=user_id,
        expires_at=expires_at
    )

    session.add(oauth_state)
    await session.commit()

    # Строим authorize URL с client_id и redirect_uri из БД
    authorize_url = hh_client.build_authorize_url(state, integration.client_id, integration.redirect_uri)

    return authorize_url


async def complete_oauth(session: AsyncSession, code: str, state: str) -> HhIntegration:
    """
    Завершает OAuth flow, обменивает код на токены и создает/обновляет интеграцию

    Args:
        session: DB session
        code: authorization code от hh.ru
        state: state для проверки CSRF

    Returns:
        HhIntegration: созданная/обновленная интеграция

    Raises:
        ValidationError: при невалидном state или ошибке API
    """
    # Находим state запись
    result = await session.execute(
        select(HhOauthState).where(HhOauthState.state == state)
    )
    oauth_state = result.scalar_one_or_none()

    if not oauth_state:
        raise ValidationError("Невалидный или истекший state")

    # Проверяем срок действия
    if datetime.now(timezone.utc) > oauth_state.expires_at:
        # Удаляем истекший state
        await session.delete(oauth_state)
        await session.commit()
        raise ValidationError("Истекший state")

    company_id = oauth_state.company_id
    user_id = oauth_state.user_id

    try:
        # Читаем конфигурацию из БД
        integration_config = await get_integration(session, company_id)
        if not integration_config or not integration_config.client_id or not integration_config.client_secret or not integration_config.redirect_uri:
            raise ValidationError("Конфигурация hh.ru не найдена")

        # Расшифровываем client_secret
        client_secret = decrypt_text(integration_config.client_secret)

        # Обмениваем код на токены с credentials из БД
        token_data = await hh_client.exchange_code(
            code,
            integration_config.client_id,
            client_secret,
            integration_config.redirect_uri
        )

        # Получаем информацию о пользователе
        me_data = await hh_client.get_me(token_data["access_token"])

        # Извлекаем employer_id
        hh_employer_id = None
        if "employer" in me_data and me_data["employer"] and "id" in me_data["employer"]:
            hh_employer_id = str(me_data["employer"]["id"])

        # Вычисляем время истечения токена
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

        # Шифруем токены
        encrypted_access = encrypt_text(token_data["access_token"])
        encrypted_refresh = encrypt_text(token_data["refresh_token"])

        # Используем существующую интеграцию (которая уже есть с конфигом)
        if integration_config:
            # Обновляем существующую (токены + employer_id)
            integration_config.access_token = encrypted_access
            integration_config.refresh_token = encrypted_refresh
            integration_config.expires_at = expires_at
            integration_config.hh_employer_id = hh_employer_id
            integration_config.connected_by_user_id = user_id
            integration = integration_config
        else:
            # Не должно происходить, так как мы проверили выше
            raise ValidationError("Конфигурация hh.ru исчезла во время OAuth")

        # Удаляем использованный state
        await session.delete(oauth_state)

        # Сохраняем изменения
        await session.commit()

        # Записываем в аудит
        if user_id:
            await audit(
                session,
                action="hh_connected",
                entity_type="hh_integration",
                entity_id=integration.id,
                after={"hh_employer_id": hh_employer_id},
                actor_user_id=user_id,
                company_id=company_id
            )
            await session.commit()  # audit() добавляет запись после основного commit — персистим её

        return integration

    except Exception as e:
        # Удаляем state при ошибке
        await session.delete(oauth_state)
        await session.commit()
        raise


async def disconnect(session: AsyncSession, company_id: UUID, user_id: UUID):
    """
    Отключает интеграцию hh.ru (обнуляет токены, оставляет config)

    Args:
        session: DB session
        company_id: ID компании
        user_id: ID пользователя

    Raises:
        NotFoundError: если интеграция не найдена
    """
    integration = await get_integration(session, company_id)

    if not integration:
        raise NotFoundError("Интеграция hh.ru не найдена")

    # Обнуляем токены и employer_id, но оставляем config (client_id, client_secret, redirect_uri)
    integration.access_token = None
    integration.refresh_token = None
    integration.expires_at = None
    integration.hh_employer_id = None

    await session.commit()

    # Записываем в аудит
    await audit(
        session,
        action="hh_disconnected",
        entity_type="hh_integration",
        entity_id=integration.id,
        actor_user_id=user_id,
        company_id=company_id
    )
    await session.commit()  # audit() после обновления — персистим audit-запись


async def get_valid_access_token(session: AsyncSession, company_id: UUID) -> str:
    """
    Получает валидный access token, обновляя при необходимости

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        str: валидный access token

    Raises:
        NotFoundError: если интеграция не найдена
        ValidationError: при ошибке обновления токенов
    """
    integration = await get_integration(session, company_id)

    if not integration:
        raise NotFoundError("Интеграция hh.ru не найдена")

    # Проверяем срок действия токена (с запасом 5 минут)
    now = datetime.now(timezone.utc)
    expires_soon = integration.expires_at - timedelta(minutes=5)

    if now >= expires_soon:
        # Токен истек или истечет скоро, обновляем
        try:
            # Проверяем что у нас есть client credentials для refresh
            if not integration.client_id or not integration.client_secret:
                raise ValidationError("Отсутствуют client credentials для обновления токенов")

            current_refresh = decrypt_text(integration.refresh_token)
            client_secret = decrypt_text(integration.client_secret)

            token_data = await hh_client.refresh_tokens(
                current_refresh,
                integration.client_id,
                client_secret
            )

            # Обновляем токены
            integration.access_token = encrypt_text(token_data["access_token"])
            integration.refresh_token = encrypt_text(token_data["refresh_token"])
            integration.expires_at = now + timedelta(seconds=token_data["expires_in"])

            await session.commit()

            return token_data["access_token"]

        except Exception as e:
            raise ValidationError(f"Не удалось обновить токены hh.ru: {e}")

    else:
        # Токен еще валидный
        return decrypt_text(integration.access_token)


async def get_status(session: AsyncSession, company_id: UUID) -> dict:
    """
    Получает статус интеграции hh.ru

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        dict: статус интеграции
    """
    integration = await get_integration(session, company_id)

    if not integration:
        return {
            "configured": False,
            "connected": False,
            "redirect_uri": None,
            "client_id_masked": None,
            "hh_employer_id": None,
            "expires_at": None
        }

    # Проверяем что конфигурация сохранена
    configured = bool(integration.client_id)

    # Проверяем что есть валидные токены
    connected = bool(integration.access_token)

    # Маскируем client_id
    client_id_masked = None
    if integration.client_id:
        if len(integration.client_id) > 4:
            client_id_masked = "••••" + integration.client_id[-4:]
        else:
            client_id_masked = "••••"

    return {
        "configured": configured,
        "connected": connected,
        "redirect_uri": integration.redirect_uri,
        "client_id_masked": client_id_masked,
        "hh_employer_id": integration.hh_employer_id,
        "expires_at": integration.expires_at
    }


async def list_hh_vacancies(session: AsyncSession, company_id: UUID) -> list[dict]:
    """
    Получает список вакансий с hh.ru

    Args:
        session: DB session
        company_id: ID компании

    Returns:
        list: упрощённый список вакансий [{id, name, area}, ...]

    Raises:
        ValidationError: если hh не подключён или ошибка API
    """
    integration = await get_integration(session, company_id)
    if not integration:
        raise ValidationError("Интеграция hh.ru не подключена")

    if not integration.hh_employer_id:
        raise ValidationError("Отсутствует hh_employer_id в интеграции")

    access_token = await get_valid_access_token(session, company_id)

    # Получаем все страницы (начинаем с первой)
    all_items = []
    page = 0

    while True:
        data = await hh_client.get_employer_vacancies(
            access_token, integration.hh_employer_id, page=page, per_page=50
        )

        items = data.get("items", [])
        if not items:
            break

        all_items.extend(items)

        # Проверяем, есть ли ещё страницы
        if page >= data.get("pages", 1) - 1:
            break

        page += 1

    # Возвращаем упрощённый список
    result = []
    for item in all_items:
        result.append({
            "id": str(item["id"]),
            "name": item.get("name", ""),
            "area": item.get("area", {}).get("name") if item.get("area") else None
        })

    return result


async def link_vacancy(session: AsyncSession, vacancy_id: UUID, hh_vacancy_id: str, company_id: UUID, user_id: UUID):
    """
    Привязывает вакансию Глафиры к вакансии hh.ru

    Args:
        session: DB session
        vacancy_id: ID вакансии в Глафире
        hh_vacancy_id: ID вакансии на hh.ru
        company_id: ID компании
        user_id: ID пользователя

    Raises:
        NotFoundError: если вакансия не найдена
        ValidationError: при ошибках валидации
    """
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id
        )
    )
    vacancy = result.scalar_one_or_none()

    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    vacancy.hh_vacancy_id = hh_vacancy_id

    # Запись в аудит
    await audit(
        session,
        action="hh_vacancy_linked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"hh_vacancy_id": hh_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id
    )


async def unlink_vacancy(session: AsyncSession, vacancy_id: UUID, company_id: UUID, user_id: UUID):
    """
    Отвязывает вакансию Глафиры от hh.ru

    Args:
        session: DB session
        vacancy_id: ID вакансии в Глафире
        company_id: ID компании
        user_id: ID пользователя

    Raises:
        NotFoundError: если вакансия не найдена
    """
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id
        )
    )
    vacancy = result.scalar_one_or_none()

    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    old_hh_vacancy_id = vacancy.hh_vacancy_id
    vacancy.hh_vacancy_id = None

    # Запись в аудит
    await audit(
        session,
        action="hh_vacancy_unlinked",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"hh_vacancy_id": None},
        before={"hh_vacancy_id": old_hh_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id
    )


async def publish_vacancy_to_hh(session: AsyncSession, vacancy_id: UUID, company_id: UUID, user_id: UUID) -> str:
    """
    Публикует вакансию Глафиры на hh.ru

    ⚠️  НЕ проверено без реального токена hh.ru
    ⚠️  Требует маппинга города → hh area_id (TODO)

    Args:
        session: DB session
        vacancy_id: ID вакансии в Глафире
        company_id: ID компании
        user_id: ID пользователя

    Returns:
        str: hh_vacancy_id созданной вакансии

    Raises:
        NotFoundError: если вакансия не найдена
        ValidationError: при ошибках валидации или отсутствии маппинга
    """
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id,
            Vacancy.company_id == company_id
        )
    )
    vacancy = result.scalar_one_or_none()

    if not vacancy:
        raise NotFoundError("Вакансия не найдена")

    access_token = await get_valid_access_token(session, company_id)

    # Собираем payload из данных вакансии
    payload = {
        "name": vacancy.name,
        "description": vacancy.description or "",
    }

    # Зарплата
    if vacancy.salary_from or vacancy.salary_to:
        salary = {}
        if vacancy.salary_from:
            salary["from"] = vacancy.salary_from
        if vacancy.salary_to:
            salary["to"] = vacancy.salary_to
        salary["currency"] = vacancy.currency
        payload["salary"] = salary

    # Город (требует маппинга)
    if vacancy.city:
        # TODO: маппинг город → hh area_id
        raise ValidationError(f"Требуется маппинг города '{vacancy.city}' в hh area_id")

    # TODO: обязательные поля hh.ru (type, professional_roles, employment, schedule)
    # Точный состав зависит от менеджера/региона и не проверен без реального токена

    # Публикуем вакансию
    result = await hh_client.publish_vacancy(access_token, payload)

    hh_vacancy_id = str(result.get("id"))
    if not hh_vacancy_id:
        raise ValidationError("hh.ru не вернул id созданной вакансии")

    # Сохраняем связь
    vacancy.hh_vacancy_id = hh_vacancy_id

    # Запись в аудит
    await audit(
        session,
        action="hh_vacancy_published",
        entity_type="vacancy",
        entity_id=vacancy_id,
        after={"hh_vacancy_id": hh_vacancy_id},
        actor_user_id=user_id,
        company_id=company_id
    )

    return hh_vacancy_id


async def import_response(session: AsyncSession, company_id: UUID, vacancy: "Vacancy", item: dict, access_token: str = None) -> str:
    """Импорт ИЛИ обновление одного отклика hh. Возвращает 'created' | 'updated'.

    Существующий (по hh_negotiation_id) НЕ пропускается — обновляем данные кандидата
    и пересоздаём опыт/навыки/образование. Этап существующей заявки НЕ трогаем.
    Краткое резюме из списка откликов УРЕЗАНО — догружаем ПОЛНОЕ по resume.url
    (опыт с описанием, возраст, образование, контакты — если hh их открыл).
    """
    nid = str(item["id"])

    # --- Полное резюме (догрузка по url; краткое из списка откликов неполное) ---
    resume = item.get("resume") or {}
    resume_url = resume.get("url")
    if access_token and resume_url:
        try:
            full = await hh_client.get_resume(access_token, resume_url)
            if isinstance(full, dict):
                resume = full
        except Exception:
            pass  # нет доступа к полному резюме — остаёмся на кратком

    # --- Маппинг резюме hh → поля кандидата ---
    first_name = (resume.get("first_name") or "").strip()
    last_name = (resume.get("last_name") or "").strip()
    middle_name = (resume.get("middle_name") or "").strip() or None
    title = (resume.get("title") or "").strip() or None
    city = (resume.get("area") or {}).get("name")
    gender = (resume.get("gender") or {}).get("id")  # 'male' | 'female'

    # Возраст → birth_date (hh даёт birth_date 'YYYY-MM-DD' или age числом)
    birth_date = None
    bd = resume.get("birth_date")
    if bd:
        try:
            birth_date = date.fromisoformat(str(bd)[:10])
        except (ValueError, TypeError):
            birth_date = None
    elif isinstance(resume.get("age"), int):
        try:
            birth_date = date(date.today().year - resume["age"], 1, 1)
        except (ValueError, TypeError):
            birth_date = None

    salary = resume.get("salary") or {}
    salary_amount = salary.get("amount")
    salary_currency = salary.get("currency") or "RUB"
    if salary_currency == "RUR":
        salary_currency = "RUB"

    phone = _hh_phone(resume.get("contact"))
    email = _hh_email(resume.get("contact"))

    experiences = resume.get("experience") or []
    last_position, last_company, last_period = title, None, None
    if experiences:
        e0 = experiences[0]
        last_position = (e0.get("position") or title)
        last_company = e0.get("company")
        last_period = _hh_period(e0.get("start"), e0.get("end"))

    rt_parts = []
    if title:
        rt_parts.append(f"Желаемая должность: {title}")
    if resume.get("skills"):
        rt_parts.append(str(resume.get("skills")))
    resume_text = "\n\n".join(rt_parts) or None
    resume_id = (str(resume.get("id"))[:120] if resume.get("id") else None)

    state_id = (item.get("state") or {}).get("id") or "response"
    # Любая коллекция discard_* (by_employer/by_applicant/no_interaction/
    # vacancy_closed/to_other_vacancy) — это завершённый/отклонённый отклик → «Отказ».
    stage = "rejected" if str(state_id).startswith("discard") else "response"

    # --- Существующая заявка? (create-or-update) ---
    existing = (await session.execute(
        select(Application).where(
            Application.hh_negotiation_id == nid,
            Application.company_id == company_id,
        )
    )).scalar_one_or_none()

    if existing:
        candidate = await session.get(Candidate, existing.candidate_id)
        is_new = candidate is None
        if candidate is None:
            candidate = Candidate(company_id=company_id, source="hh", first_name="Неизвестно", last_name="")
            session.add(candidate)
    else:
        candidate = Candidate(company_id=company_id, source="hh", first_name="Неизвестно", last_name="")
        session.add(candidate)
        is_new = True

    # Заполняем поля (непустым значением — не затираем уже заполненное пустым)
    candidate.first_name = first_name or candidate.first_name or "Неизвестно"
    candidate.last_name = last_name or candidate.last_name or ""
    if middle_name:
        candidate.middle_name = middle_name
    if city:
        candidate.city = city[:120]
    if gender:
        candidate.gender = gender[:10]
    if birth_date:
        candidate.birth_date = birth_date
    if phone:
        candidate.phone = phone[:20]
    if email:
        candidate.email = email[:255]
    if isinstance(salary_amount, int):
        candidate.salary_expectation = salary_amount
    if salary_currency:
        candidate.currency = str(salary_currency)[:3]
    if last_position:
        candidate.last_position = last_position[:255]
    if last_company:
        candidate.last_company = last_company[:255]
    if last_period:
        candidate.last_period = last_period[:120]
    if resume_text:
        candidate.resume_text = resume_text
    candidate.source = "hh"
    candidate.external_source = "hh"
    if resume_id:
        candidate.external_id = resume_id
    await session.flush()

    # Опыт/навыки/образование: при обновлении заменяем старые (от прежнего импорта)
    if not is_new:
        await session.execute(delete(CandidateExperience).where(CandidateExperience.candidate_id == candidate.id))
        await session.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id))
        await session.execute(delete(CandidateEducation).where(CandidateEducation.candidate_id == candidate.id))

    for idx, exp in enumerate(experiences):
        pos = (exp.get("position") or "").strip()
        if not pos:
            continue
        session.add(CandidateExperience(
            company_id=company_id, candidate_id=candidate.id, position=pos[:255],
            company=((exp.get("company") or "")[:255] or None),
            period=_hh_period(exp.get("start"), exp.get("end")),
            description=(exp.get("description") or None), order_index=idx,
        ))
    for idx, sk in enumerate(resume.get("skill_set") or []):
        s = str(sk).strip()
        if s:
            session.add(CandidateSkill(
                company_id=company_id, candidate_id=candidate.id, skill=s[:120], order_index=idx,
            ))
    for idx, ed in enumerate((resume.get("education") or {}).get("primary") or []):
        inst = (ed.get("name") or ed.get("organization") or "").strip()
        if not inst:
            continue
        session.add(CandidateEducation(
            company_id=company_id, candidate_id=candidate.id, institution=inst[:255],
            specialty=((ed.get("organization") or ed.get("result") or "")[:255] or None),
            years=(str(ed.get("year"))[:40] if ed.get("year") else None), order_index=idx,
        ))

    # Заявка: создать (этап по hh) или оставить как есть (этап не трогаем)
    now = datetime.now(timezone.utc)
    chat_id_str = str(item.get("chat_id")) if item.get("chat_id") is not None else None

    if existing is None:
        application = Application(
            company_id=company_id, candidate_id=candidate.id, vacancy_id=vacancy.id,
            stage=stage, hh_negotiation_id=nid, hh_chat_id=chat_id_str,
            # Импортирован из discard-коллекции = УЖЕ отклонён на hh → сразу synced,
            # чтобы cron не пытался повторно отклонять (вернёт wrong_state).
            hh_discard_synced_at=(now if stage == "rejected" else None),
            created_at=now, selected_at=now,
        )
        session.add(application)
    else:
        application = existing
    await session.flush()

    await audit(
        session,
        action=("hh_response_imported" if existing is None else "hh_response_updated"),
        entity_type="application",
        entity_id=application.id,
        after={"candidate_name": f"{first_name} {last_name}".strip(), "hh_negotiation_id": nid, "stage": stage},
        actor_type="system",
        company_id=company_id,
    )

    return "created" if existing is None else "updated"


async def poll_responses_now(session: AsyncSession, company_id: UUID) -> dict:
    """Ручной забор откликов с hh.ru для привязанных АКТИВНЫХ вакансий компании.

    Тот же импорт, что cron-джоб poll_hh_responses, но по запросу из UI (мгновенно).
    Требует подключённого hh + ПЛАТНОГО доступа работодателя (negotiations).
    """
    integration = await get_integration(session, company_id)
    if not integration or not integration.hh_employer_id:
        raise ValidationError("hh.ru не подключён")

    access_token = await get_valid_access_token(session, company_id)

    # По кнопке опрашиваем ВСЕ привязанные вакансии (любой ATS-статус): hh-публикация
    # может быть активна, даже если вакансия в ATS закрыта/в архиве — отклики всё
    # равно нужно забрать. (Авто-cron — только active, чтобы не дёргать лишнее.)
    result = await session.execute(
        select(Vacancy).where(
            Vacancy.company_id == company_id,
            Vacancy.hh_vacancy_id.isnot(None),
        )
    )
    vacancies = result.scalars().all()

    # Инкрементально: полное резюме (дорогой GET по url) тянем ТОЛЬКО для НОВЫХ
    # откликов. Заранее берём set уже импортированных hh_negotiation_id компании —
    # известные пропускаем без фетча резюме. Это и есть «грузить только новых»
    # (раньше резюме передёргивалось по каждому отклику каждый прогон).
    existing_rows = await session.execute(
        select(Application.hh_negotiation_id).where(
            Application.company_id == company_id,
            Application.hh_negotiation_id.isnot(None),
        )
    )
    existing_nids = {str(r[0]) for r in existing_rows if r[0] is not None}

    # Диагностику возвращаем В ОТВЕТЕ (а не в логи — кастомный logger.info может не
    # выводиться в docker logs, если root-логгер не на INFO). По каждой вакансии:
    # сколько откликов вернул hh (found), сколько импортировано, и ошибка hh если была.
    # Забираем коллекции «Отклик» (неразобранные → этап «Отклик») и «Отказ»
    # (отклонённые на hh → этап «Отказ»). Этап для каждого item определяет
    # import_response по item.state.id.
    # Забираем «Отклик» (неразобранные) + все коллекции отказа hh. consider/
    # phone_interview/interview/offer/hired НЕ трогаем (это уже продвинутые на hh —
    # их этап на нашей стороне определяет рекрутёр, не импорт).
    wanted = (
        "response",
        "discard_by_employer", "discard_by_applicant", "discard_no_interaction",
        "discard_vacancy_closed", "discard_to_other_vacancy",
    )

    stats = {"imported": 0, "updated": 0, "skipped": 0, "vacancies": len(vacancies), "details": []}
    for vacancy in vacancies:
        vstat = {
            "name": vacancy.name,
            "status": vacancy.status,
            "hh_id": vacancy.hh_vacancy_id,
            "found": 0,
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "by_collection": {},
            "all_collections": {},
            "error": None,
        }
        try:
            collections = await hh_client.get_negotiation_collections(access_token, vacancy.hh_vacancy_id)
            # Диагностика: ВСЕ коллекции hh (id→count) — чтобы увидеть, как называется
            # коллекция «Отказ» (она может быть не 'discard').
            vstat["all_collections"] = {str(c.get("id")): c.get("count") for c in collections}
            for coll in collections:
                cid = coll.get("id")
                if cid not in wanted:
                    continue
                url = coll.get("url")
                if not url:
                    vstat["by_collection"][cid] = coll.get("count") or 0
                    continue
                coll_found = None
                page = 0
                while True:
                    data = await hh_client.get_collection_page(access_token, url, page=page, per_page=50)
                    if coll_found is None:
                        # реальное число откликов коллекции (а не coll.count, которого может не быть)
                        coll_found = data.get("found")
                        if coll_found is None:
                            coll_found = coll.get("count")
                        vstat["by_collection"][cid] = coll_found or 0
                        vstat["found"] += coll_found or 0
                    items = data.get("items", []) or []
                    if not items:
                        break
                    # Собираем map hh_negotiation_id → chat_id для бэкфилла существующих
                    nid_to_chat_id = {}
                    for item in items:
                        nid = str(item.get("id"))
                        chat_id = item.get("chat_id")
                        if nid and chat_id is not None:
                            nid_to_chat_id[nid] = str(chat_id)

                    # Бэкфилл chat_id для существующих Applications с пустым hh_chat_id
                    if nid_to_chat_id:
                        existing_apps_result = await session.execute(
                            select(Application).where(
                                Application.company_id == company_id,
                                Application.hh_negotiation_id.in_(list(nid_to_chat_id.keys())),
                                Application.hh_chat_id.is_(None)
                            )
                        )
                        existing_apps = existing_apps_result.scalars().all()
                        for app in existing_apps:
                            if app.hh_negotiation_id in nid_to_chat_id:
                                app.hh_chat_id = nid_to_chat_id[app.hh_negotiation_id]

                    for item in items:
                        nid = str(item.get("id"))
                        # Уже импортирован → пропускаем БЕЗ фетча резюме (только новые грузим).
                        if nid in existing_nids:
                            stats["skipped"] += 1
                            vstat["skipped"] += 1
                            continue
                        try:
                            res = await import_response(session, company_id, vacancy, item, access_token=access_token)
                            if res == "created":
                                stats["imported"] += 1
                                vstat["imported"] += 1
                                existing_nids.add(nid)
                            elif res == "updated":
                                stats["updated"] += 1
                                vstat["updated"] += 1
                            else:
                                stats["skipped"] += 1
                        except Exception:
                            stats["skipped"] += 1
                    if page >= (data.get("pages", 1) or 1) - 1:
                        break
                    page += 1
        except Exception as e:
            vstat["error"] = getattr(e, "message", None) or str(e)
        stats["details"].append(vstat)

    return stats


# Константа вежливого текста отказа
POLITE_REJECTION_TEXT = (
    "Здравствуйте! Благодарим за интерес к нашей вакансии и время, уделённое отклику. "
    "К сожалению, по итогам рассмотрения мы приняли решение не продолжать общение по этой позиции. "
    "Это не оценка вас как специалиста — на данном этапе мы остановились на другой кандидатуре. "
    "Желаем успехов в поиске работы и будем рады видеть ваш отклик на наши будущие вакансии!"
)


async def sync_company_rejections(session: AsyncSession, company_id: UUID, limit: int = 20) -> dict:
    """
    Синхронизирует отказы hh-кандидатов: отклоняет на hh.ru + отправляет вежливое сообщение

    Обрабатывает Applications со stage='rejected', у которых есть hh_negotiation_id
    и ещё не установлен флаг hh_discard_synced_at (не синхронизированы с hh).

    Args:
        session: DB session
        company_id: ID компании
        limit: максимальное количество отказов за проход (по умолчанию 20)

    Returns:
        dict: статистика {discarded, failed, skipped_no_token}

    Raises:
        NotFoundError: если интеграция hh.ru не найдена
    """
    stats = {"discarded": 0, "already_discarded": 0, "failed": 0, "skipped_no_token": 0}

    try:
        # Проверяем доступность токена
        access_token = await get_valid_access_token(session, company_id)
    except (NotFoundError, ValidationError):
        logger.warning(f"Компания {company_id}: нет валидного токена hh.ru для синхронизации отказов")
        stats["skipped_no_token"] = -1  # Индикатор отсутствия токена
        return stats

    # Выбираем hh-кандидатов, которых отклонили, но ещё не синхронизировали с hh
    stmt = (
        select(Application, Candidate)
        .join(Candidate)
        .where(
            Application.company_id == company_id,
            Application.stage == "rejected",
            Application.hh_negotiation_id.isnot(None),
            Application.hh_discard_synced_at.is_(None),
            Candidate.deleted_at.is_(None)
        )
        .limit(limit)
    )

    result = await session.execute(stmt)
    applications_with_candidates = result.fetchall()

    logger.info(f"Компания {company_id}: найдено {len(applications_with_candidates)} отклонённых hh-кандидатов для синхронизации")

    for app, candidate in applications_with_candidates:
        try:
            # 1. Резолв chat_id (лениво, если не установлен)
            chat_id = app.hh_chat_id
            if not chat_id:
                try:
                    nego_data = await hh_client.get_negotiation(access_token, app.hh_negotiation_id)
                    chat_id = nego_data.get("chat_id")
                    if chat_id:
                        app.hh_chat_id = chat_id
                        await session.flush()  # Сохраним chat_id сразу
                except Exception as e:
                    logger.warning(f"Не удалось получить chat_id для отклика {app.hh_negotiation_id}: {e}")

            # 2. Отклоняем на hh.ru
            try:
                discarded_now = await hh_client.discard_negotiation(access_token, app.hh_negotiation_id)
            except Exception as e:
                # Транзиентная ошибка (нет прав/сеть) — НЕ помечаем synced, ретрай.
                log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard НЕ выполнен: {e}")
                stats["failed"] += 1
                logger.error(f"Ошибка отказа hh отклика {app.hh_negotiation_id}: {e}")
                continue

            # Помечаем synced в любом случае (discarded_now True ИЛИ False=уже в отказе):
            # повторять не нужно.
            app.hh_discard_synced_at = datetime.now(timezone.utc)
            await session.flush()

            # Отклик уже был в отказе на hh (wrong_state, обычно импортирован из
            # discard-коллекции) → сообщение НЕ шлём (кандидат уже отклонён).
            if not discarded_now:
                await session.commit()
                log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • уже в отказе на hh (синк не требуется)")
                stats["already_discarded"] += 1
                continue

            # 3. Отправляем вежливое сообщение (best-effort) — только тем, кого
            #    реально отклонили сейчас.
            message_sent = False
            if chat_id:
                try:
                    msg_response = await hh_client.send_chat_message(
                        access_token,
                        chat_id,
                        POLITE_REJECTION_TEXT
                    )

                    # Сохраняем исходящее сообщение
                    message = Message(
                        company_id=company_id,
                        candidate_id=candidate.id,
                        application_id=app.id,
                        channel="hh",
                        direction="out",
                        sender_type="ai",
                        sender_user_id=None,
                        body=POLITE_REJECTION_TEXT,
                        sent_at=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                        external_id=str(msg_response.get("id", ""))
                    )
                    session.add(message)
                    message_sent = True

                except Exception as e:
                    # Ошибка отправки сообщения не откатывает discard
                    logger.warning(f"Не удалось отправить сообщение отказа в чат {chat_id}: {e}")

            # 4. Коммитим каждую application отдельно
            await session.commit()

            # Логируем результат
            if message_sent:
                log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard + вежливое сообщение отправлено")
            else:
                log_chat(f"АВТО-ОТКАЗ hh → {candidate.full_name} • discard выполнен, сообщение не отправлено")

            stats["discarded"] += 1

        except Exception as e:
            # Откат транзакции для этой application
            await session.rollback()
            stats["failed"] += 1
            logger.error(f"Критическая ошибка синхронизации отказа application {app.id}: {e}")
            continue

    logger.info(
        f"Компания {company_id}: синхронизация отказов завершена. "
        f"Успешно: {stats['discarded']}, Неудачно: {stats['failed']}"
    )

    return stats