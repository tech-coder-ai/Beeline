"""Pretends to upload: writes a receipt next to the project. Same contract, no credentials, no quota."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.youtube.base import UploadResult


class DryRunPublisher:
    name = "dry_run"

    def __init__(self, receipts_dir: Path):
        self.receipts_dir = receipts_dir

    def _receipt(self, attempt_id: str) -> Path:
        return self.receipts_dir / f"{attempt_id}.json"

    def find_existing(self, attempt_id: str) -> UploadResult | None:
        p = self._receipt(attempt_id)
        if p.exists():
            d = json.loads(p.read_text())
            return UploadResult(d["video_id"], d["url"])
        return None

    def upload(self, video: Path, thumbnail: Path | None, metadata: dict[str, Any], attempt_id: str) -> UploadResult:
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        vid = f"dryrun_{attempt_id[-10:]}"
        result = UploadResult(vid, f"https://www.youtube.com/watch?v={vid}")
        self._receipt(attempt_id).write_text(json.dumps({
            "video_id": vid, "url": result.url, "video": str(video), "thumbnail": str(thumbnail) if thumbnail else None,
            "metadata": metadata, "uploaded_at": datetime.now(UTC).isoformat(),
        }, indent=2, ensure_ascii=False))
        return result

    def processing_status(self, video_id: str) -> str:
        return "succeeded"

    def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "dry run - receipts written locally, nothing leaves this machine"}
