"""LLM provider abstraction.

Providers are selected via config (llm.active). Each provider takes a system
prompt + user message and returns text. JSON-mode helpers parse structured
output with graceful degradation.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResult:
    text: str
    model: str = ""
    provider: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: dict = field(default_factory=dict)


class ILLMProvider(ABC):
    provider_id: str = "base"

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def complete(self, system_prompt: str, user_message: str) -> LLMResult: ...

    async def complete_json(self, system_prompt: str, user_message: str) -> tuple[dict, LLMResult]:
        """Request JSON output and parse it defensively."""
        result = await self.complete(
            system_prompt + "\n\nRespond with valid JSON only. No prose, no markdown fences.",
            user_message,
        )
        return parse_json_loosely(result.text), result


def parse_json_loosely(text: str) -> dict:
    """Extract the first JSON object from LLM output, tolerating fences/prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {}
