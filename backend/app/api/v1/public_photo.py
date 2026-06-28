"""Публичный прокси фото кандидата (БЕЗ авторизации).

`<img src>` не шлёт Authorization → этот роутер монтируется под /public БЕЗ
auth-dependency (как public_surveys). SSRF-гард: только домены hh.ru / hhcdn.ru.
Логика 1:1 как /smart/auto/photo — общий хелпер serve_hh_photo. Никогда не 500:
при любом сбое 404 → силуэт на фронте.
"""

from fastapi import APIRouter, Query, Response

from ...services.photo_proxy import serve_hh_photo

router = APIRouter()


@router.get("/photo")
async def get_public_candidate_photo(src: str = Query(...)) -> Response:
    """Прокси-кэш фото кандидата с hh (SSRF-гард, без токена, публичный).

    Путь: /api/v1/public/photo?src=<url>. SSRF → 400; всё прочее → 404 (силуэт)."""
    return await serve_hh_photo(src)
