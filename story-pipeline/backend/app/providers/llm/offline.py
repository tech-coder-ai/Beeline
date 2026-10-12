"""The 'no LLM' provider. Every call raises ProviderUnavailable so services use their deterministic fallbacks."""
from __future__ import annotations

from typing import Any

from app.providers.errors import ProviderUnavailable


class OfflineProvider:
    name = "offline"

    async def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        raise ProviderUnavailable("LLM provider is 'offline'")

    async def generate_json(self, prompt: str, schema: dict[str, Any], system_prompt: str | None = None) -> dict[str, Any]:
        raise ProviderUnavailable("LLM provider is 'offline'")

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "offline mode - deterministic fallbacks, no translation"}
