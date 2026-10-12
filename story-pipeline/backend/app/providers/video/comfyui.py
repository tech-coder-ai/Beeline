"""ComfyUI image-to-video adapter (e.g. Wan 2.2 14B I2V).

The workflow (comfyui-workflows/<models.video.workflow>) is an API-format export containing:
  "{{image}}"  start frame (uploaded)      "{{prompt}}" / "{{negative_prompt}}"
  "{{seed}}"   "{{width}}" "{{height}}"    "{{frames}}"  "{{fps}}"
and ending in a node that saves an .mp4/.webm (core SaveVideo or VHS_VideoCombine).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import VideoModelCfg
from app.providers.comfy_client import VIDEO_EXT, ComfyClient
from app.providers.errors import ProviderError
from app.providers.video.base import VideoRequest


class ComfyUIVideoProvider:
    name = "comfyui-video"

    def __init__(self, cfg: VideoModelCfg, workflow_dir: Path):
        self.cfg = cfg
        self.path = workflow_dir / cfg.workflow
        self.comfy = ComfyClient(cfg.base_url, cfg.timeout_seconds)
        # The workflow file's hash is part of the model identity: editing it re-animates scenes.
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()[:10] if self.path.exists() else "missing"
        self.model = f"{cfg.workflow}@{digest}"

    def generate(self, req: VideoRequest) -> bytes:
        if not self.path.exists():
            raise ProviderError(f"video workflow missing: {self.path}")
        wf = json.loads(self.path.read_text())
        data, _ = self.comfy.run(wf, {"prompt": req.prompt, "negative_prompt": req.negative_prompt, "seed": req.seed,
                                      "width": req.width, "height": req.height, "frames": req.frames,
                                      "fps": req.fps}, {"image": req.image_path}, want=VIDEO_EXT)
        return data

    def free(self) -> None:
        self.comfy.free()

    def health(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"ok": False, "detail": f"workflow file missing: {self.path.name}"}
        try:
            stats = self.comfy.system_stats()
            dev = (stats.get("devices") or [{}])[0]
            vram = dev.get("vram_total")
            gb = f", {vram / 2**30:.0f} GB VRAM" if vram else ""
            return {"ok": True, "detail": f"{self.cfg.workflow} on {dev.get('name', 'GPU')}{gb}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"ComfyUI unreachable: {exc}"}
