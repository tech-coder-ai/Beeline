"""Publishing contract."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class UploadResult:
    video_id: str
    url: str


class Publisher(Protocol):
    name: str

    def find_existing(self, attempt_id: str) -> UploadResult | None:
        """Reconcile: did a previous (maybe timed-out) attempt actually create a video?"""
        ...

    def upload(self, video: Path, thumbnail: Path | None, metadata: dict[str, Any], attempt_id: str) -> UploadResult: ...

    def processing_status(self, video_id: str) -> str: ...

    def health(self) -> dict[str, Any]: ...
