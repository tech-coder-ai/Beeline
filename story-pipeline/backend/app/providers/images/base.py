"""Image generation contract (separate from the LLM contract - different capability)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol


@dataclass
class ImageRequest:
    kind: Literal["character_sheet", "scene"]
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int
    reference_images: list[Path] = field(default_factory=list)
    # Structured hints - real models ignore these; the placeholder renderer uses them.
    hints: dict[str, Any] = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str
    model: str

    def generate(self, req: ImageRequest) -> bytes:
        """Return PNG bytes."""
        ...

    def health(self) -> dict[str, Any]: ...
