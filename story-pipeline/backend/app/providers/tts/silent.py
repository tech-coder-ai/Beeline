"""Timed silence. Lets a language render (subtitles carry the words) while real TTS is being set up."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import VoiceCfg
from app.media import duration_of, run_ffmpeg
from app.providers.tts.base import SAMPLE_RATE, SynthesisResult

WORDS_PER_SECOND = 2.5


def estimate_seconds(text: str, rate: float = 1.0) -> float:
    words = len(text.split())
    # Scripts without spaces between words (e.g. Japanese) - fall back to characters.
    units = words if words > 1 or len(text) < 20 else len(text) / 5
    return max(1.0, units / WORDS_PER_SECOND / rate)


class SilentTTS:
    name = "silent"

    def synthesize(self, text: str, voice: VoiceCfg, out_path: Path) -> SynthesisResult:
        seconds = estimate_seconds(text, voice.rate)
        run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{seconds:.2f}",
                    "-c:a", "pcm_s16le", str(out_path)])
        return SynthesisResult(duration_of(out_path))

    def health(self, voice: VoiceCfg | None = None) -> dict[str, Any]:
        return {"ok": True, "detail": "always available (produces silence)"}
