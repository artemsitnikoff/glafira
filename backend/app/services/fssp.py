"""ФССП (исполнительные производства) через стороннего провайдера parser-api.com.

Официальный API ФССП закрыт → используем parser-api.com (СИНХРОННЫЙ поиск по банку
данных исполнительных производств ФССП). Провайдер требует ФИО + ДАТУ РОЖДЕНИЯ (dob):
без даты рождения поиск невозможен вовсе.

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
    иной формы. Если done=1, но список не нашёлся — вернём [] (провайдер отработал,
    производств нет). Реальную форму ответа пиннить на живом ключе (см. лог ниже).
    """
    for k in ("records", "result", "data", "items", "enforcements", "productions"):
        v = data.get(k)
        if isinstance(v, list):
            return v
    return []


def _normalize_record(rec: dict) -> dict:
    """Одна запись ИП provider parser-api → нормализованный словарь для UI.

    Реальная форма записи parser-api (запинена на живом ключе 2026-09-29):
      debtor_name, debtor_address, debtor_dob, process_title (номер ИП), process_date,
      subjects: [{title}, {title:"Общая сумма задолженности", sum:"3621.21"}],
      stop_date, stop_reason, department_title, officer_name, officer_phones[].
    Старые имена (name/exe_production/…) оставлены как ФОЛБЭК. Исходная запись целиком —
    в `raw`: фронт/аудит видят всё, даже если конкретное поле не распозналось.
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


async def search_enforcement(
    last_name: str,
    first_name: str,
    patronymic: str | None,
    birth_date,
    region_id: str | int | None = None,
) -> list[dict] | None:
    """Поиск исполнительных производств физлица через parser-api.com (синхронно, один GET).

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
        "key": settings.FSSP_API_KEY,
        "lastName": last_name.strip(),
        "firstName": first_name.strip(),
        "dob": dob,
    }
    if patronymic and patronymic.strip():
        params["patronymic"] = patronymic.strip()
    if region_id not in (None, ""):
        params["regionID"] = str(region_id)

    url = f"{settings.FSSP_API_BASE}/search_fiz"
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

    # done=1 — успех. Любое другое (done=0/отсутствует, код 403/400 в теле) → не удалось.
    if not isinstance(data, dict) or data.get("done") != 1:
        logger.warning("[fssp] provider done!=1 or bad payload: %s", str(data)[:300])
        return None

    records = _extract_records(data)
    # info-лог формы ответа — помогает пиннить ключ списка на живом провайдере, если наш
    # маппинг разошёлся (done=1, но records пуст при непривычном ключе → ложное «чисто»).
    logger.info("[fssp] done=1 keys=%s records=%d", list(data.keys()), len(records))
    return [_normalize_record(r) for r in records if isinstance(r, dict)]
