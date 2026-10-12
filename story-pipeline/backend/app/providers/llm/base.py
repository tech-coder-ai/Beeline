"""LLM provider contract. Application code depends on this, never on Ollama directly."""
from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.errors import ProviderError

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    name: str

    async def generate_text(self, prompt: str, system_prompt: str | None = None) -> str: ...

    async def generate_json(self, prompt: str, schema: dict[str, Any], system_prompt: str | None = None) -> dict[str, Any]: ...

    async def health(self) -> dict[str, Any]: ...


async def generate_model(llm: LLMProvider, prompt: str, model: type[T], *, system_prompt: str | None = None,
                         repair_attempts: int = 2) -> T:
    """Ask for JSON matching `model`, validate with Pydantic, re-prompt with the errors if invalid.

    Constrained decoding makes the JSON *well-formed*; validation makes it *correct*.
    You need both.
    """
    schema = model.model_json_schema()
    last_error = ""
    for attempt in range(repair_attempts + 1):
        p = prompt if not last_error else (
            f"{prompt}\n\nYour previous answer was invalid:\n{last_error}\nReturn corrected JSON only."
        )
        data = await llm.generate_json(p, schema, system_prompt=system_prompt)
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            last_error = str(exc)[:2000]
    raise ProviderError(f"{llm.name} returned invalid {model.__name__} after {repair_attempts + 1} attempts: {last_error[:500]}")
