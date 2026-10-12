"""Kokoro neural TTS (82M params, Apache 2.0) via kokoro-onnx. Natural voices, runs faster than real time on CPU.

Install:  pip install -e "backend[tts]"   then   scripts/download_models.sh   (fetches the ONNX model + voices)
Voices are named <lang><gender>_<name>: af_/am_ US English, bf_/bm_ British, hf_/hm_ Hindi, ef_/em_ Spanish,
ff_ French, if_/im_ Italian, pf_/pm_ Portuguese, jf_/jm_ Japanese, zf_/zm_ Mandarin.
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any

from app.config import VoiceCfg
from app.media import MediaError, duration_of, run_ffmpeg
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.tts.base import SAMPLE_RATE, SynthesisResult

LANG_BY_PREFIX = {"a": "en-us", "b": "en-gb", "h": "hi", "e": "es", "f": "fr-fr", "i": "it", "p": "pt-br",
                  "j": "ja", "z": "cmn"}
MODEL_FILE, VOICES_FILE = "kokoro-v1.0.onnx", "voices-v1.0.bin"


class KokoroTTS:
    name = "kokoro"
    _engine = None
    _lock = threading.Lock()

    def __init__(self, models_dir: Path):
        self.models_dir = models_dir

    def _load(self):
        with KokoroTTS._lock:
            if KokoroTTS._engine is None:
                try:
                    from kokoro_onnx import Kokoro
                except ImportError as exc:
                    raise ProviderUnavailable('kokoro-onnx not installed: pip install -e "backend[tts]"') from exc
                model, voices = self.models_dir / MODEL_FILE, self.models_dir / VOICES_FILE
                if not model.exists() or not voices.exists():
                    raise ProviderUnavailable(f"Kokoro model files missing in {self.models_dir} - run scripts/download_models.sh")
                KokoroTTS._engine = Kokoro(str(model), str(voices))
            return KokoroTTS._engine

    def synthesize(self, text: str, voice: VoiceCfg, out_path: Path) -> SynthesisResult:
        engine = self._load()
        name = voice.voice
        if name not in engine.get_voices():
            raise ProviderError(f"unknown Kokoro voice '{name}'")
        try:
            with KokoroTTS._lock:  # the ONNX session is shared; keep calls serial
                samples, sr = engine.create(text, voice=name, speed=voice.rate, lang=LANG_BY_PREFIX.get(name[:1], "en-us"))
        except Exception as exc:  # noqa: BLE001 - phonemizer/onnx errors are not retryable
            raise ProviderError(f"Kokoro failed on '{text[:40]}…': {exc}") from exc
        import soundfile as sf
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.wav"
            sf.write(raw, samples, sr)
            try:
                run_ffmpeg(["-i", str(raw), "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out_path)])
            except MediaError as exc:
                raise ProviderError(str(exc)) from exc
        return SynthesisResult(duration_of(out_path))

    def health(self, voice: VoiceCfg | None = None) -> dict[str, Any]:
        try:
            engine = self._load()
        except ProviderUnavailable as exc:
            return {"ok": False, "detail": str(exc)}
        if voice and voice.voice not in engine.get_voices():
            return {"ok": False, "detail": f"unknown voice {voice.voice}"}
        return {"ok": True, "detail": "Kokoro v1.0 (ONNX)"}
