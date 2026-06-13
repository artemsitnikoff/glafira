"""Модуль транскрибации и анализа звонков"""

import asyncio
import base64
import json
import logging
from typing import Dict, Any, Optional

import httpx

from ...config import settings
from ...core.errors import GlafiraParseError
from .client import call_json

logger = logging.getLogger(__name__)

# Промпт для диаризации (скопирован из ArkadyJarvis)
VOICE_TRANSCRIBE_PROMPT = """Транскрибируй голосовое сообщение на русском языке.
Если говорит один человек — всё помечай как S1.
Если несколько — определи разных спикеров: S1, S2, S3...
Один и тот же голос — один и тот же номер.
Не перефразируй, сохраняй пунктуацию.

Для каждого сегмента укажи start и end в секундах от начала
аудио (число с точностью до 0.1 сек). Новый сегмент — при смене
спикера или при паузе больше 2 секунд.

Верни только JSON:
{
  "speakers_count": <число>,
  "segments": [
    {"speaker": "S1", "start": 0.0, "end": 3.2, "text": "..."},
    {"speaker": "S2", "start": 3.5, "end": 7.1, "text": "..."}
  ]
}"""

# Промпт для анализа звонка (адаптирован под рекрутинг)
CALL_ANALYSIS_PROMPT = """Ты — тренер по рекрутингу. Ниже расшифровка звонка рекрутера с кандидатом. Сделай разбор звонка.

---

## Расшифровка звонка

{transcript}

---

## Что нужно

Сформируй компактный разбор звонка. Лимит — 4–6 строк. Ответь СТРОГО таким форматом JSON:

{
  "summary": "<одно предложение — о чём разговор, какой итог>",
  "hint": "<что рекрутёр сделал правильно или что упустил, 1–2 коротких пункта>",
  "hint_tone": "<warn или good>"
}

## Правила

- Опирайся на контекст рекрутинга: выяснение потребностей кандидата, презентация вакансии, назначение встречи, обратная связь
- Если звонок короткий, не информативный, гудки — "summary": "Короткий звонок (N сек), сути нет"
- НЕ пиши прелюдий, ТОЛЬКО JSON
- Будь конкретен: что выяснил, что презентовал, следующий шаг
- hint_tone: "warn" если есть упущения, "good" если всё хорошо

## Типы звонков

Классифицируй правильно:
- **Звонок кандидату по вакансии** → анализируй как рекрутинговый звонок
- **Входящий от кандидата** → анализируй интерес и качество обработки
- **Не рекрутинг** (поставщики, спам, ошибка номером) → "summary": "Не рекрутинговый звонок", "hint": "Корректно обработан", "hint_tone": "good"

НЕ выдумывай несуществующие детали из-за ошибок автоматической расшифровки."""


async def transcribe_audio(audio_bytes: bytes, audio_format: str = 'mp3') -> Dict[str, Any]:
    """Транскрибация аудио через Gemini с диаризацией спикеров.

    Args:
        audio_bytes: Байты аудиофайла
        audio_format: Формат аудио (mp3, wav, ogg и т.д.)

    Returns:
        dict: {
            "success": bool,
            "full_text": str,
            "segments": List[dict],
            "speakers_count": int,
            "error": Optional[str]
        }
    """
    if not settings.OPENROUTER_API_KEY:
        return {
            "success": False,
            "full_text": "",
            "segments": [],
            "speakers_count": 0,
            "error": "OPENROUTER_API_KEY не настроен"
        }

    # Кодируем аудио в base64
    audio_b64 = base64.b64encode(audio_bytes).decode()

    payload = {
        "model": settings.GLAFIRA_TRANSCRIBE_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VOICE_TRANSCRIBE_PROMPT},
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_format}},
            ],
        }],
        "response_format": {"type": "json_object"},
        "max_tokens": 60000,
    }

    # Ретрай с экспоненциальным backoff
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
        except Exception as e:
            logger.error("Transcribe HTTP error attempt %d: %s", attempt + 1, e)
            if attempt == 1:  # Последняя попытка
                return {
                    "success": False,
                    "full_text": "",
                    "segments": [],
                    "speakers_count": 0,
                    "error": f"Сетевая ошибка: {str(e)}"
                }
            await asyncio.sleep(5)
            continue

        if response.status_code == 429 or (500 <= response.status_code < 600):
            if attempt == 1:
                return {
                    "success": False,
                    "full_text": "",
                    "segments": [],
                    "speakers_count": 0,
                    "error": f"OpenRouter {response.status_code}: {response.text[:200]}"
                }
            logger.warning("Transcribe retry %d after retryable %d", attempt + 1, response.status_code)
            await asyncio.sleep(5)
            continue
        elif response.status_code != 200:
            return {
                "success": False,
                "full_text": "",
                "segments": [],
                "speakers_count": 0,
                "error": f"OpenRouter {response.status_code}: {response.text[:200]}"
            }

        # Парсинг ответа
        try:
            data = response.json()
        except Exception as e:
            return {
                "success": False,
                "full_text": "",
                "segments": [],
                "speakers_count": 0,
                "error": f"Невалидный JSON от OpenRouter: {e}"
            }

        # Проверка ошибок на уровне choices
        if not data.get("choices"):
            error_info = data.get("error", {})
            error_msg = error_info.get("message", "Нет choices в ответе")
            return {
                "success": False,
                "full_text": "",
                "segments": [],
                "speakers_count": 0,
                "error": f"OpenRouter: {error_msg}"
            }

        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason", "")
        message = choice.get("message") or {}
        content = message.get("content")
        refusal = message.get("refusal")

        if refusal:
            return {
                "success": False,
                "full_text": "",
                "segments": [],
                "speakers_count": 0,
                "error": f"Модель отказала: {refusal[:200]}"
            }

        if not content or not content.strip():
            hint = ""
            if finish_reason == "length":
                hint = " (ответ обрезан по лимиту токенов)"
            elif finish_reason == "content_filter":
                hint = " (сработал контент-фильтр)"
            return {
                "success": False,
                "full_text": "",
                "segments": [],
                "speakers_count": 0,
                "error": f"Пустой ответ от модели{hint}"
            }

        # Парсинг JSON ответа
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            hint = ""
            if finish_reason == "length":
                hint = " (возможно, ответ обрезан)"
            return {
                "success": False,
                "full_text": "",
                "segments": [],
                "speakers_count": 0,
                "error": f"Не удалось разобрать JSON: {e}{hint}"
            }

        segments = parsed.get("segments") or []

        # Санитизация временных меток
        for seg in segments:
            seg["start"] = max(0.0, float(seg.get("start", 0) or 0))
            seg["end"] = max(seg["start"], float(seg.get("end", seg["start"]) or seg["start"]))

        # Формируем полный текст
        full_text = _build_full_text(segments)
        if not full_text:
            return {
                "success": False,
                "full_text": "",
                "segments": [],
                "speakers_count": 0,
                "error": "Пустая расшифровка — возможно, тишина или слишком тихо"
            }

        return {
            "success": True,
            "full_text": full_text,
            "segments": segments,
            "speakers_count": int(parsed.get("speakers_count") or 0),
            "error": None
        }

    # Не должен достигаться
    return {
        "success": False,
        "full_text": "",
        "segments": [],
        "speakers_count": 0,
        "error": "Неожиданное завершение ретрай-цикла"
    }


def _build_full_text(segments: list) -> str:
    """Построение полного текста из сегментов с таймстампами"""
    parts = []
    for seg in segments:
        speaker = seg.get("speaker", "S?")
        start = float(seg.get("start", 0))
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        time_str = f"{int(start) // 60}:{int(start) % 60:02d}"
        parts.append(f"{speaker} [{time_str}]: {text}")
    return "\n\n".join(parts)


async def analyze_call(transcript: str) -> Dict[str, Any]:
    """Анализ расшифровки звонка через LLM.

    Args:
        transcript: Полная расшифровка звонка

    Returns:
        dict: {
            "summary": str,
            "hint": str,
            "hint_tone": str  # "warn" or "good"
        }
        При ошибке возвращает None
    """
    if not transcript or not transcript.strip():
        return None

    # Используем существующий клиент проекта
    try:
        system_prompt = "Ты — эксперт по рекрутингу. Анализируй звонки рекрутеров с кандидатами."
        user_prompt = CALL_ANALYSIS_PROMPT.format(transcript=transcript)

        result = await call_json(
            system=system_prompt,
            user=user_prompt,
            max_tokens=1000
        )

        # Валидация результата
        if not isinstance(result, dict):
            return None

        summary = result.get("summary", "").strip()
        hint = result.get("hint", "").strip()
        hint_tone = result.get("hint_tone", "").strip()

        if not summary:
            return None

        # Валидация hint_tone
        if hint_tone not in ("warn", "good"):
            hint_tone = "good"

        return {
            "summary": summary,
            "hint": hint,
            "hint_tone": hint_tone
        }

    except (GlafiraParseError, Exception) as e:
        logger.error("Call analysis failed: %s", e)
        return None