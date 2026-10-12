"""Deterministic adaptation used when no LLM is configured (or the LLM output can't be repaired).

It is intentionally simple and faithful: it reorganises the source into scenes
rather than rewriting it. That is only acceptable for sources whose rights
allow verbatim use - the script stage enforces this.
"""
from __future__ import annotations

import hashlib
import re

from app.schemas.story import (
    Appearance,
    Camera,
    CharacterProfile,
    Location,
    SceneSpec,
    Script,
    ScriptLine,
    StoryAnalysis,
    StoryBible,
    VoiceProfile,
)

STOP = {"I", "The", "A", "An", "You", "If", "It", "Just", "At", "On", "As", "Though", "Although", "When", "Then",
        "He", "She", "They", "We", "But", "And", "In", "Of", "To", "My", "His", "Her", "Their", "Our", "This",
        "That", "There", "Rising", "Slow", "Once", "One", "So", "Now", "What", "Why", "How", "No", "Yes", "Oh"}
ANIMALS = {"lion", "mouse", "hare", "tortoise", "fox", "wolf", "lamb", "crow", "ant", "grasshopper", "dog", "cat",
           "bear", "eagle", "frog", "goat", "horse", "ox", "owl", "rabbit", "snake", "monkey", "elephant", "deer",
           "cock", "hen", "mice", "stag", "ass", "donkey", "bird", "tiger", "crane", "stork"}
PALETTES = [["#c0392b", "#f5cba7"], ["#2e86c1", "#d6eaf8"], ["#28b463", "#d5f5e3"], ["#8e44ad", "#e8daef"],
            ["#d68910", "#fdebd0"], ["#5d6d7e", "#eaeded"], ["#a04000", "#f6ddcc"], ["#117a65", "#d1f2eb"]]
MOODS = [
    ("tense", r"\b(kill|angr|caught|danger|fright|fear|bound|hunter|trap|famished)"),
    ("triumphant", r"\b(free|won|wins|goal|victor|reached)"),
    ("joyful", r"\b(laugh|delight|luxur|feast|dainties|cheer|plenty)"),
    ("peaceful", r"\b(asleep|sleep|dozing|rest|safety|quiet)"),
]
QUOTE = re.compile(r'"([^"]+)"')
SENT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z\"])")


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def detect_characters(text: str, max_chars: int = 5) -> list[str]:
    """Capitalised words (or runs like 'Town Mouse') that recur mid-sentence are probably characters."""
    counts: dict[str, int] = {}
    for m in re.finditer(r"(?<![.!?\"]\s)(?<!^)\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", text, re.M):
        name = m.group(1)
        first = name.split()[0]
        if first in STOP:
            name = " ".join(name.split()[1:])
            if not name:
                continue
        counts[name] = counts.get(name, 0) + 1
    # a single word that only ever appears inside a longer name ("Mouse" in "Town Mouse") is not separate
    multi = [n for n in counts if " " in n]
    for n in list(counts):
        if " " not in n and any(m.endswith(" " + n) for m in multi):
            standalone = len(re.findall(rf"(?<![A-Z][a-z]\s)(?<![A-Z][a-z]{{2}}\s)\b{n}\b", text)) - sum(
                counts[m] for m in multi if m.endswith(" " + n))
            if standalone < 2:
                counts.pop(n)
    names = [n for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], text.find(kv[0]))) if c >= 2]
    return names[:max_chars]


def _mood(text: str) -> str:
    low = text.lower()
    for mood, pat in MOODS:
        if re.search(pat, low):
            return mood
    return "reflective"


def _beats(text: str) -> list[list[tuple[str, str]]]:
    """Split into beats: a narration sentence plus any quotes attached to it. Each item: (kind, text)."""
    beats: list[list[tuple[str, str]]] = []
    for para in [p for p in text.split("\n\n") if p.strip()]:
        pos = 0
        current: list[tuple[str, str]] | None = None
        for m in QUOTE.finditer(para):
            outside = para[pos:m.start()].strip()
            for i, sent in enumerate(s for s in SENT.split(outside) if s.strip()):
                current = [("narration", sent.strip())]
                beats.append(current)
            if current is None:
                current = []
                beats.append(current)
            current.append(("quote", m.group(1).strip()))
            pos = m.end()
        tail = para[pos:].strip()
        for sent in (s for s in SENT.split(tail) if s.strip()):
            beats.append([("narration", sent.strip())])
            current = beats[-1]
    return [b for b in beats if b]


def adapt(title: str, author: str | None, text: str, *, target_scenes: int, min_s: float, max_s: float,
          style: str) -> tuple[StoryAnalysis, Script]:
    names = detect_characters(text) or ["Narrator"]
    chars: list[CharacterProfile] = []
    for i, name in enumerate(names):
        species = name.split()[-1].lower()
        chars.append(CharacterProfile(
            character_id=f"char_{i + 1:03d}", name=name,
            role="protagonist" if i == 0 else "supporting" if i < 3 else "minor",
            description=f"The {name} from the story.",
            appearance=Appearance(species=species if species in ANIMALS else "human",
                                  palette=PALETTES[(_h(name) + i) % len(PALETTES)],
                                  distinctive_features=[f"signature {PALETTES[(_h(name) + i) % len(PALETTES)][0]} colouring"]),
            voice_profile=VoiceProfile(speaking_style="expressive"),
        ))
    by_name = {c.name: c.character_id for c in chars}
    location = Location(location_id="location_001", name="Story world", description=f"The world of {title}")
    sentences = [t for b in _beats(text) for k, t in b if k == "narration"]
    complete = [x for x in sentences if x.rstrip().endswith((".", "!", "?"))]  # skip "...said:" lead-ins
    last = sentences[-1] if sentences else ""
    bible = StoryBible(
        title=title,
        synopsis=" ".join(complete[:2])[:600],
        genre="fable" if author and "aesop" in author.lower() else "short story",
        tone="classic", audience="general", locations=[location],
        main_plot=" ".join(sentences[:3])[:800],
        resolution=sentences[-1] if sentences else "",
        moral=last if last.endswith(".") and len(last.split()) < 12 else "",
        preserved_facts=[f"{c.name} appears in the story" for c in chars] + ([sentences[-1]] if sentences else []),
        permitted_changes=["scene pacing", "visual framing", "narration split into scenes"],
    )
    beats = _beats(text)
    n = max(1, min(target_scenes, len(beats)))
    total_words = sum(len(t.split()) for b in beats for _, t in b)
    per_scene = total_words / n
    groups: list[list[list[tuple[str, str]]]] = [[]]
    acc = 0
    for b in beats:
        w = sum(len(t.split()) for _, t in b)
        if groups[-1] and acc + w / 2 > per_scene and len(groups) < n:
            groups.append([])
            acc = 0
        groups[-1].append(b)
        acc += w
    scenes: list[SceneSpec] = []
    shots = ["establishing", "medium", "close_up", "wide", "medium", "over_shoulder"]
    moves = ["slow_push_in", "pan_right", "slow_push_in", "slow_pull_out", "pan_left", "slow_push_in"]
    for i, group in enumerate(groups):
        lines: list[ScriptLine] = []
        last_speaker = "narrator"
        for beat in group:
            for kind, t in beat:
                if kind == "narration":
                    lines.append(ScriptLine(speaker="narrator", text=t))
                    mentioned = [(t.rfind(nm), cid) for nm, cid in by_name.items() if nm in t]
                    if mentioned:
                        last_speaker = max(mentioned)[1]
                else:
                    lines.append(ScriptLine(speaker=last_speaker if last_speaker != "narrator" else chars[0].character_id,
                                            text=t))
        scene_text = " ".join(l.text for l in lines)
        present = [cid for nm, cid in by_name.items() if nm in scene_text]
        present += [l.speaker for l in lines if l.speaker != "narrator" and l.speaker not in present]
        if not present and scenes:  # "the two started together" - carry the cast over from the last scene
            present = list(scenes[-1].characters)
        mood = _mood(scene_text)
        words = len(scene_text.split())
        first = lines[0].text if lines else title
        cast = "; ".join(f"{c.name} ({c.appearance.species}, colours {', '.join(c.appearance.palette)})"
                         for c in chars if c.character_id in present)
        shot = shots[i % len(shots)] if i else "establishing"
        scenes.append(SceneSpec(
            scene_id=f"scene_{i + 1:03d}", sequence=i + 1,
            title=" ".join(first.split()[:6]).rstrip(",;:") + ("…" if len(first.split()) > 6 else ""),
            duration_seconds=round(min(max_s, max(min_s, words / 2.5 + 1.5)), 1),
            location_id=location.location_id, characters=present, lines=lines,
            visual_prompt=f"{style}. {first[:300]} Characters: {cast or 'none'}. Mood: {mood}. {shot.replace('_', ' ')} shot.",
            camera=Camera(shot_type=shot, movement=moves[i % len(moves)]),
            mood=mood, music_cue="gentle_strings" if mood in ("peaceful", "reflective") else "light_percussion",
            continuity_requirements=[f"{c.name} keeps the {c.appearance.palette[0]} colouring" for c in chars
                                     if c.character_id in present],
        ))
    script = Script(title=title, hook=sentences[0] if sentences else title, scenes=scenes,
                    ending=sentences[-1] if sentences else "")
    return StoryAnalysis(bible=bible, characters=chars), script
