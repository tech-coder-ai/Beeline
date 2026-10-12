"""Fake image-to-video with FFmpeg: a gentle handheld drift. Lets you test the hybrid path without a GPU."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.media import run_ffmpeg
from app.providers.video.base import VideoRequest


class PlaceholderVideoProvider:
    name = "placeholder-video"
    model = "ffmpeg-drift-v1"

    def generate(self, req: VideoRequest) -> bytes:
        w, h, n = req.width, req.height, req.frames
        amp = 0.015 + (req.seed % 7) / 1000  # seed changes the motion slightly, like a real model
        vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
              f"zoompan=z='1.08+0.02*sin(on/{n}*PI)':x='iw/2-(iw/zoom/2)+iw*{amp}*sin(on/9)':"
              f"y='ih/2-(ih/zoom/2)+ih*{amp}*cos(on/11)':d={n}:s={w}x{h}:fps={req.fps},format=yuv420p")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "clip.mp4"
            run_ffmpeg(["-i", str(req.image_path), "-vf", vf, "-frames:v", str(n), "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "20", "-an", str(out)])
            return out.read_bytes()

    def free(self) -> None:
        pass

    def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "FFmpeg drift (stand-in for a real image-to-video model)"}


class NoVideoProvider:
    name = "none"
    model = "none"

    def generate(self, req: VideoRequest) -> bytes:  # pragma: no cover - never called
        raise NotImplementedError

    def free(self) -> None:
        pass

    def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "disabled - hybrid projects render every scene as a still"}
