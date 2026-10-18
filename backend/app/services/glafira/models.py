"""Конфигурация LLM-моделей для AI-сервисов.

Список доступных моделей теперь ДИНАМИЧЕСКИЙ — тянется из публичного каталога
OpenRouter (`GET /models`, без ключа) с оценкой стоимости одной оценки резюме.
Статический «белый список» (ALLOWED_LLM_MODELS/ALLOWED_MODEL_VALUES) устарел и
удалён; валидация сохраняемой модели идёт против live-каталога (см. is_valid_model).
"""

import logging
import time

import httpx

from ...config import settings

logger = logging.getLogger(__name__)

# --- Оценка стоимости одной оценки резюме --------------------------------------
# ⚠️ ЭТО ОЦЕНКА, НЕ ТОЧНЫЙ БИЛЛИНГ. Усреднённый размер промпта/ответа скоринга
# одного резюме; реальный расход зависит от длины резюме/вакансии и ответа модели.
SCORING_EST_PROMPT_TOKENS = 4500
SCORING_EST_COMPLETION_TOKENS = 900
USD_RUB_RATE = 100.0  # грубый курс для прикидки в рублях (оценка, не курс ЦБ)

# Дефолтная модель (используется при отсутствии company-настройки и env)
DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"

# Рекомендованные модели — показываются в Настройки→AI в этом порядке
# (только те, что реально присутствуют в live-каталоге OpenRouter).
RECOMMENDED_MODELS = [
    "deepseek/deepseek-v4-pro",
    "z-ai/glm-5.2",
    "google/gemini-3.8-flash",
    "qwen/qwen3.7-max",
    "moonshotai/kimi-k3",
    "qwen/qwen3.8-max-0902",
    "anthropic/claude-sonnet-5.5",
    "openai/gpt-6.1-sol",
]

# --- DEPRECATED shim -----------------------------------------------------------
# Пустой set: суперадминка (`backend/superadmin/*`) импортирует это имя и валидирует
# как `if ALLOWED_MODEL_VALUES and ...` — пустое значение корректно отключает стейл-
# проверку (оператор доверенный, модель всё равно валидируется в клиентском приложении
# против live-каталога OpenRouter). НЕ использовать в новом коде.
ALLOWED_MODEL_VALUES: set[str] = set()

# --- live-каталог OpenRouter ---------------------------------------------------
_MODELS_CACHE_TTL = 3600.0  # секунд
# (timestamp, {id: {"name","prompt","completion","context_length"}})
_models_cache: tuple[float, dict] | None = None


def _prettify_slug(slug: str) -> str:
    """Человекочитаемое имя из slug, если каталог не дал `name`.

    'anthropic/claude-sonnet-5.5' -> 'Claude Sonnet 5.5'
    """
    tail = slug.split("/")[-1]
    words = [w for w in tail.replace("_", "-").split("-") if w]
    return " ".join(w[:1].upper() + w[1:] for w in words) if words else slug


def cost_estimate(prompt_per_token: float, completion_per_token: float) -> dict:
    """Прикидка стоимости одной оценки резюме (ОЦЕНКА, не точный биллинг).

    prompt_per_token / completion_per_token — цена OpenRouter в USD за ОДИН токен.
    """
    usd = (
        SCORING_EST_PROMPT_TOKENS * prompt_per_token
        + SCORING_EST_COMPLETION_TOKENS * completion_per_token
    )
    return {"usd": round(usd, 4), "rub": round(usd * USD_RUB_RATE, 2)}


async def fetch_openrouter_models() -> dict[str, dict]:
    """Тянет публичный каталог моделей OpenRouter с in-memory кэшем (TTL ~1ч).

    Возвращает {id: {"name", "prompt", "completion", "context_length"}}, где
    prompt/completion — float USD за ОДИН токен. Любой сбой/не-200 → последний
    успешный кэш, иначе {}. Наружу исключения не бросает (graceful).
    """
    global _models_cache
    now = time.time()
    if _models_cache is not None and (now - _models_cache[0]) < _MODELS_CACHE_TTL:
        return _models_cache[1]

    url = f"{settings.OPENROUTER_BASE_URL}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning(
                "fetch_openrouter_models: non-200 (%s) from %s", resp.status_code, url
            )
            return _models_cache[1] if _models_cache else {}

        payload = resp.json()
        data = payload.get("data") or []
        parsed: dict[str, dict] = {}
        for m in data:
            mid = m.get("id")
            if not mid:
                continue
            pricing = m.get("pricing") or {}
            try:
                prompt = float(pricing.get("prompt") or 0.0)
            except (TypeError, ValueError):
                prompt = 0.0
            try:
                completion = float(pricing.get("completion") or 0.0)
            except (TypeError, ValueError):
                completion = 0.0
            ctx = m.get("context_length")
            try:
                ctx = int(ctx) if ctx is not None else None
            except (TypeError, ValueError):
                ctx = None
            parsed[mid] = {
                "name": m.get("name") or "",
                "prompt": prompt,
                "completion": completion,
                "context_length": ctx,
            }

        _models_cache = (now, parsed)
        return parsed
    except Exception as e:  # noqa: BLE001 — graceful, не роняем вызывающих
        logger.warning("fetch_openrouter_models failed: %s", e)
        return _models_cache[1] if _models_cache else {}


def _build_option(slug: str, info: dict | None) -> dict:
    """Собрать опцию модели (значение/лейбл/оценка стоимости/контекст)."""
    if info:
        est = cost_estimate(info.get("prompt", 0.0), info.get("completion", 0.0))
        return {
            "value": slug,
            "label": info.get("name") or _prettify_slug(slug),
            "cost_usd": est["usd"],
            "cost_rub": est["rub"],
            "context_length": info.get("context_length"),
        }
    return {
        "value": slug,
        "label": _prettify_slug(slug),
        "cost_usd": None,
        "cost_rub": None,
        "context_length": None,
    }


async def get_model_options() -> list[dict]:
    """Рекомендованные модели с оценкой стоимости (порядок RECOMMENDED_MODELS).

    - live-каталог доступен → только те recommended, что РЕАЛЬНО есть в каталоге,
      с оценкой стоимости;
    - live-каталог недоступен ({}) → все recommended с cost_usd/cost_rub=None
      (не падаем, чтобы недоступность OpenRouter не ломала экран настроек).
    """
    live = await fetch_openrouter_models()
    if not live:
        return [_build_option(slug, None) for slug in RECOMMENDED_MODELS]

    options: list[dict] = []
    for slug in RECOMMENDED_MODELS:
        info = live.get(slug)
        if not info:
            continue  # recommended, но в каталоге отсутствует — не показываем
        options.append(_build_option(slug, info))
    return options


async def search_models(q: str, limit: int = 50) -> list[dict]:
    """Поиск по live-каталогу: подстрока в id (регистронезависимо), с оценкой цены.

    Пустой запрос → []. Отсекает служебные дубликаты (:free/:batch). Кап limit.
    """
    q = (q or "").strip().lower()
    if not q:
        return []

    live = await fetch_openrouter_models()
    results: list[dict] = []
    for slug, info in live.items():
        if q not in slug.lower():
            continue
        if slug.endswith(":free") or slug.endswith(":batch"):
            continue
        results.append(_build_option(slug, info))

    results.sort(key=lambda o: o["value"])
    return results[:limit]


async def is_valid_model(slug: str) -> bool:
    """Модель валидна, если присутствует в live-каталоге OpenRouter.

    FALLBACK: если каталог недоступен/пуст → разрешаем только recommended-модели,
    чтобы недоступность OpenRouter не блокировала сохранение настройки.
    """
    if not slug:
        return False
    live = await fetch_openrouter_models()
    if live:
        return slug in live
    return slug in RECOMMENDED_MODELS
