"""ФССП (исполнительные производства) через стороннего провайдера api-cloud.ru.

Официальный API ФССП закрыт → используем api-cloud.ru (СИНХРОННЫЙ поиск по банку
данных исполнительных производств ФССП). Контракт:
    GET {FSSP_API_BASE}/fssp.php?type=physical&token=…&lastname=…&firstname=…
        &secondname=…&birthdate=дд.мм.гггг&region=…
    → успех: {"status": 200, "records": [ … ], "countAll": N, …}
    → ошибка: {"error": "503", "message": "TOKEN_NOT_REGISTERED_IN_THE_SYSTEM"} и т.п.
Провайдер требует ФИО + ДАТУ РОЖДЕНИЯ (dob): без даты рождения поиск невозможен вовсе.
BASE в env — у api-cloud есть клоны/реселлеры с тем же API, но своим токеном.

⚠️ Результат — ВОЗМОЖНЫЕ совпадения по ФИО + ДР, а НЕ подтверждённая задолженность
конкретного кандидата (возможны однофамильцы). Подача в UI — со строгой плашкой,
её формирует verify.py (`_build_fssp_block`). Тут — только транспорт и нормализация.

Gated ключом `FSSP_API_KEY`: пусто → интеграция выключена (verify.py оставляет честную
заглушку). Любой сбой (нет ключа / нет ДР / сеть / done!=1 / 403/400) → graceful None.
⚠️ None ≠ пустой список: None = «не удалось проверить» (НЕЛЬЗЯ трактовать как «чисто»),
[] = «провайдер отработал, производств не найдено» (чисто). Различать обязательно (§0).
"""

import logging
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Провайдер синхронный и обычно отвечает быстро; держим потолок, чтобы не подвесить
# HTTP-запрос верификации (вызов встроен в verify_candidate, не в фон).
FSSP_TIMEOUT = 20


def _format_dob(birth_date) -> str | None:
    """Дата рождения → формат провайдера дд.мм.ГГГГ. None/пусто → None."""
    if birth_date is None:
        return None
    if isinstance(birth_date, (date, datetime)):
        return birth_date.strftime("%d.%m.%Y")
    s = str(birth_date).strip()
    return s or None


def _extract_records(data: dict) -> list:
    """Достать список исполнительных производств из ответа провайдера.

    Основной документированный ключ — `records`; остальные — защитный фолбэк на случай
    иной формы. Если status=200, но список не нашёлся — вернём [] (провайдер отработал,
    производств нет). Реальную форму ответа пиннить на живом ключе (см. лог ниже).
    """
    for k in ("records", "result", "data", "items", "enforcements", "productions"):
        v = data.get(k)
        if isinstance(v, list):
            return v
    return []


def _normalize_record(rec: dict) -> dict:
    """Одна запись ИП провайдера → нормализованный словарь.

    Ключи мапим ЗАЩИТНО (несколько вариантов имён — точная форма пиннится на живом
    ключе), исходную запись целиком сохраняем в `raw`: фронт/аудит увидят всё как
    отдал провайдер, даже если конкретное поле не распозналось.
    """
    def pick(*keys: str) -> str:
        for k in keys:
            v = rec.get(k)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    return {
        "debtor": pick("name", "debtor", "fio", "full_name", "debtor_name"),
        "production": pick("process_title", "exe_production", "exeProduction", "ip_number", "number"),
        "subject": pick("subject", "details", "exe_subject", "purpose", "process_subject"),
        "amount": pick("subject_amount", "amount", "debt", "sum", "summ"),
        "status": pick("ip_end", "status", "state", "ip_status", "process_status"),
        "department": pick("department", "osp", "subdivision", "division", "department_name"),
        "bailiff": pick("bailiff", "officer", "executor", "spi", "bailiff_name"),
        "raw": rec,
    }


async def search_enforcement(
    last_name: str,
    first_name: str,
    patronymic: str | None,
    birth_date,
    region_id: str | int | None = None,
) -> list[dict] | None:
    """Поиск исполнительных производств физлица через api-cloud.ru (синхронно, один GET).

    Возвращает:
      - list[dict] (НЕПУСТОЙ) — найдены возможные совпадения ИП;
      - []            — провайдер отработал, производств не найдено (чисто);
      - None          — не удалось проверить (нет ключа / нет ДР / сеть / done!=1 / 403/400).

    ⚠️ None НЕЛЬЗЯ трактовать как «чисто» (§0). Дата рождения ОБЯЗАТЕЛЬНА провайдером —
    без неё поиск не выполняется (возвращаем None; verify.py даёт по этому кейсу отдельный
    честный текст, проверяя candidate.birth_date ДО вызова).
    """
    if not settings.FSSP_API_KEY:
        logger.debug("[fssp] FSSP_API_KEY не настроен — проверка выключена")
        return None
    if not (last_name and last_name.strip()) or not (first_name and first_name.strip()):
        logger.debug("[fssp] недостаточно ФИО для поиска")
        return None

    dob = _format_dob(birth_date)
    if not dob:
        # Провайдер БЕЗ даты рождения не ищет — честно None.
        logger.debug("[fssp] нет даты рождения — поиск невозможен")
        return None

    params = {
        "type": "physical",
        "token": settings.FSSP_API_KEY,
        "lastname": last_name.strip(),
        "firstname": first_name.strip(),
        "birthdate": dob,
    }
    if patronymic and patronymic.strip():
        params["secondname"] = patronymic.strip()
    if region_id not in (None, ""):
        params["region"] = str(region_id)

    url = f"{settings.FSSP_API_BASE}/fssp.php"
    try:
        async with httpx.AsyncClient(timeout=FSSP_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        # Логируем тело ответа (как в dadata.py) — на живом ключе видно причину 403/400.
        body = (getattr(getattr(e, "response", None), "text", "") or "")[:500]
        logger.warning("[fssp] search_enforcement failed: %s: %s | %s", type(e).__name__, e, body)
        return None

    # api-cloud: успех → {"status": 200, ...}. Ошибка провайдера (нет токена/лимит/неверный
    # type) приходит с HTTP 200, но телом {"error": "...", "message": "..."} (напр.
    # TOKEN_NOT_REGISTERED_IN_THE_SYSTEM) → status!=200 → не удалось (None, НЕ «чисто», §0).
    if not isinstance(data, dict):
        logger.warning("[fssp] bad payload (not a dict): %s", str(data)[:300])
        return None
    if data.get("status") not in (200, "200"):
        logger.warning("[fssp] provider status!=200: %s", str(data)[:300])
        return None

    records = _extract_records(data)
    # info-лог формы ответа — помогает пиннить ключ списка на живом провайдере, если наш
    # маппинг разошёлся (status=200, но records пуст при непривычном ключе → ложное «чисто»).
    logger.info("[fssp] status=200 keys=%s records=%d", list(data.keys()), len(records))
    return [_normalize_record(r) for r in records if isinstance(r, dict)]
