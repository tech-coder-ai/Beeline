"""Adapter for any OpenAI-compatible /v1/chat/completions server (vLLM, LM Studio, llama.cpp server...)."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import LLMCfg
from app.providers.errors import ProviderError


class OpenAICompatibleProvider:
    def __init__(self, cfg: LLMCfg):
        self.cfg = cfg
        self.name = f"openai:{cfg.model}"
        self.base_url = cfg.base_url.rstrip("/")

    async def _complete(self, prompt: str, system_prompt: str | None, schema: dict | None = None) -> str:
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [
            {"role": "user", "content": prompt}]
        body: dict[str, Any] = {"model": self.cfg.model, "messages": messages, "temperature": self.cfg.temperature}
        if schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": schema.get("title", "result"), "schema": schema}}
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                r = await client.post(f"{self.base_url}/v1/chat/completions", json=body, headers=headers)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderError(f"LLM server unreachable: {exc}", transient=True) from exc
        if r.status_code >= 500 or r.status_code == 429:
            raise ProviderError(f"LLM server error {r.status_code}", transient=True)
        if r.status_code >= 400:
            raise ProviderError(f"LLM request rejected {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]

    async def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return await self._complete(prompt, system_prompt)

    async def generate_json(self, prompt: str, schema: dict[str, Any], system_prompt: str | None = None) -> dict[str, Any]:
        raw = await self._complete(prompt, system_prompt, schema)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"non-JSON response: {raw[:200]}", transient=True) from exc

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/v1/models")
            return {"ok": r.status_code == 200, "detail": f"HTTP {r.status_code}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"unreachable: {exc}"}
