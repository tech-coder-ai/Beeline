"""Image-to-video contract: animate one approved still into a short clip."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class VideoRequest:
    image_path: Path
    prompt: str            # what moves
    negative_prompt: str
    seed: int
    width: int
    height: int
    frames: int
    fps: int


class VideoProvider(Protocol):
    name: str
    model: str

    def generate(self, req: VideoRequest) -> bytes:
        """Return an encoded video file (mp4/webm)."""
        ...

    def free(self) -> None:
        """Release GPU memory after a batch (no-op if not applicable)."""
        ...

    def health(self) -> dict[str, Any]: ...
