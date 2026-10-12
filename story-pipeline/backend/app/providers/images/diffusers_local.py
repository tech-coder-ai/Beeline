"""Local text-to-image with Hugging Face diffusers - the simplest way to get real AI art without ComfyUI.

    pip install -e "backend[diffusers]"          (torch + diffusers + transformers + accelerate)
    models.image.provider: diffusers
    models.image.diffusers_model: black-forest-labs/FLUX.1-schnell   # Apache 2.0, 4 steps; ~33 GB in bf16 -> 48 GB GPU
                               or stabilityai/stable-diffusion-xl-base-1.0 (30 steps, 12+ GB)
                               or stabilityai/sdxl-turbo / stabilityai/sd-turbo (1-4 steps; usable even on CPU)

Weights download from Hugging Face on first use (cached in ~/.cache/huggingface). If
models.image.ip_adapter is set (SDXL only), the character reference sheet conditions every
scene, which keeps characters looking the same from shot to shot.
"""
from __future__ import annotations

import inspect
import io
import threading
from typing import Any

from app.config import ImageCfg
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.images.base import ImageRequest


class DiffusersProvider:
    name = "diffusers"
    _pipe = None
    _lock = threading.Lock()

    def __init__(self, cfg: ImageCfg):
        self.cfg = cfg
        self.model = cfg.diffusers_model + (f"+ip:{cfg.ip_adapter}" if cfg.ip_adapter else "")

    def _load(self):
        with DiffusersProvider._lock:
            if DiffusersProvider._pipe is not None:
                return DiffusersProvider._pipe
            try:
                import torch
                from diffusers import AutoPipelineForText2Image
            except ImportError as exc:
                raise ProviderUnavailable('diffusers not installed: pip install -e "backend[diffusers]"') from exc
            cuda = torch.cuda.is_available() and self.cfg.device in ("auto", "cuda")
            dtype = (torch.bfloat16 if "flux" in self.cfg.diffusers_model.lower() else torch.float16) if cuda else torch.float32
            try:
                pipe = AutoPipelineForText2Image.from_pretrained(self.cfg.diffusers_model, torch_dtype=dtype)
            except Exception as exc:  # noqa: BLE001 - network/auth/missing model
                raise ProviderError(f"could not load {self.cfg.diffusers_model}: {exc}", transient="connect" in str(exc).lower()) from exc
            if self.cfg.ip_adapter:
                repo, _, weight = self.cfg.ip_adapter.partition(":")
                pipe.load_ip_adapter(repo, subfolder="sdxl_models", weight_name=weight or "ip-adapter_sdxl.bin")
                pipe.set_ip_adapter_scale(self.cfg.ip_adapter_scale)
            if cuda:
                if self.cfg.cpu_offload:
                    pipe.enable_model_cpu_offload()   # fits big models in less VRAM, slower
                else:
                    pipe.to("cuda")
            DiffusersProvider._pipe = (pipe, "cuda" if cuda else "cpu")
            return DiffusersProvider._pipe

    def generate(self, req: ImageRequest) -> bytes:
        import torch
        pipe, device = self._load()
        params = inspect.signature(pipe.__call__).parameters
        kwargs: dict[str, Any] = {
            "prompt": req.prompt, "num_inference_steps": self.cfg.steps, "guidance_scale": self.cfg.guidance,
            "width": req.width - req.width % 16, "height": req.height - req.height % 16,
            "generator": torch.Generator(device="cpu").manual_seed(req.seed),
        }
        if "negative_prompt" in params and self.cfg.guidance > 1 and req.negative_prompt:
            kwargs["negative_prompt"] = req.negative_prompt   # FLUX/turbo models ignore negatives
        if self.cfg.ip_adapter and req.reference_images:
            from PIL import Image
            kwargs["ip_adapter_image"] = Image.open(req.reference_images[0]).convert("RGB")
        try:
            with DiffusersProvider._lock:
                image = pipe(**kwargs).images[0]
        except torch.cuda.OutOfMemoryError as exc:  # type: ignore[attr-defined]
            raise ProviderError("GPU out of memory - lower models.image width/height or set cpu_offload: true") from exc
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    def health(self) -> dict[str, Any]:
        try:
            import diffusers  # noqa: F401
            import torch
        except ImportError:
            return {"ok": False, "detail": 'diffusers not installed: pip install -e "backend[diffusers]"'}
        dev = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU (slow)"
        return {"ok": True, "detail": f"{self.cfg.diffusers_model} on {dev} (weights load on first use)"}
