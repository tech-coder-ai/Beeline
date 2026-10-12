"""Minimal ComfyUI HTTP client shared by the image and video adapters.

ComfyUI's API is small: upload inputs, POST /prompt with a workflow graph,
poll /history/<id>, download outputs with /view, and POST /free to unload models.
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.providers.errors import ProviderError

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".gif")


def fill_tokens(node: Any, values: dict[str, Any]) -> Any:
    """Replace "{{token}}" placeholders. A token that is the whole string keeps the value's type."""
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


class ComfyClient:
    def __init__(self, base_url: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client_id = uuid.uuid4().hex

    def upload(self, client: httpx.Client, path: Path) -> str:
        with path.open("rb") as f:
            r = client.post(f"{self.base_url}/upload/image", files={"image": (path.name, f, "image/png")},
                            data={"overwrite": "true"})
        r.raise_for_status()
        return r.json()["name"]

    def run(self, workflow: dict, values: dict[str, Any], uploads: dict[str, Path] | None = None,
            want: tuple[str, ...] = IMAGE_EXT) -> tuple[bytes, str]:
        """Fill tokens, queue the graph, wait, and return the first output file with an extension in `want`."""
        try:
            with httpx.Client(timeout=120) as client:
                vals = dict(values)
                for token, path in (uploads or {}).items():
                    vals[token] = self.upload(client, path)
                graph = fill_tokens(copy.deepcopy(workflow), vals)
                leftover = [t for t in ("{{prompt}}", "{{image}}", "{{seed}}") if t in json.dumps(graph)]
                if leftover:
                    raise ProviderError(f"workflow still contains unfilled tokens {leftover}")
                r = client.post(f"{self.base_url}/prompt", json={"prompt": graph, "client_id": self.client_id})
                if r.status_code == 400:
                    raise ProviderError(f"ComfyUI rejected the workflow (missing node or model?): {r.text[:600]}")
                r.raise_for_status()
                prompt_id = r.json()["prompt_id"]
                deadline = time.monotonic() + self.timeout_seconds
                while time.monotonic() < deadline:
                    hist = client.get(f"{self.base_url}/history/{prompt_id}").json()
                    entry = hist.get(prompt_id)
                    if entry:
                        status = entry.get("status", {})
                        if status.get("status_str") == "error":
                            raise ProviderError(f"ComfyUI execution error: {json.dumps(status)[:600]}")
                        if status.get("completed", True):
                            for out in entry.get("outputs", {}).values():
                                # images / gifs / videos / animated - node packs use different keys
                                for files in out.values():
                                    if not isinstance(files, list):
                                        continue
                                    for f in files:
                                        if isinstance(f, dict) and str(f.get("filename", "")).lower().endswith(want):
                                            v = client.get(f"{self.base_url}/view", params={
                                                "filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                                "type": f.get("type", "output")})
                                            v.raise_for_status()
                                            return v.content, f["filename"]
                            raise ProviderError(f"ComfyUI finished but produced no {want} output - check the save node")
                    time.sleep(2.0)
                raise ProviderError(f"ComfyUI timed out after {self.timeout_seconds:.0f}s", transient=True)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderError(f"ComfyUI unreachable at {self.base_url}: {exc}", transient=True) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"ComfyUI HTTP error: {exc}", transient=exc.response.status_code >= 500) from exc

    def free(self) -> None:
        """Unload models and free VRAM (ComfyUI POST /free). Best effort."""
        try:
            httpx.post(f"{self.base_url}/free", json={"unload_models": True, "free_memory": True}, timeout=30)
        except httpx.HTTPError:
            pass

    def system_stats(self) -> dict:
        r = httpx.get(f"{self.base_url}/system_stats", timeout=5)
        r.raise_for_status()
        return r.json()
