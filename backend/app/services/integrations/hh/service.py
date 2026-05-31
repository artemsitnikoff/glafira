"""Сервис для работы с hh.ru интеграцией"""

import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import HhIntegration, HhOauthState, Vacancy, Application, Candidate
from ....services.settings.crypto import encrypt_text, decrypt_text
from ....services.audit import audit
from ....core.errors import ValidationError, NotFoundError
from . import client as hh_client


async def get_integration(session: AsyncSession, company_id: UUID) -> Optional[HhIntegration]:
    """Получает интеграцию hh.ru для компании"""
    result = await session.execute(
        select(HhIntegration).where(HhIntegration.company_id == company_id)
    )
    return result.scalar_one_or_none()


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
        ValidationError: при ошибке конфигурации
    """
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

    # Строим authorize URL
    authorize_url = hh_client.build_authorize_url(state)

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
        # Обмениваем код на токены
        token_data = await hh_client.exchange_code(code)

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

        # Проверяем существующую интеграцию
        existing = await get_integration(session, company_id)

        if existing:
            # Обновляем существующую
            existing.access_token = encrypted_access
            existing.refresh_token = encrypted_refresh
            existing.expires_at = expires_at
            existing.hh_employer_id = hh_employer_id
            existing.connected_by_user_id = user_id
            integration = existing
        else:
            # Создаем новую
            integration = HhIntegration(
                company_id=company_id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                hh_employer_id=hh_employer_id,
                connected_by_user_id=user_id
            )
            session.add(integration)

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
    Отключает интеграцию hh.ru

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

    integration_id = integration.id

    await session.delete(integration)
    await session.commit()

    # Записываем в аудит
    await audit(
        session,
        action="hh_disconnected",
        entity_type="hh_integration",
        entity_id=integration_id,
        actor_user_id=user_id,
        company_id=company_id
    )
    await session.commit()  # audit() после delete-commit — персистим audit-запись


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
            current_refresh = decrypt_text(integration.refresh_token)
            token_data = await hh_client.refresh_tokens(current_refresh)

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
        return {"connected": False}

    return {
        "connected": True,
        "hh_employer_id": integration.hh_employer_id,
        "connected_at": integration.created_at,
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


async def import_response(session: AsyncSession, company_id: UUID, vacancy: "Vacancy", item: dict) -> bool:
    """
    Импортирует один отклик с hh.ru

    ⚠️  Точные имена полей resume НЕ проверены без реального hh.ru токена

    Args:
        session: DB session
        company_id: ID компании
        vacancy: объект вакансии
        item: данные отклика с hh.ru

    Returns:
        bool: True если создан новый Application, False если пропущен (дедуп)
    """

    # Дедуп по hh_negotiation_id
    nid = str(item["id"])

    existing_result = await session.execute(
        select(Application).where(
            Application.hh_negotiation_id == nid,
            Application.company_id == company_id
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        return False  # Уже импортирован

    # Извлекаем данные кандидата из resume (с фолбэками)
    resume = item.get("resume", {})
    first_name = resume.get("first_name", "")
    last_name = resume.get("last_name", "")
    area_name = None
    if resume.get("area"):
        area_name = resume["area"].get("name")

    # Создаём кандидата
    candidate = Candidate(
        company_id=company_id,
        first_name=first_name or "Неизвестно",
        last_name=last_name or "",
        source="hh",
        city=area_name
    )
    session.add(candidate)
    await session.flush()  # Получаем candidate.id

    # Создаём Application
    now = datetime.now(timezone.utc)
    application = Application(
        company_id=company_id,
        candidate_id=candidate.id,
        vacancy_id=vacancy.id,
        stage="added",
        hh_negotiation_id=nid,
        created_at=now,
        selected_at=now
    )
    session.add(application)

    # Запись в аудит
    await audit(
        session,
        action="hh_response_imported",
        entity_type="application",
        entity_id=application.id,
        after={
            "candidate_name": f"{first_name} {last_name}".strip(),
            "hh_negotiation_id": nid
        },
        actor_type="system",
        company_id=company_id
    )

    return True