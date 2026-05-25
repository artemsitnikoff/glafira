"""Клиент для взаимодействия с Claude API"""

import json
import re
from anthropic import AsyncAnthropic
from ...config import settings
from ...core.errors import GlafiraParseError


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    """Get Claude API client instance"""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# Regex to clean markdown fences from JSON response
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


async def call_json(*, system: str, user: str, max_tokens: int = 2048) -> dict:
    """Call Claude API expecting JSON response"""
    client = get_client()

    response = await client.messages.create(
        model=settings.GLAFIRA_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    # Extract text from response
    text = response.content[0].text if response.content else ""

    # Clean markdown fences
    cleaned = _FENCE_RE.sub("", text).strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        raise GlafiraParseError(details={"raw": text[:500], "reason": str(e)})


async def call_text(*, system: str, user: str, max_tokens: int = 1024) -> str:
    """Call Claude API expecting text response"""
    client = get_client()

    response = await client.messages.create(
        model=settings.GLAFIRA_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    return response.content[0].text if response.content else ""