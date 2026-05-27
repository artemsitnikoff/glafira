"""Клиент для взаимодействия с Claude API через OpenRouter"""

import json
import re
import httpx
from ...config import settings
from ...core.errors import GlafiraParseError


# Regex to clean markdown fences from JSON response
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


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

        response = await client.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload
        )

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

        response = await client.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload
        )

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