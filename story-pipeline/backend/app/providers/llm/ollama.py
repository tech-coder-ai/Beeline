"""Ollama adapter using structured outputs (format=<JSON schema>)."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import LLMCfg
from app.providers.errors import ProviderError


class OllamaProvider:
    def __init__(self, cfg: LLMCfg):
        self.cfg = cfg
        self.name = f"ollama:{cfg.model}"
        self.base_url = cfg.base_url.rstrip("/")

    async def _chat(self, prompt: str, system_prompt: str | None, fmt: Any = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.cfg.keep_alive,  # "0" frees VRAM right away for the image/video models
            "options": {"temperature": self.cfg.temperature},
        }
        if fmt is not None:
            body["format"] = fmt
        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
                r = await client.post(f"{self.base_url}/api/chat", json=body)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderError(f"Ollama unreachable at {self.base_url}: {exc}", transient=True) from exc
        if r.status_code == 404:
            raise ProviderError(f"Ollama model '{self.cfg.model}' not found - run `ollama pull {self.cfg.model}`")
        if r.status_code >= 500:
            raise ProviderError(f"Ollama error {r.status_code}: {r.text[:300]}", transient=True)
        if r.status_code >= 400:
            raise ProviderError(f"Ollama rejected request {r.status_code}: {r.text[:300]}")
        return r.json()["message"]["content"]

    async def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return await self._chat(prompt, system_prompt)

    async def generate_json(self, prompt: str, schema: dict[str, Any], system_prompt: str | None = None) -> dict[str, Any]:
        raw = await self._chat(prompt, system_prompt, fmt=schema)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Ollama returned non-JSON: {raw[:200]}", transient=True) from exc

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            ok = any(m == self.cfg.model or m.split(":")[0] == self.cfg.model for m in models)
            return {"ok": ok, "detail": "model installed" if ok else f"model not installed; have {models}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"unreachable: {exc}"}
