"""Piper neural TTS (https://github.com/rhasspy/piper). Runs the `piper` CLI per segment."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import VoiceCfg
from app.media import MediaError, duration_of, run_ffmpeg
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.tts.base import SAMPLE_RATE, SynthesisResult


class PiperTTS:
    name = "piper"

    def __init__(self, models_dir: Path):
        self.models_dir = models_dir

    def _model(self, voice: VoiceCfg) -> Path:
        return self.models_dir / f"{voice.voice}.onnx"

    def synthesize(self, text: str, voice: VoiceCfg, out_path: Path) -> SynthesisResult:
        binary = shutil.which("piper")
        if not binary:
            raise ProviderUnavailable("piper binary not found on PATH")
        model = self._model(voice)
        if not model.exists():
            raise ProviderUnavailable(f"piper voice model missing: {model}")
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.wav"
            proc = subprocess.run(
                [binary, "--model", str(model), "--output_file", str(raw), "--length_scale", f"{1 / voice.rate:.3f}"],
                input=text, capture_output=True, text=True, timeout=600,
            )
            if proc.returncode != 0 or not raw.exists():
                raise ProviderError(f"piper failed: {proc.stderr.strip()[-400:]}")
            try:
                run_ffmpeg(["-i", str(raw), "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out_path)])
            except MediaError as exc:
                raise ProviderError(str(exc)) from exc
        return SynthesisResult(duration_of(out_path))

    def health(self, voice: VoiceCfg | None = None) -> dict[str, Any]:
        if not shutil.which("piper"):
            return {"ok": False, "detail": "piper not installed (pip install piper-tts)"}
        if voice and not self._model(voice).exists():
            return {"ok": False, "detail": f"voice model missing: {self._model(voice).name}"}
        return {"ok": True, "detail": "piper available"}
