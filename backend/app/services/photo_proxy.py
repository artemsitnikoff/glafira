"""Прокси-кэш фото кандидата с hh CDN (img.hhcdn.ru).

Фото на hh публичны, но URL содержит истекающий токен → мы кэшируем БАЙТЫ
по хешу src на диск при первом показе. `<img src>` не шлёт Authorization,
поэтому прокси публичный (см. /api/v1/public/photo) — токен hh здесь НЕ нужен
и НЕ передаётся (фото отдаётся анонимно).

SSRF-гард: только домены hh.ru / hhcdn.ru. Любая неожиданная ошибка → 404
(силуэт на фронте), НИКОГДА 500.
"""

import asyncio
import hashlib
import logging
from urllib.parse import quote, urlparse

import httpx
from fastapi import Response
from fastapi.responses import FileResponse

from ..core.errors import NotFoundError, ValidationError
from .integrations.net_guard import validate_outbound_url
from .storage import storage_root

logger = logging.getLogger(__name__)

# Разрешённые домены фото (SSRF). img.hhcdn.ru покрывается суффиксом hhcdn.ru.
PHOTO_ALLOWED_DOMAINS = ("hh.ru", "hhcdn.ru")


def extract_hh_photo_url(photo) -> str | None:
    """Достаёт URL фото из hh-объекта photo, устойчиво к разным структурам:
    dict {medium/small} ИЛИ {'500','100','40',...} ИЛИ плоская строка-URL."""
    if not photo:
        return None
    if isinstance(photo, str):
        return photo if photo.startswith("http") else None
    if isinstance(photo, dict):
        # приоритет по убыванию размера/предпочтения
        for k in ("medium", "500", "100", "small", "40"):
            v = photo.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        # фолбэк: первое строковое значение-URL (кроме id)
        for k, v in photo.items():
            if k == "id":
                continue
            if isinstance(v, str) and v.startswith("http"):
                return v
    return None


def build_photo_proxy_url(photo) -> str | None:
    """hh-объект photo → публичный прокси-URL `/api/v1/public/photo?src=<real_url>`.

    Возвращает None, если фото нет/URL не извлечён. Реальный URL hh идёт в src
    закодированным (safe='') — при показе фронт дёргает публичный прокси, тот
    кэширует байты (токен hh истекает, прямую ссылку хранить нельзя)."""
    real_url = extract_hh_photo_url(photo)
    if not real_url:
        return None
    return f"/api/v1/public/photo?src={quote(real_url, safe='')}"


async def serve_hh_photo(src: str) -> Response:
    """Пуленепробиваемый прокси-кэш фото с hh. SSRF-гард → 400; всё прочее → 404.

    1) SSRF-гард (ValidationError → 400, вне try — намеренно, чтобы SSRF был 400).
    2) Дисковый кэш по sha1(src) (best-effort чтение).
    3) Скачать БЕЗ Authorization (фото публично, токен не утекает); не-200 /
       не-image / >3МБ → 404.
    4) Best-effort запись в кэш + отдать БАЙТЫ напрямую.

    Любая неожиданная ошибка → logger.exception + 404 (силуэт), НИКОГДА 500.
    """
    # SSRF-гард (ValidationError → 400). Вне try — намеренно: SSRF = 400, а не 404.
    await validate_outbound_url(src, allowed_domains=PHOTO_ALLOWED_DOMAINS)

    key = hashlib.sha1(src.encode("utf-8")).hexdigest()
    cache_dir = storage_root / "photos"
    cache_path = cache_dir / key
    ct_path = cache_dir / f"{key}.ct"

    # 1) Кэш-чтение (best-effort: сбой диска не ломает — идём качать заново)
    try:
        if cache_path.exists():
            media_type = "image/jpeg"
            if ct_path.exists():
                media_type = (ct_path.read_text().strip() or "image/jpeg")
            return FileResponse(cache_path, media_type=media_type,
                                headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        logger.exception("[photo] cache read failed")  # игнор, качаем заново

    # 2) Скачать с hh (БЕЗ Authorization — фото публично, токен не утекает)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True) as client:
            resp = await client.get(src)
        media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip().lower() or "image/jpeg"
        if resp.status_code != 200 or not media_type.startswith("image/") or len(resp.content) > 3 * 1024 * 1024:
            raise NotFoundError("Фото")
        content = resp.content
    except (ValidationError, NotFoundError):
        raise
    except Exception:
        logger.exception("[photo] fetch failed host=%s", (urlparse(src).hostname or "?"))
        raise NotFoundError("Фото")

    # 3) Дисковый кэш — BEST-EFFORT (сбой НЕ ломает раздачу)
    try:
        def _write() -> None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(content)
            ct_path.write_text(media_type)
        await asyncio.to_thread(_write)
    except Exception:
        logger.exception("[photo] cache write failed")  # игнор — всё равно отдаём ниже

    # 4) Отдать БАЙТЫ напрямую (надёжно — не зависит от файла на диске)
    return Response(content=content, media_type=media_type,
                    headers={"Cache-Control": "public, max-age=86400"})
