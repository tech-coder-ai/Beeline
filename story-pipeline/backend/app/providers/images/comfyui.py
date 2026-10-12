"""ComfyUI adapter.

Workflows are exported from ComfyUI with "Save (API Format)" into
comfyui-workflows/. Inside the JSON, use these tokens and the adapter fills them:

    "{{prompt}}"  "{{negative_prompt}}"  "{{seed}}"  "{{width}}"  "{{height}}"
    "{{reference_image}}"   (uploaded first; use it in a LoadImage node feeding IP-Adapter etc.)

A token that is the *whole* string value is replaced with the typed value
(so "{{seed}}" becomes an int); tokens inside longer strings are interpolated.
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import ImageCfg
from app.providers.errors import ProviderError
from app.providers.images.base import ImageRequest


def fill_tokens(node: Any, values: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        return {k: fill_tokens(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [fill_tokens(v, values) for v in node]
    if isinstance(node, str):
        for key, val in values.items():
            token = "{{" + key + "}}"
            if node == token:
                return val
            if token in node:
                node = node.replace(token, str(val))
    return node


class ComfyUIProvider:
    name = "comfyui"

    def __init__(self, cfg: ImageCfg, workflow_dir: Path):
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")
        self.workflow_dir = workflow_dir
        self.model = ",".join(f"{k}={v}" for k, v in cfg.workflows.items())
        self.client_id = uuid.uuid4().hex

    def _workflow(self, kind: str) -> dict:
        fname = self.cfg.workflows.get(kind)
        if not fname:
            raise ProviderError(f"No ComfyUI workflow configured for '{kind}' (models.image.workflows)")
        path = self.workflow_dir / fname
        if not path.exists():
            raise ProviderError(f"ComfyUI workflow file missing: {path}")
        return json.loads(path.read_text())

    def _upload(self, client: httpx.Client, image: Path) -> str:
        with image.open("rb") as f:
            r = client.post(f"{self.base_url}/upload/image", files={"image": (image.name, f, "image/png")},
                            data={"overwrite": "true"})
        r.raise_for_status()
        return r.json()["name"]

    def generate(self, req: ImageRequest) -> bytes:
        wf = self._workflow(req.kind)
        try:
            with httpx.Client(timeout=60) as client:
                values: dict[str, Any] = {
                    "prompt": req.prompt, "negative_prompt": req.negative_prompt, "seed": req.seed,
                    "width": req.width, "height": req.height,
                }
                if "{{reference_image}}" in json.dumps(wf):
                    if not req.reference_images:
                        raise ProviderError(f"workflow for {req.kind} expects a reference image but none was given")
                    values["reference_image"] = self._upload(client, req.reference_images[0])
                graph = fill_tokens(copy.deepcopy(wf), values)
                r = client.post(f"{self.base_url}/prompt", json={"prompt": graph, "client_id": self.client_id})
                if r.status_code == 400:
                    raise ProviderError(f"ComfyUI rejected workflow: {r.text[:500]}")
                r.raise_for_status()
                prompt_id = r.json()["prompt_id"]
                deadline = time.monotonic() + self.cfg.timeout_seconds
                while time.monotonic() < deadline:
                    hist = client.get(f"{self.base_url}/history/{prompt_id}").json()
                    if prompt_id in hist:
                        entry = hist[prompt_id]
                        status = entry.get("status", {})
                        if status.get("status_str") == "error":
                            raise ProviderError(f"ComfyUI execution error: {json.dumps(status)[:500]}")
                        for out in entry.get("outputs", {}).values():
                            for img in out.get("images", []):
                                v = client.get(f"{self.base_url}/view", params={
                                    "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                    "type": img.get("type", "output")})
                                v.raise_for_status()
                                return v.content
                    time.sleep(1.0)
                raise ProviderError(f"ComfyUI timed out after {self.cfg.timeout_seconds}s", transient=True)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderError(f"ComfyUI unreachable at {self.base_url}: {exc}", transient=True) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"ComfyUI HTTP error: {exc}", transient=exc.response.status_code >= 500) from exc

    def health(self) -> dict[str, Any]:
        try:
            r = httpx.get(f"{self.base_url}/system_stats", timeout=5)
            missing = [f for f in self.cfg.workflows.values() if not (self.workflow_dir / f).exists()]
            ok = r.status_code == 200 and not missing
            detail = r.json().get("system", {}).get("comfyui_version", "running") if r.status_code == 200 else f"HTTP {r.status_code}"
            if missing:
                detail += f"; missing workflow files {missing}"
            return {"ok": ok, "detail": detail}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"unreachable: {exc}"}
