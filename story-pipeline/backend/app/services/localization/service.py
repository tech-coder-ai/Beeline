"""Localization: translate the approved script per language, keeping scene/segment ids stable.

The scene structure is language-independent. Only the spoken text (and
therefore audio, subtitles and timing) differs per language.
"""
from __future__ import annotations

import json

from app.config import Settings
from app.media import fingerprint
from app.prompts import render_prompt
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.llm.base import LLMProvider, generate_model
from app.schemas.story import CharacterProfile, Script, Translation


def source_segments(script: Script) -> list[dict]:
    segs = []
    order = 0
    for sc in sorted(script.scenes, key=lambda x: x.sequence):
        for i, line in enumerate(sc.lines):
            segs.append({"segment_id": f"{sc.scene_id}_l{i:02d}", "scene_id": sc.scene_id, "order": order,
                         "speaker": line.speaker, "text": line.text})
            order += 1
    return segs


def glossary_for(characters: list[CharacterProfile]) -> dict[str, str]:
    # Names stay as-is by default; extend here (or via config) for transliteration.
    return {c.name: c.name for c in characters}


async def translate(settings: Settings, llm: LLMProvider, segments: list[dict], language: str,
                    glossary: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Translate scene by scene (small prompts suit small local models). Returns (segments, warnings)."""
    langs = settings.languages
    src_name = langs.languages[langs.source].name
    tgt_name = langs.languages[language].name
    out: list[dict] = []
    warnings: list[str] = []
    by_scene: dict[str, list[dict]] = {}
    for seg in segments:
        by_scene.setdefault(seg["scene_id"], []).append(seg)
    for scene_id, segs in by_scene.items():
        payload = [{"segment_id": s["segment_id"], "speaker": s["speaker"], "text": s["text"]} for s in segs]
        prompt = render_prompt(settings, "translate", source_language=src_name, target_language=tgt_name,
                               glossary="\n".join(f"{k} -> {v}" for k, v in glossary.items()) or "(none)",
                               segments_json=json.dumps(payload, ensure_ascii=False, indent=1))
        result = await generate_model(llm, prompt, Translation, repair_attempts=settings.models.llm.json_repair_attempts)
        got = {t.segment_id: t.text.strip() for t in result.segments}
        missing = [s["segment_id"] for s in segs if not got.get(s["segment_id"])]
        if missing:
            raise ProviderError(f"translation to {language} dropped segments {missing}", transient=True)
        for s in segs:
            text = got[s["segment_id"]]
            ratio = len(text) / max(1, len(s["text"]))
            if ratio > 1.6 or ratio < 0.4:
                warnings.append(f"{language}/{s['segment_id']}: translation length ratio {ratio:.1f} - check timing")
            out.append({**s, "text": text})
    return out, warnings


def localization_fingerprint(segments: list[dict], language: str, glossary: dict, llm_name: str) -> str:
    return fingerprint("localization", language, llm_name, glossary, [(s["segment_id"], s["speaker"], s["text"]) for s in segments])


__all__ = ["source_segments", "glossary_for", "translate", "localization_fingerprint", "ProviderUnavailable"]
