"""Клиент для взаимодействия с Claude API через OpenRouter"""

import asyncio
import json
import re
import httpx
from ...config import settings
from ...core.errors import GlafiraParseError


# Regex to clean markdown fences from JSON response
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Retry configuration constants
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
MAX_RETRY_ATTEMPTS = 4
BASE_BACKOFF_DELAY = 2.0


async def _make_openrouter_request(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    """Makes request with exponential backoff retry on transient errors"""
    for attempt in range(MAX_RETRY_ATTEMPTS):
        response = await client.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload
        )

        # Success case
        if response.status_code == 200:
            return response

        # Final attempt - don't retry, just return
        if attempt == MAX_RETRY_ATTEMPTS - 1:
            return response

        # Check if status code is retryable
        if response.status_code not in RETRYABLE_STATUS_CODES:
            return response

        # Calculate backoff delay
        backoff_delay = BASE_BACKOFF_DELAY * (2.5 ** attempt)

        # Check for Retry-After header and respect it
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            backoff_delay = max(backoff_delay, float(retry_after))

        await asyncio.sleep(backoff_delay)

    return response


async def call_json(*, system: str, user: str, max_tokens: int = 2048) -> dict:
    """Call Claude API via OpenRouter expecting JSON response"""
    if not settings.OPENROUTER_API_KEY:
        raise GlafiraParseError(details={"reason": "OPENROUTER_API_KEY not configured"})

    async with httpx.AsyncClient() as client:
        payload = {
            "model": settings.GLAFIRA_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }

        response = await _make_openrouter_request(client, payload)

        if response.status_code != 200:
            raise GlafiraParseError(details={
                "reason": f"OpenRouter HTTP {response.status_code}",
                "raw": response.text[:500]
            })

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise GlafiraParseError(details={
                "reason": "No choices in response",
                "raw": str(data)[:500]
            })

        # Extract text from response
        text = choices[0].get("message", {}).get("content", "")
        finish_reason = choices[0].get("finish_reason")

    # Обрезка по лимиту токенов → JSON заведомо невалиден, даём явную причину вместо JSONDecodeError
    if finish_reason == "length":
        raise GlafiraParseError(details={
            "reason": "Ответ обрезан по лимиту токенов (finish_reason=length) — увеличьте max_tokens",
            "raw": text[-300:]
        })

    # Clean markdown fences
    cleaned = _FENCE_RE.sub("", text).strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        raise GlafiraParseError(details={"raw": text[:500], "reason": str(e)})


async def call_text(*, system: str, user: str, max_tokens: int = 1024) -> str:
    """Call Claude API via OpenRouter expecting text response"""
    if not settings.OPENROUTER_API_KEY:
        raise GlafiraParseError(details={"reason": "OPENROUTER_API_KEY not configured"})

    async with httpx.AsyncClient() as client:
        payload = {
            "model": settings.GLAFIRA_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }

        response = await _make_openrouter_request(client, payload)

        if response.status_code != 200:
            raise GlafiraParseError(details={
                "reason": f"OpenRouter HTTP {response.status_code}",
                "raw": response.text[:500]
            })

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise GlafiraParseError(details={
                "reason": "No choices in response",
                "raw": str(data)[:500]
            })

        # Extract text from response
        return choices[0].get("message", {}).get("content", "")