"""Deterministic script checks. Cheap, explainable, and they run on every script - LLM-written or not."""
from __future__ import annotations

import re

from app.schemas.story import Issue, Script, StoryAnalysis
from app.services.discovery.pipeline import shingles


def verbatim_overlap(script: Script, source_text: str, k: int = 8) -> float:
    """Share of the script's 8-word sequences that appear verbatim in the source (0..1)."""
    script_text = " ".join(l.text for s in script.scenes for l in s.lines)
    a, b = shingles(script_text, k), shingles(source_text, k)
    return len(a & b) / len(a) if a else 0.0


def check_script(analysis: StoryAnalysis, script: Script, *, source_text: str, min_s: float, max_s: float,
                 require_transformation: bool, max_similarity: float) -> list[Issue]:
    issues: list[Issue] = []
    char_ids = {c.character_id for c in analysis.characters}
    loc_ids = {loc.location_id for loc in analysis.bible.locations}

    if len({c.character_id for c in analysis.characters}) != len(analysis.characters):
        issues.append(Issue(severity="error", code="duplicate_character", message="duplicate character ids"))
    seen: set[str] = set()
    for idx, sc in enumerate(sorted(script.scenes, key=lambda s: s.sequence), start=1):
        if sc.scene_id in seen:
            issues.append(Issue(severity="error", code="duplicate_scene", message=f"{sc.scene_id} appears twice", scene_id=sc.scene_id))
        seen.add(sc.scene_id)
        if sc.sequence != idx:
            issues.append(Issue(severity="error", code="sequence_gap", message=f"expected sequence {idx}, got {sc.sequence}", scene_id=sc.scene_id))
        if sc.location_id not in loc_ids:
            issues.append(Issue(severity="warning", code="unknown_location", message=f"unknown location {sc.location_id}", scene_id=sc.scene_id))
        for cid in sc.characters:
            if cid not in char_ids:
                issues.append(Issue(severity="error", code="unknown_character", message=f"unknown character {cid}", scene_id=sc.scene_id))
        for line in sc.lines:
            if line.speaker != "narrator" and line.speaker not in char_ids:
                issues.append(Issue(severity="error", code="unknown_speaker", message=f"line spoken by unknown speaker '{line.speaker}'", scene_id=sc.scene_id))
        if not sc.lines:
            issues.append(Issue(severity="error", code="empty_scene", message="scene has no narration or dialogue", scene_id=sc.scene_id))
        if not (min_s <= sc.duration_seconds <= max_s):
            issues.append(Issue(severity="warning", code="duration_range", message=f"duration {sc.duration_seconds}s outside {min_s}-{max_s}s", scene_id=sc.scene_id))
        words = sum(len(l.text.split()) for l in sc.lines)
        if words / 2.5 > sc.duration_seconds * 1.6:
            issues.append(Issue(severity="warning", code="too_much_text", message=f"{words} words won't fit {sc.duration_seconds}s comfortably (scene will be stretched)", scene_id=sc.scene_id))

    on_screen = {cid for sc in script.scenes for cid in sc.characters} | {l.speaker for sc in script.scenes for l in sc.lines}
    for c in analysis.characters:
        if c.role == "protagonist" and c.character_id not in on_screen:
            issues.append(Issue(severity="error", code="missing_protagonist", message=f"protagonist {c.name} never appears"))
    if not script.ending.strip():
        issues.append(Issue(severity="warning", code="no_ending", message="script has no ending line - story may end abruptly"))
    elif not re.search(r"[.!?\"')]$", script.ending.strip()):
        issues.append(Issue(severity="warning", code="abrupt_ending", message="ending line looks truncated"))

    overlap = verbatim_overlap(script, source_text)
    if require_transformation and overlap > max_similarity:
        issues.append(Issue(severity="error", code="too_close_to_source",
                            message=f"{overlap:.0%} of the script's phrases appear verbatim in the source; this license requires an original adaptation (max {max_similarity:.0%})"))
    elif overlap > 0.5:
        issues.append(Issue(severity="warning", code="close_to_source",
                            message=f"{overlap:.0%} verbatim overlap with the source (allowed by this license)"))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
