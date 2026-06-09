"""hh.ru API клиент для OAuth и API вызовов"""

import logging
import uuid

import httpx
from urllib.parse import urlencode

from ....config import settings
from ....core.errors import ValidationError

logger = logging.getLogger(__name__)


def _get_client() -> httpx.AsyncClient:
    """Создает async HTTP клиент с таймаутами и User-Agent"""
    timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0
    )

    headers = {
        "User-Agent": settings.HH_USER_AGENT
    }

    return httpx.AsyncClient(timeout=timeout, headers=headers)


def _check_credentials(client_id: str, client_secret: str, redirect_uri: str):
    """Проверяет переданные credentials"""
    if not client_id:
        raise ValidationError("hh.ru не настроен: отсутствует client_id")
    if not client_secret:
        raise ValidationError("hh.ru не настроен: отсутствует client_secret")
    if not redirect_uri:
        raise ValidationError("hh.ru не настроен: отсутствует redirect_uri")


async def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    """
    Обменивает authorization_code на токены

    Args:
        code: authorization code от hh.ru
        client_id: ID приложения hh.ru
        client_secret: секрет приложения hh.ru
        redirect_uri: redirect URI приложения hh.ru

    Returns:
        dict: {access_token, refresh_token, token_type, expires_in}

    Raises:
        ValidationError: при ошибке API или валидации
    """
    _check_credentials(client_id, client_secret, redirect_uri)

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri
    }

    async with _get_client() as client:
        try:
            response = await client.post(
                settings.HH_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            result = response.json()

            # Проверяем обязательные поля в ответе
            required_fields = ["access_token", "refresh_token", "token_type", "expires_in"]
            for field in required_fields:
                if field not in result:
                    raise ValidationError(f"Ответ hh.ru не содержит поле {field}")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка обмена кода hh.ru: {e}")


async def refresh_tokens(refresh_token: str, client_id: str, client_secret: str) -> dict:
    """
    Обновляет токены через refresh_token

    Args:
        refresh_token: refresh token
        client_id: ID приложения hh.ru
        client_secret: секрет приложения hh.ru

    Returns:
        dict: {access_token, refresh_token, token_type, expires_in}

    Raises:
        ValidationError: при ошибке API или валидации
    """
    if not client_id or not client_secret:
        raise ValidationError("hh.ru не настроен: отсутствует client_id или client_secret")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }

    async with _get_client() as client:
        try:
            response = await client.post(
                settings.HH_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            result = response.json()

            # Проверяем обязательные поля в ответе
            required_fields = ["access_token", "refresh_token", "token_type", "expires_in"]
            for field in required_fields:
                if field not in result:
                    raise ValidationError(f"Ответ hh.ru не содержит поле {field}")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка обновления токенов hh.ru: {e}")


async def get_me(access_token: str) -> dict:
    """
    Получает информацию о текущем пользователе/менеджере

    Args:
        access_token: access token

    Returns:
        dict: данные пользователя с employer.id

    Raises:
        ValidationError: при ошибке API или валидации
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            result = response.json()

            # Базовая проверка структуры ответа
            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru /me")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения данных пользователя hh.ru: {e}")


async def get_employer_vacancies(access_token: str, employer_id: str, page: int = 0, per_page: int = 50) -> dict:
    """
    Получает активные вакансии работодателя

    Args:
        access_token: access token
        employer_id: ID работодателя на hh.ru
        page: страница (0-based)
        per_page: количество записей на странице

    Returns:
        dict: список вакансий {items: [...], pages, page, ...}

    Raises:
        ValidationError: при ошибке API
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/vacancies",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "employer_id": employer_id,
                    "page": page,
                    "per_page": per_page
                }
            )
            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru /vacancies")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения вакансий hh.ru: {e}")


async def get_negotiation_collections(access_token: str, vacancy_id: str) -> list[dict]:
    """Список коллекций откликов работодателя по вакансии.

    hh для работодателя на /negotiations?vacancy_id отдаёт КОЛЛЕКЦИИ по статусам
    (response/consider/interview/discard/…), у каждой свой url для получения откликов.
    ⚠️ Требует доступа работодателя к откликам на hh.ru.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with _get_client() as client:
        try:
            r = await client.get(
                f"{settings.HH_API_BASE}/negotiations",
                headers=headers,
                params={"vacancy_id": vacancy_id},
            )
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения коллекций откликов hh.ru: {e}")
        if r.status_code >= 400:
            raise ValidationError(f"hh.ru ошибка (коллекции, HTTP {r.status_code}): {r.text[:200]}")
        data = r.json()
        if not isinstance(data, dict):
            raise ValidationError("Некорректный формат ответа hh.ru /negotiations")
        return data.get("collections") or []


async def get_collection_page(access_token: str, url: str, page: int = 0, per_page: int = 50) -> dict:
    """Одна страница откликов коллекции по её url. Возвращает {items, found, pages, ...}."""
    headers = {"Authorization": f"Bearer {access_token}"}
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}page={page}&per_page={per_page}"
    async with _get_client() as client:
        try:
            r = await client.get(full, headers=headers)
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения откликов hh.ru: {e}")
        if r.status_code >= 400:
            raise ValidationError(f"hh.ru ошибка (отклики, HTTP {r.status_code}): {r.text[:200]}")
        data = r.json()
        if not isinstance(data, dict):
            raise ValidationError("Некорректный формат откликов hh.ru")
        return data


async def get_negotiation_responses(access_token: str, vacancy_id: str, page: int = 0, per_page: int = 50) -> dict:
    """Отклики коллекции 'response' (обёртка — используется cron-джобом)."""
    collections = await get_negotiation_collections(access_token, vacancy_id)
    resp = next((c for c in collections if c.get("id") == "response"), None)
    if not resp:
        return {"items": [], "found": 0, "pages": 0}
    url = resp.get("url") or f"{settings.HH_API_BASE}/negotiations/response?vacancy_id={vacancy_id}"
    return await get_collection_page(access_token, url, page, per_page)


async def get_resume(access_token: str, resume_url: str) -> dict:
    """Полное резюме по его url (из отклика). В отличие от краткого resume в списке
    откликов, содержит опыт с описанием, образование, возраст и контакты
    (контакты — если hh их открыл/оплачены)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with _get_client() as client:
        try:
            r = await client.get(resume_url, headers=headers)
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения резюме hh.ru: {e}")
        if r.status_code >= 400:
            raise ValidationError(f"hh.ru ошибка (резюме, HTTP {r.status_code}): {r.text[:200]}")
        data = r.json()
        if not isinstance(data, dict):
            raise ValidationError("Некорректный формат резюме hh.ru")
        return data


async def publish_vacancy(access_token: str, payload: dict) -> dict:
    """
    Публикует вакансию на hh.ru

    ⚠️  НЕ проверено без реального токена hh.ru

    Args:
        access_token: access token
        payload: данные вакансии в формате hh.ru API

    Returns:
        dict: ответ с id созданной вакансии

    Raises:
        ValidationError: при ошибке API
    """
    async with _get_client() as client:
        try:
            response = await client.post(
                f"{settings.HH_API_BASE}/vacancies",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru POST /vacancies")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка публикации вакансии hh.ru: {e}")


async def get_chat_messages(access_token: str, chat_id: str, limit: int = 50, order: str = "prev") -> dict:
    """
    Получает сообщения чата с кандидатом через новый Chats API

    Args:
        access_token: access token
        chat_id: ID чата на hh.ru
        limit: максимальное количество сообщений (1-50)
        order: порядок сообщений ("prev" | "next")

    Returns:
        dict: ответ hh.ru с полями {"items": [...], "has_more": bool}

    Raises:
        ValidationError: при ошибке API
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/common/chats/{chat_id}/messages",
                headers=headers,
                params={"limit": limit, "order": order}
            )

            if response.status_code == 403:
                raise ValidationError("Нет прав на чат hh")
            elif response.status_code == 404:
                raise ValidationError("Чат hh не найден")
            elif response.status_code == 410:
                raise ValidationError("hh-чат недоступен")
            elif response.status_code >= 400:
                raise ValidationError(f"hh.ru ошибка чтения чата (HTTP {response.status_code}): {response.text[:200]}")

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru /common/chats/.../messages")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения сообщений чата hh.ru: {e}")


async def send_chat_message(access_token: str, chat_id: str, text: str) -> dict:
    """
    Отправляет сообщение в чат кандидату через новый Chats API

    Args:
        access_token: access token
        chat_id: ID чата на hh.ru
        text: текст сообщения

    Returns:
        dict: ответ hh.ru с id созданного сообщения

    Raises:
        ValidationError: при ошибке API или недоступности чата
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "text": text,
        "idempotency_key": str(uuid.uuid4())
    }

    async with _get_client() as client:
        try:
            response = await client.post(
                f"{settings.HH_API_BASE}/common/chats/{chat_id}/messages",
                headers=headers,
                json=payload
            )

            if response.status_code == 403:
                raise ValidationError("Нет прав на чат hh")
            elif response.status_code == 404:
                raise ValidationError("Чат hh не найден")
            elif response.status_code == 410:
                raise ValidationError("hh-чат недоступен")
            elif response.status_code == 409:
                raise ValidationError("Конфликт при отправке сообщения hh (дублирующий idempotency_key)")
            elif response.status_code == 400:
                raise ValidationError(f"Некорректные аргументы отправки hh: {response.text[:200]}")
            elif response.status_code >= 400:
                raise ValidationError(f"hh.ru ошибка отправки чата (HTTP {response.status_code}): {response.text[:200]}")

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru POST /common/chats/.../messages")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка отправки сообщения в чат hh.ru: {e}")


async def get_negotiation(access_token: str, negotiation_id: str) -> dict:
    """
    Получает информацию об отклике/переписке (для извлечения chat_id)

    Args:
        access_token: access token
        negotiation_id: ID отклика на hh.ru

    Returns:
        dict: объект отклика с полем chat_id

    Raises:
        ValidationError: при ошибке API
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/negotiations/{negotiation_id}",
                headers=headers
            )

            if response.status_code == 403:
                raise ValidationError("Нет прав на отклик hh")
            elif response.status_code == 404:
                raise ValidationError("Отклик hh не найден")
            elif response.status_code >= 400:
                raise ValidationError(f"hh.ru ошибка получения отклика (HTTP {response.status_code}): {response.text[:200]}")

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru GET /negotiations/.../")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения отклика hh.ru: {e}")


async def discard_negotiation(access_token: str, negotiation_id: str) -> bool:
    """
    Отклоняет отклик на hh.ru (переводит employer_state в discard).

    Метод по спеке hh `put-negotiations-collection-to-next-state`:
    `PUT /negotiations/{collection}` где collection — в ПУТИ, а id отклика — в ТЕЛЕ
    form-urlencoded как `topic_id` (обязателен).

    Коллекция отказа РАБОТОДАТЕЛЯ — `discard_by_employer` (НЕ `discard`!). Подтверждено
    дампом actions[] активного отклика (state=response): доступны discard_by_employer/
    discard_by_applicant/discard_no_interaction/..., а action `discard` отсутствует —
    поэтому `PUT /negotiations/discard` возвращал wrong_state. Сообщение шлём отдельно
    новым Chats API.

    Returns:
        True  — отклик отклонён сейчас (204).
        False — отклик УЖЕ в недоступном для отказа состоянии (hh 403 wrong_state,
                как правило уже в discard). Повторять не нужно.

    Raises:
        ValidationError — прочие ошибки (нет прав/не найден/сеть) → нужен ретрай.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    data = {"topic_id": negotiation_id}  # id отклика — в теле (collection — в пути)

    async with _get_client() as client:
        try:
            response = await client.put(
                f"{settings.HH_API_BASE}/negotiations/discard_by_employer",
                headers=headers,
                data=data
            )
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка отказа отклика hh.ru: {e}")

        if response.status_code == 204:
            logger.info(f"hh.ru отклик {negotiation_id} успешно отклонён")
            return True

        body = response.text[:300]
        # 403 wrong_state — отклик уже в недоступном для отказа состоянии (обычно
        # уже discard, т.к. импортирован из discard-коллекции). Не ошибка: цель
        # (отказ на hh) уже достигнута. Помечаем synced, не ретраим.
        if response.status_code == 403 and "wrong_state" in body:
            logger.info(f"hh.ru отклик {negotiation_id} уже в недоступном для отказа состоянии (wrong_state) — синк не требуется")
            return False
        if response.status_code == 400:
            raise ValidationError(f"Некорректные данные для отказа hh отклика {negotiation_id}: {body}")
        if response.status_code == 403:
            raise ValidationError(f"Невозможно выполнить отказ hh отклика {negotiation_id}: {body}")
        if response.status_code == 404:
            raise ValidationError(f"hh отклик {negotiation_id} не найден")
        raise ValidationError(f"hh.ru ошибка отказа отклика (HTTP {response.status_code}): {body}")


async def search_resumes(access_token: str, params: dict) -> dict:
    """
    Поиск резюме в базе hh.ru

    Args:
        access_token: access token
        params: параметры поиска (text, area, professional_role, experience, salary, etc.)

    Returns:
        dict: ответ hh.ru с полями found и items

    Raises:
        ValidationError: при ошибке API
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/resumes",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru /resumes")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка поиска резюме hh.ru: {e}")


async def get_resume_by_id(access_token: str, resume_id: str) -> dict:
    """
    Получает резюме по ID (ПЛАТНО - тратит квоту просмотров)

    Args:
        access_token: access token
        resume_id: ID резюме на hh.ru

    Returns:
        dict: полное резюме

    Raises:
        ValidationError: при ошибке API или превышении квоты (429)
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/resumes/{resume_id}",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code == 429:
                raise ValidationError("Превышена квота просмотров резюме hh.ru")

            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru GET /resumes/{id}")

            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения резюме hh.ru: {e}")


async def invite_to_vacancy(access_token: str, resume_id: str, vacancy_id: str, message: str | None = None) -> dict:
    """
    Приглашает кандидата на вакансию

    Args:
        access_token: access token
        resume_id: ID резюме на hh.ru
        vacancy_id: ID вакансии на hh.ru
        message: сообщение приглашения (опционально)

    Returns:
        dict: ответ hh.ru с созданным приглашением (извлекаем negotiation_id)

    Raises:
        ValidationError: при ошибке API
    """
    data = {
        "resume_id": resume_id,
        "vacancy_id": vacancy_id
    }
    if message:
        data["message"] = message

    async with _get_client() as client:
        try:
            response = await client.post(
                f"{settings.HH_API_BASE}/negotiations/phone_interview",
                headers={"Authorization": f"Bearer {access_token}"},
                data=data
            )
        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка приглашения кандидата hh.ru: {e}")

        # Тело ответа hh при ошибке содержит РЕАЛЬНУЮ причину (лимит приглашений, нет прав
        # на вакансию, нужен доступ к контактам и т.п.) — пробрасываем её, иначе видно
        # лишь обобщённое «403 Forbidden» от httpx.
        if response.status_code >= 400:
            raise ValidationError(
                f"hh.ru отклонил приглашение (HTTP {response.status_code}): {response.text[:400]}"
            )

        # Успех phone_interview может прийти 201 с пустым телом — это нормально.
        try:
            result = response.json()
        except Exception:
            result = {}
        return result if isinstance(result, dict) else {}


async def get_payable_api_actions(access_token: str, employer_id: str) -> dict:
    """
    Получает остаток платных API-действий работодателя

    Args:
        access_token: access token
        employer_id: ID работодателя на hh.ru

    Returns:
        dict: ответ hh.ru с остатками квот

    Raises:
        ValidationError: при ошибке API
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/employers/{employer_id}/services/payable_api_actions/active",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            result = response.json()

            # Может вернуть как dict, так и list
            return result

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения квот hh.ru: {e}")


async def suggest_areas(access_token: str, text: str) -> list[dict]:
    """
    Получает подсказки регионов/городов из справочника hh.ru

    Args:
        access_token: access token
        text: текст для поиска

    Returns:
        list[dict]: список областей/регионов с полями id и text

    Raises:
        ValidationError: при ошибке API
    """
    async with _get_client() as client:
        try:
            response = await client.get(
                f"{settings.HH_API_BASE}/suggests/areas",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"text": text}
            )
            response.raise_for_status()

            result = response.json()

            if not isinstance(result, dict):
                raise ValidationError("Некорректный формат ответа hh.ru /suggests/areas")

            return result.get("items", [])

        except httpx.HTTPError as e:
            raise ValidationError(f"Ошибка получения подсказок регионов hh.ru: {e}")


def build_authorize_url(state: str, client_id: str, redirect_uri: str) -> str:
    """
    Строит URL для авторизации через hh.ru

    Args:
        state: уникальный state для CSRF защиты
        client_id: ID приложения hh.ru
        redirect_uri: redirect URI приложения hh.ru

    Returns:
        str: полный URL для редиректа в браузер

    Raises:
        ValidationError: если нет конфигурации
    """
    if not client_id or not redirect_uri:
        raise ValidationError("hh.ru не настроен: отсутствует client_id или redirect_uri")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "role": "employer",
        "force_role": "true",
        "skip_choose_account": "true"
    }

    return f"{settings.HH_AUTHORIZE_URL}?{urlencode(params)}"