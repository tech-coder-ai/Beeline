"""FFmpeg's built-in flite synthesizer (English only). Zero install if your ffmpeg has --enable-libflite."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.config import VoiceCfg
from app.media import MediaError, duration_of, ffmpeg_filters, run_ffmpeg
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.tts.base import SAMPLE_RATE, SynthesisResult

VOICES = {"awb", "kal", "kal16", "rms", "slt"}


def _atempo_chain(rate: float) -> str:
    # atempo accepts 0.5-2.0 per instance; chain for anything outside.
    parts, r = [], rate
    while r > 2.0:
        parts.append("atempo=2.0")
        r /= 2.0
    while r < 0.5:
        parts.append("atempo=0.5")
        r /= 0.5
    parts.append(f"atempo={r:.3f}")
    return ",".join(parts)


class FliteTTS:
    name = "flite"
    _available: bool | None = None

    def _check(self) -> None:
        if FliteTTS._available is None:
            FliteTTS._available = "flite" in ffmpeg_filters()
        if not FliteTTS._available:
            raise ProviderUnavailable("this ffmpeg build has no flite filter")

    def synthesize(self, text: str, voice: VoiceCfg, out_path: Path) -> SynthesisResult:
        self._check()
        v = voice.voice or "slt"
        if v not in VOICES:
            raise ProviderError(f"unknown flite voice '{v}' (choose from {sorted(VOICES)})")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(text)
            text_file = tf.name
        try:
            # textfile= avoids all filtergraph escaping problems with quotes/colons in dialogue.
            esc = text_file.replace("\\", "/").replace(":", "\\:")
            run_ffmpeg(["-f", "lavfi", "-i", f"flite=textfile='{esc}':voice={v}",
                        "-af", f"{_atempo_chain(voice.rate)},aresample={SAMPLE_RATE}",
                        "-ac", "1", "-c:a", "pcm_s16le", str(out_path)])
        except MediaError as exc:
            raise ProviderError(str(exc)) from exc
        finally:
            Path(text_file).unlink(missing_ok=True)
        return SynthesisResult(duration_of(out_path))

    def health(self, voice: VoiceCfg | None = None) -> dict[str, Any]:
        try:
            self._check()
            return {"ok": True, "detail": "ffmpeg flite filter available"}
        except ProviderUnavailable as exc:
            return {"ok": False, "detail": str(exc)}
