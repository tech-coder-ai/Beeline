"""Text-to-speech contract. Every provider writes 44.1 kHz mono WAV so segments concatenate cleanly."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import VoiceCfg

SAMPLE_RATE = 44100


@dataclass
class SynthesisResult:
    duration_seconds: float
    sample_rate: int = SAMPLE_RATE


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, voice: VoiceCfg, out_path: Path) -> SynthesisResult: ...

    def health(self, voice: VoiceCfg | None = None) -> dict[str, Any]: ...
