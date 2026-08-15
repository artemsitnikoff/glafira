"""GraphQL-клиент Talantix (talantix.ru). Зеркалит glafiraeuro/talantix_client.py.

⚠️ Особенности (подтверждены по клиенту euro + доке api.talantix.ru/docs):
* Тип Person — interface (union PersonItem | PersonError). Запрос через inline-фрагмент
  `... on PersonItem`, ошибка — `... on PersonError { message }` (НЕ роняет импорт).
* HTTP 200 с непустым `data["errors"]` = ОШИБКА (raise TalantixError, НЕ успех).
* 401 = access_token протух → force refresh + retry (token.force_refresh_on_401).
* persons(first, after, filter): сервер капит 50/стр., идём по after=endCursor пока
  hasNextPage. total НЕТ — считаем перечислением.
* Instant = миллисекунды с эпохи (int).
* history(after, first): HistoryEvent — interface; нужны только CommentAdded /
  HhCommentAdded (inline-фрагменты). ВСЕ страницы курсором.
"""

import asyncio
import logging
from uuid import UUID

import httpx

from ....config import settings
from ....core.errors import ValidationError
from . import token as talantix_token

logger = logging.getLogger(__name__)


class TalantixError(Exception):
    """Ошибка GraphQL Talantix (data.errors) или сети."""
    pass


# ---------- GraphQL запросы (поля подтверждены по доке) ----------

CHECK_QUERY = """
query Check {
  persons(first: 1) {
    items { ... on PersonItem { id } }
  }
}
""".strip()


PERSONS_LIST_QUERY = """
query Persons($first: Int!, $after: String, $filter: PersonFilterInput) {
  persons(first: $first, after: $after, filter: $filter) {
    items { ... on PersonItem { id } }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()


PERSON_FULL_QUERY = """
query Person($id: Int!) {
  person(id: $id) {
    __typename
    ... on PersonItem {
      id
      firstName
      lastName
      middleName
      gender
      birthDay
      updatedAt
      area { id name }
      source { id name }
      contacts { items { ... on ContactItem { type value } } }
      resumes { items { ... on StructuredResume {
        id title skills keySkills
        salary { amount currency }
        experiences { items { position description company { name } area { name } period { start end months } } }
        education { level { name } }
        languages { items { name level { name } } }
      } } }
      personalDataAgreement { personalDataAgreementStatus updatedAt expiredAt }
      responses { count }
    }
    ... on PersonError {
      message
    }
  }
}
""".strip()


# История кандидата — только комментарии (CommentAdded / HhCommentAdded).
# Прочие типы событий вернут лишь __typename и отфильтруются маппером.
PERSON_HISTORY_QUERY = """
query PersonHistory($id: Int!, $first: Int!, $after: String) {
  person(id: $id) {
    __typename
    ... on PersonItem {
      history(first: $first, after: $after) {
        items {
          __typename
          ... on CommentAdded {
            id
            eventTime
            html
            initiator { __typename ... on CompanyManager { firstName lastName middleName } }
            vacancy { ... on VacancyItem { id title } }
          }
          ... on HhCommentAdded {
            id
            eventTime
            html
            managerName
            initiator { __typename ... on CompanyManager { firstName lastName middleName } }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    ... on PersonError {
      message
    }
  }
}
""".strip()


async def probe_access_token(access_token: str) -> bool:
    """Лёгкая проверка access_token НАПРЯМУЮ (persons first:1), БЕЗ рефреша и БЕЗ БД.

    Используется на connect: если пастнутый access рабочий — не тратим свежий
    refresh_token на ротацию. True — токен рабочий; False — 401/GraphQL-ошибка/сеть.
    Не кидает (валидация — pass/fail; при False вызывающий делает фолбэк на refresh)."""
    if not access_token:
        return False
    try:
        async with httpx.AsyncClient(
            base_url=settings.TALANTIX_GRAPHQL_URL,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": settings.TALANTIX_USER_AGENT,
            },
        ) as client:
            resp = await client.post(
                "",
                json={"query": CHECK_QUERY, "variables": {}},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except (httpx.TimeoutException, httpx.NetworkError):
        return False
    if not resp.is_success:
        return False
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return False
    return not data.get("errors")


class TalantixClient:
    """Per-company клиент. Токен резолвится лениво через token.get_access_token."""

    def __init__(self, company_id: UUID):
        self.company_id = company_id
        self._token: str | None = None
        self._client = httpx.AsyncClient(
            base_url=settings.TALANTIX_GRAPHQL_URL,
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": settings.TALANTIX_USER_AGENT,
            },
        )
        # Кап на параллельные запросы — сервер может ругаться при шквале.
        self._sem = asyncio.Semaphore(6)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TalantixClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def _ensure_token(self) -> str:
        if not self._token:
            self._token = await talantix_token.get_access_token(self.company_id)
        return self._token

    async def _gql(self, query: str, variables: dict | None = None, _retry: bool = True) -> dict:
        token = await self._ensure_token()
        try:
            async with self._sem:
                resp = await self._client.post(
                    "",
                    json={"query": query, "variables": variables or {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TalantixError("Talantix недоступен (сеть/таймаут)") from exc

        if resp.status_code == 401 and _retry:
            logger.info("[talantix] 401 → принудительный refresh + retry")
            self._token = await talantix_token.force_refresh_on_401(self.company_id)
            return await self._gql(query, variables, _retry=False)

        if not resp.is_success:
            raise TalantixError(f"Talantix вернул HTTP {resp.status_code}")

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise TalantixError("Talantix вернул некорректный JSON") from exc

        # HTTP 200 + непустой errors = ОШИБКА (не успех).
        if data.get("errors"):
            msg = "; ".join(e.get("message", "?") for e in data["errors"] if isinstance(e, dict))
            raise TalantixError(f"GraphQL: {msg}")
        return data.get("data") or {}

    # ----- Проверка соединения -----

    async def check_connection(self) -> bool:
        """Лёгкий запрос для проверки токена. Кидает при сбое (обрабатывает вызывающий)."""
        await self._gql(CHECK_QUERY)
        return True

    # ----- Список персон (курсор) -----

    async def iter_person_ids(self, filter_: dict | None = None, max_pages: int = 2000):
        """Async-генератор id персон постранично (сервер капит 50/стр.)."""
        cursor: str | None = None
        for _ in range(max_pages):
            data = await self._gql(
                PERSONS_LIST_QUERY,
                {"first": 50, "after": cursor, "filter": filter_},
            )
            persons_obj = data.get("persons") or {}
            for it in (persons_obj.get("items") or []):
                if it and it.get("id") is not None:
                    yield it["id"]
            page_info = persons_obj.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break
        else:
            logger.warning("[talantix] iter_person_ids упёрлась в max_pages=%d", max_pages)

    async def collect_person_ids(self, filter_: dict | None = None, max_pages: int = 2000) -> list[int]:
        """Собрать ВСЕ id персон в список (для total прогресса + сэмпла превью)."""
        ids: list[int] = []
        async for pid in self.iter_person_ids(filter_, max_pages=max_pages):
            ids.append(pid)
        return ids

    # ----- Полная карточка персоны -----

    async def get_person_full(self, person_id: int) -> dict | None:
        """Полная карточка PersonItem как dict. None — если PersonError (пропустить с логом)."""
        data = await self._gql(PERSON_FULL_QUERY, {"id": int(person_id)})
        node = data.get("person") or {}
        if node.get("__typename") == "PersonError":
            logger.warning("[talantix] person %s: PersonError %s", person_id, node.get("message"))
            return None
        return node

    # ----- История (все страницы курсором) -----

    async def fetch_all_history(self, person_id: int, max_pages: int = 200) -> list[dict]:
        """ВСЕ события истории персоны (сырьё nodes) — идём по курсору до конца.

        Возвращает список raw-nodes событий (с __typename); маппер отфильтрует комментарии.
        PersonError → пустой список (не роняем импорт кандидата)."""
        events: list[dict] = []
        cursor: str | None = None
        for _ in range(max_pages):
            data = await self._gql(
                PERSON_HISTORY_QUERY,
                {"id": int(person_id), "first": 50, "after": cursor},
            )
            node = data.get("person") or {}
            if node.get("__typename") == "PersonError":
                logger.warning(
                    "[talantix] history person %s: PersonError %s", person_id, node.get("message")
                )
                break
            history = node.get("history") or {}
            for it in (history.get("items") or []):
                if it:
                    events.append(it)
            page_info = history.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break
        else:
            logger.warning("[talantix] fetch_all_history person %s упёрлась в max_pages=%d", person_id, max_pages)
        return events
