"""Built-in LLM providers: OpenAI-compatible and Stellar (custom local endpoint)."""
from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.exceptions import LLMUnavailable
from app.llm.base import ILLMProvider, LLMResult


class OpenAIProvider(ILLMProvider):
    """Any OpenAI-compatible chat completions endpoint (OpenAI, Azure, vLLM, Ollama...)."""

    provider_id = "openai"

    async def complete(self, system_prompt: str, user_message: str) -> LLMResult:
        settings = get_settings()
        timeout = settings.get("llm.request_timeout_seconds", 60)
        base_url = (self.config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        payload = {
            "model": self.config.get("model", "gpt-4o"),
            "temperature": self.config.get("temperature", 0.1),
            "max_tokens": self.config.get("max_tokens", 4096),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.config.get("api_key"):
            headers["Authorization"] = f"Bearer {self.config['api_key']}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url}/chat/completions", json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"OpenAI-compatible endpoint unavailable: {exc}") from exc

        usage = data.get("usage", {})
        return LLMResult(
            text=data["choices"][0]["message"]["content"] or "",
            model=data.get("model", payload["model"]),
            provider=self.provider_id,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw=data,
        )


class StellarProvider(ILLMProvider):
    """Custom enterprise-local endpoint.

    Request:  POST {endpoint}  body: {"systemPrompt": "...", "userMessage": "..."}
    Response: JSON - the reply text is read from config `response_field`
              (default "response"); if blank, the raw body is used.
    """

    provider_id = "stellar"

    async def complete(self, system_prompt: str, user_message: str) -> LLMResult:
        settings = get_settings()
        timeout = settings.get("llm.request_timeout_seconds", 60)
        endpoint = self.config.get("endpoint")
        if not endpoint:
            raise LLMUnavailable("Stellar provider has no endpoint configured")
        payload = {"systemPrompt": system_prompt, "userMessage": user_message}
        headers = {"Content-Type": "application/json", **(self.config.get("headers") or {})}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Stellar endpoint unavailable: {exc}") from exc

        field = self.config.get("response_field", "response")
        text = response.text
        raw: dict = {}
        if field:
            try:
                raw = response.json()
                # support nested paths like "data.output"
                node = raw
                for part in field.split("."):
                    node = node[part]
                text = str(node)
            except Exception:  # noqa: BLE001 - fall back to raw body
                text = response.text
        return LLMResult(text=text, model="stellar", provider=self.provider_id, raw=raw)


_PROVIDER_TYPES: dict[str, type[ILLMProvider]] = {
    "openai": OpenAIProvider,
    "stellar": StellarProvider,
}

_instances: dict[str, ILLMProvider] = {}


def register_provider(type_name: str, cls: type[ILLMProvider]) -> None:
    _PROVIDER_TYPES[type_name] = cls


def get_llm(provider_name: str | None = None) -> ILLMProvider:
    settings = get_settings()
    name = provider_name or settings.get("llm.active", "openai")
    if name in _instances:
        return _instances[name]
    providers = settings.section("llm.providers")
    if name not in providers:
        raise LLMUnavailable(f"LLM provider '{name}' is not configured")
    config = providers[name]
    cls = _PROVIDER_TYPES.get(config.get("type", name))
    if cls is None:
        raise LLMUnavailable(f"Unknown LLM provider type '{config.get('type')}'")
    _instances[name] = cls(config)
    return _instances[name]


def reset_providers() -> None:
    _instances.clear()
