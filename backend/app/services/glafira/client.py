"""Клиент для взаимодействия с Claude API через OpenRouter"""

import asyncio
import json
import re
import httpx
from ...config import settings
from ...core.errors import GlafiraParseError, OpenRouterNotConfiguredError


# Functions to clean markdown fences from JSON response
def _clean_markdown_fences(text: str) -> str:
    """Remove markdown code fence blocks from beginning and end of text"""
    # Remove leading ```json or ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    # Remove trailing ```
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned

# Retry configuration constants
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
MAX_RETRY_ATTEMPTS = 4
BASE_BACKOFF_DELAY = 2.0

# HTTP timeout configuration
_HTTP_TIMEOUT = httpx.Timeout(
    connect=10.0,  # Connection timeout
    read=120.0,    # Read timeout (generous for LLM scoring)
    write=10.0,    # Write timeout
    pool=10.0      # Pool timeout
)


async def _make_openrouter_request(client: httpx.AsyncClient, payload: dict, api_key: str) -> httpx.Response:
    """Makes request with exponential backoff retry on transient errors and network failures"""
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            response = await client.post(
                f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
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

        except httpx.HTTPError:
            # Network error - retry with backoff, but re-raise on final attempt
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                raise

        # Calculate backoff delay
        backoff_delay = BASE_BACKOFF_DELAY * (2.5 ** attempt)

        # Check for Retry-After header and respect it (only if response exists)
        if 'response' in locals():
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                backoff_delay = max(backoff_delay, float(retry_after))

        await asyncio.sleep(backoff_delay)

    return response


async def call_json(*, system: str, user: str, api_key: str, max_tokens: int = 2048, model: str | None = None) -> dict:
    """Call Claude API via OpenRouter expecting JSON response"""
    if not api_key:
        raise OpenRouterNotConfiguredError()

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        payload = {
            "model": model or settings.GLAFIRA_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }

        try:
            response = await _make_openrouter_request(client, payload, api_key)
        except httpx.HTTPError as e:
            raise GlafiraParseError(details={
                "reason": f"Сетевая ошибка при обращении к OpenRouter: {type(e).__name__}"
            })

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
    cleaned = _clean_markdown_fences(text)

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        raise GlafiraParseError(details={"raw": text[:500], "reason": str(e)})


async def call_text(*, system: str, user: str, api_key: str, max_tokens: int = 1024, model: str | None = None) -> str:
    """Call Claude API via OpenRouter expecting text response"""
    if not api_key:
        raise OpenRouterNotConfiguredError()

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        payload = {
            "model": model or settings.GLAFIRA_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }

        try:
            response = await _make_openrouter_request(client, payload, api_key)
        except httpx.HTTPError as e:
            raise GlafiraParseError(details={
                "reason": f"Сетевая ошибка при обращении к OpenRouter: {type(e).__name__}"
            })

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