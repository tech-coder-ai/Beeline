"""ComfyUI image adapter.

Workflows are exported from ComfyUI with "Save (API Format)" into comfyui-workflows/.
Tokens filled by the adapter: "{{prompt}}" "{{negative_prompt}}" "{{seed}}" "{{width}}" "{{height}}"
and "{{reference_image}}" (uploaded first; feed it to IP-Adapter / reference conditioning).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import ImageCfg
from app.providers.comfy_client import IMAGE_EXT, ComfyClient, fill_tokens  # noqa: F401  (fill_tokens re-exported)
from app.providers.errors import ProviderError
from app.providers.images.base import ImageRequest


class ComfyUIProvider:
    name = "comfyui"

    def __init__(self, cfg: ImageCfg, workflow_dir: Path):
        self.cfg = cfg
        self.workflow_dir = workflow_dir
        self.model = ",".join(f"{k}={v}" for k, v in cfg.workflows.items())
        self.comfy = ComfyClient(cfg.base_url, cfg.timeout_seconds)

    def _workflow(self, kind: str) -> dict:
        fname = self.cfg.workflows.get(kind)
        if not fname:
            raise ProviderError(f"No ComfyUI workflow configured for '{kind}' (models.image.workflows)")
        path = self.workflow_dir / fname
        if not path.exists():
            raise ProviderError(f"ComfyUI workflow file missing: {path}")
        return json.loads(path.read_text())

    def generate(self, req: ImageRequest) -> bytes:
        wf = self._workflow(req.kind)
        uploads = {}
        if "{{reference_image}}" in json.dumps(wf):
            if not req.reference_images:
                raise ProviderError(f"workflow for {req.kind} expects a reference image but none was given")
            uploads["reference_image"] = req.reference_images[0]
        data, _ = self.comfy.run(wf, {"prompt": req.prompt, "negative_prompt": req.negative_prompt, "seed": req.seed,
                                      "width": req.width, "height": req.height}, uploads, want=IMAGE_EXT)
        return data

    def health(self) -> dict[str, Any]:
        try:
            stats = self.comfy.system_stats()
            missing = [f for f in self.cfg.workflows.values() if not (self.workflow_dir / f).exists()]
            detail = stats.get("system", {}).get("comfyui_version", "running")
            if missing:
                detail += f"; missing workflow files {missing}"
            return {"ok": not missing, "detail": detail}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"unreachable: {exc}"}
