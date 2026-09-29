"""Госпроверки физлица через стороннего провайдера parser-api.com.

Официальные API ФССП/МВД закрыты → используем parser-api.com (СИНХРОННЫЙ поиск).
Один провайдер, один ключ `FSSP_API_KEY`, общий транспорт `_parser_get`. Реализованы
проверки, доступные по данным кандидата (ФИО + дата рождения):

  - search_enforcement — исполнительные производства (`fssp_api/search_fiz`);
  - search_alimony      — задолженность по алиментам (`fssp_alim_api/`);
  - search_fssp_wanted  — реестр розыска должников ФССП (`fssp_search_api/`, ДР не нужна);
  - search_mvd_wanted   — розыск МВД (`mvd_wanted_api/`, ДР в YYYY-MM-DD).

⚠️ Результат — ВОЗМОЖНЫЕ совпадения по ФИО (+ДР), а НЕ подтверждённый факт про конкретного
кандидата (возможны однофамильцы). Плашку формирует verify.py. Тут — транспорт+нормализация.

⚠️ Семантика возврата (общая для всех search_*): None = «не удалось проверить» (нет ключа /
нет обязательных полей / сеть / провайдер вернул ошибку) — НЕЛЬЗЯ трактовать как «чисто» (§0);
[] = «провайдер отработал, ничего не найдено» (чисто); [ … ] = найдены совпадения.
"""

import logging
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Провайдер синхронный и обычно отвечает быстро; держим потолок, чтобы не подвесить
# HTTP-запрос верификации (вызовы встроены в verify_candidate, не в фон).
FSSP_TIMEOUT = 20


def _format_dob(birth_date) -> str | None:
    """Дата рождения → формат дд.мм.ГГГГ (fssp/alim принимают его). None/пусто → None."""
    if birth_date is None:
        return None
    if isinstance(birth_date, (date, datetime)):
        return birth_date.strftime("%d.%m.%Y")
    s = str(birth_date).strip()
    return s or None


def _format_dob_iso(birth_date) -> str | None:
    """Дата рождения → YYYY-MM-DD (требует mvd_wanted). None/пусто → None.

    Строку возвращаем как есть (может уже прийти в нужном формате); date/datetime → ISO.
    """
    if birth_date is None:
        return None
    if isinstance(birth_date, (date, datetime)):
        return birth_date.strftime("%Y-%m-%d")
    s = str(birth_date).strip()
    return s or None


def _api_root() -> str:
    """Корень parser-api (…/parser) из FSSP_API_BASE (…/parser/fssp_api).

    Позволяет бить в соседние модули провайдера (fssp_alim_api/mvd_wanted_api/…), меняя
    только один env FSSP_API_BASE (напр. при переезде на клон/реселлер с тем же API).
    """
    return settings.FSSP_API_BASE.rsplit("/", 1)[0]


async def _parser_get(endpoint: str, params: dict) -> dict | None:
    """Один GET к parser-api по пути {root}/{endpoint}. Ключ добавляется автоматически.

    Успех = тело dict c `done==1` ИЛИ `success==1` (разные модули используют разный флаг).
    Иначе (нет ключа / сеть / HTTP / ошибка провайдера в теле, напр. TOKEN_NOT_REGISTERED,
    лимит) → None. ⚠️ None ≠ «чисто» (§0). Тело ошибки логируем (как в dadata.py).
    """
    if not settings.FSSP_API_KEY:
        logger.debug("[fssp] FSSP_API_KEY не настроен — проверка выключена")
        return None
    url = f"{_api_root()}/{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=FSSP_TIMEOUT) as client:
            resp = await client.get(url, params={**params, "key": settings.FSSP_API_KEY})
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        body = (getattr(getattr(e, "response", None), "text", "") or "")[:500]
        logger.warning("[fssp] %s failed: %s: %s | %s", endpoint, type(e).__name__, e, body)
        return None
    if not isinstance(data, dict) or not (data.get("done") == 1 or data.get("success") == 1):
        logger.warning("[fssp] %s not ok: %s", endpoint, str(data)[:300])
        return None
    return data


def _extract_records(data: dict) -> list:
    """Достать список записей из ответа провайдера.

    Разные модули кладут список под разными ключами: `result` (fssp/alim/search),
    `records` (mvd). Пробуем оба + защитный фолбэк. Если ответ успешен, но списка нет —
    вернём [] (провайдер отработал, ничего не найдено).
    """
    for k in ("result", "records", "data", "items", "enforcements", "productions"):
        v = data.get(k)
        if isinstance(v, list):
            return v
    return []


def _normalize_record(rec: dict) -> dict:
    """Запись исполнительного производства / алиментов parser-api → словарь для UI.

    Реальная форма записи (запинена на живом ключе 2026-09-29):
      debtor_name, debtor_address, debtor_dob, process_title (номер ИП), process_date,
      subjects: [{title}, {title:"Общая сумма задолженности", sum:"3621.21"}],
      stop_date, stop_reason, department_title, officer_name, officer_phones[].
    Старые имена (name/exe_production/…) — ФОЛБЭК. Исходная запись целиком — в `raw`.
    """
    def pick(*keys: str) -> str:
        for k in keys:
            v = rec.get(k)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    # subjects — список: предмет(ы) взыскания + отдельной строкой «Общая сумма задолженности»
    # со `sum`. Разносим: title'ы (кроме метки суммы) → предмет, значение суммы → amount.
    subject_titles: list[str] = []
    amount = ""
    subjects = rec.get("subjects")
    if isinstance(subjects, list):
        for s in subjects:
            if not isinstance(s, dict):
                continue
            t = str(s.get("title") or "").strip()
            sm = s.get("sum")
            is_total = "сумма задолж" in t.lower()  # метка суммы, не предмет
            if sm not in (None, "") and (is_total or not amount):
                amount = str(sm).strip()
            if t and not is_total:
                subject_titles.append(t)
    subject = "; ".join(dict.fromkeys(subject_titles))  # dedupe, порядок сохранён

    # Статус ИП: parser-api не отдаёт явную строку — выводим из stop_date/stop_reason
    # (есть → производство окончено; иначе «на исполнении»).
    stop_date = pick("stop_date")
    stop_reason = pick("stop_reason")
    if stop_date or stop_reason:
        status = "Окончено" + (f" {stop_date}" if stop_date else "")
        if stop_reason:
            status += f" ({stop_reason})"
    else:
        status = "На исполнении"

    bailiff = pick("officer_name", "bailiff", "officer", "executor", "spi")
    phones = rec.get("officer_phones")
    if bailiff and isinstance(phones, list) and phones:
        bailiff = f"{bailiff}, {phones[0]}"

    return {
        "debtor": pick("debtor_name", "name", "debtor", "fio", "full_name"),
        "production": pick("process_title", "exe_production", "exeProduction", "ip_number", "number"),
        "subject": subject or pick("subject", "details", "exe_subject", "purpose"),
        "amount": amount or pick("subject_amount", "amount", "debt", "sum", "summ"),
        "status": status,
        "department": pick("department_title", "department", "osp", "subdivision", "division"),
        "bailiff": bailiff,
        "raw": rec,
    }


def _normalize_wanted_fssp(rec: dict) -> dict:
    """Запись реестра розыска должников ФССП (`fssp_search_api/`) → словарь для UI.

    Форма (запинена на живом ключе): search_category, search_title (розыскное дело),
    search_date, process_title (номер ИП), process_date, debtor_name, debtor_dob,
    department_title, department_address, department_phone. Сырьё — в `raw`.
    """
    def pick(*keys: str) -> str:
        for k in keys:
            v = rec.get(k)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    dept = pick("department_title")
    phone = pick("department_phone")
    if dept and phone:
        dept = f"{dept}, {phone}"

    return {
        "debtor": pick("debtor_name"),
        "debtor_dob": pick("debtor_dob"),
        "category": pick("search_category"),
        "search_case": pick("search_title"),
        "search_date": pick("search_date"),
        "production": pick("process_title"),
        "department": dept,
        "raw": rec,
    }


def _normalize_mvd(rec: dict) -> dict:
    """Запись розыска МВД (`mvd_wanted_api/`) → словарь для UI. Форма: {name: ФИО}. Сырьё — raw."""
    def pick(*keys: str) -> str:
        for k in keys:
            v = rec.get(k)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    return {
        "debtor": pick("name", "fio", "full_name", "debtor_name"),
        "raw": rec,
    }


async def search_enforcement(
    last_name: str,
    first_name: str,
    patronymic: str | None,
    birth_date,
    region_id: str | int | None = None,
) -> list[dict] | None:
    """Исполнительные производства физлица (`fssp_api/search_fiz`). ФИО + ДР обязательны.

    Возврат — см. модульный докстринг (None / [] / [ … ]).
    """
    if not (last_name and last_name.strip()) or not (first_name and first_name.strip()):
        logger.debug("[fssp] недостаточно ФИО для поиска")
        return None
    dob = _format_dob(birth_date)
    if not dob:
        logger.debug("[fssp] нет даты рождения — поиск невозможен")
        return None

    params = {"lastName": last_name.strip(), "firstName": first_name.strip(), "dob": dob}
    if patronymic and patronymic.strip():
        params["patronymic"] = patronymic.strip()
    if region_id not in (None, ""):
        params["regionID"] = str(region_id)

    data = await _parser_get("fssp_api/search_fiz", params)
    if data is None:
        return None
    records = _extract_records(data)
    logger.info("[fssp] enforcement ok keys=%s records=%d", list(data.keys()), len(records))
    return [_normalize_record(r) for r in records if isinstance(r, dict)]


async def search_alimony(
    last_name: str,
    first_name: str,
    patronymic: str | None,
    birth_date,
    region_id: str | int | None = None,
) -> list[dict] | None:
    """Задолженность по алиментам (`fssp_alim_api/`). ФИО + ДР. Форма записи — как у ИП."""
    if not (last_name and last_name.strip()) or not (first_name and first_name.strip()):
        return None
    dob = _format_dob(birth_date)
    if not dob:
        return None

    params = {"lastName": last_name.strip(), "firstName": first_name.strip(), "dob": dob}
    if patronymic and patronymic.strip():
        params["patronymic"] = patronymic.strip()
    if region_id not in (None, ""):
        params["regionID"] = str(region_id)

    data = await _parser_get("fssp_alim_api/", params)
    if data is None:
        return None
    records = _extract_records(data)
    logger.info("[fssp] alimony ok keys=%s records=%d", list(data.keys()), len(records))
    return [_normalize_record(r) for r in records if isinstance(r, dict)]


async def search_fssp_wanted(
    last_name: str,
    first_name: str,
    patronymic: str | None = None,
) -> list[dict] | None:
    """Реестр розыска должников ФССП (`fssp_search_api/`). По ФИО (дата рождения не нужна)."""
    if not (last_name and last_name.strip()) or not (first_name and first_name.strip()):
        return None

    params = {"lastName": last_name.strip(), "firstName": first_name.strip()}
    if patronymic and patronymic.strip():
        params["patronymic"] = patronymic.strip()

    data = await _parser_get("fssp_search_api/", params)
    if data is None:
        return None
    records = _extract_records(data)
    logger.info("[fssp] wanted-fssp ok keys=%s records=%d", list(data.keys()), len(records))
    return [_normalize_wanted_fssp(r) for r in records if isinstance(r, dict)]


async def search_mvd_wanted(
    last_name: str,
    first_name: str,
    patronymic: str | None,
    birth_date,
) -> list[dict] | None:
    """Розыск МВД (`mvd_wanted_api/`). ФИО + ДР обязательны (дата рождения — в YYYY-MM-DD)."""
    if not (last_name and last_name.strip()) or not (first_name and first_name.strip()):
        return None
    dob = _format_dob_iso(birth_date)
    if not dob:
        return None

    params = {"lastName": last_name.strip(), "firstName": first_name.strip(), "dob": dob}
    if patronymic and patronymic.strip():
        params["patronymic"] = patronymic.strip()

    data = await _parser_get("mvd_wanted_api/", params)
    if data is None:
        return None
    records = _extract_records(data)
    logger.info("[fssp] mvd-wanted ok keys=%s records=%d", list(data.keys()), len(records))
    return [_normalize_mvd(r) for r in records if isinstance(r, dict)]
