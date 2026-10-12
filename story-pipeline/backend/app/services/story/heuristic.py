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
# Natural colouring per species (first two = coat/accents); variants keep two of the same species apart.
SPECIES_PALETTES = {
    "lion": [["#d4a017", "#8b5a2b"], ["#c9a25e", "#5c3a1e"]], "mouse": [["#8c8c8c", "#f2c6c2"], ["#7b4a26", "#f5e6d3"]],
    "hare": [["#a0785a", "#f5f5f5"]], "rabbit": [["#c8b39a", "#f5f5f5"]], "tortoise": [["#6b7a3a", "#a0785a"]],
    "fox": [["#e07b24", "#f5f5f5"]], "wolf": [["#7f8c8d", "#ecf0f1"]], "crow": [["#1c1c1c", "#4a4a6a"]],
    "frog": [["#3c9a3c", "#e8e070"]], "ant": [["#5c3a1e", "#1c1c1c"]], "grasshopper": [["#7cb342", "#c5e1a5"]],
    "dog": [["#a0785a", "#f5f5f5"]], "cat": [["#e0a060", "#f5f5f5"]], "bear": [["#5c3a1e", "#a0785a"]],
}
NAME_TRAITS = {"town": "dapper little waistcoat", "city": "dapper little waistcoat", "country": "simple rustic scarf",
               "old": "grey whiskers", "young": "small and bright-eyed", "king": "tiny golden crown"}
SETTINGS = [
    (r"\b(plowland|field|hedgerow|country fare|meadow)", "open countryside fields with hedgerows"),
    (r"\b(town|house|cupboard|door|hole|cheese|feast)", "cosy old town house interior, warm lamplight"),
    (r"\b(race|course|wayside|goal)", "winding country road through green meadows"),
    (r"\b(hunter|rope|roar|lion)", "sunlit savanna grassland with acacia trees"),
    (r"\b(forest|wood|tree)", "deep green forest"),
    (r"\b(river|pond|stream|lake)", "riverbank with reeds"),
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


def _setting(text: str, fallback: str) -> str:
    low = text.lower()
    for pat, name in SETTINGS:
        if re.search(pat, low):
            return name
    return fallback


def _visual_action(sentence: str) -> str:
    """Turn a narration sentence into a short visual description: drop speech, keep the action."""
    text = re.sub(r'"[^"]*"', "", sentence)
    text = re.split(r",? (?:saying|exclaiming|replied|said)\b", text)[0]
    text = re.sub(r"\s+", " ", text).strip(" ,;:")
    words = text.split()
    text = " ".join(words[:28])
    return text


def adapt(title: str, author: str | None, text: str, *, target_scenes: int, min_s: float, max_s: float,
          style: str, max_animated: int = 3) -> tuple[StoryAnalysis, Script]:
    names = detect_characters(text) or ["Narrator"]
    chars: list[CharacterProfile] = []
    for i, name in enumerate(names):
        species = name.split()[-1].lower()
        same = sum(1 for c in chars if c.appearance.species == species)
        palette = (SPECIES_PALETTES[species][same % len(SPECIES_PALETTES[species])] if species in SPECIES_PALETTES
                   else PALETTES[(_h(name) + i) % len(PALETTES)])
        chars.append(CharacterProfile(
            character_id=f"char_{i + 1:03d}", name=name,
            role="protagonist" if i == 0 else "supporting" if i < 3 else "minor",
            description=f"The {name} from the story.",
            appearance=Appearance(species=species if species in ANIMALS else "human", palette=palette,
                                  distinctive_features=[NAME_TRAITS[w.lower()] for w in name.split()[:-1]
                                                        if w.lower() in NAME_TRAITS]),
            voice_profile=VoiceProfile(speaking_style="expressive"),
        ))
    by_name = {c.name: c.character_id for c in chars}
    default_setting = _setting(text, "storybook countryside")
    locations: dict[str, Location] = {}

    def location_for(scene_text: str) -> str:
        name = _setting(scene_text, default_setting)
        if name not in locations:
            locations[name] = Location(location_id=f"location_{len(locations) + 1:03d}", name=name)
        return locations[name].location_id
    sentences = [t for b in _beats(text) for k, t in b if k == "narration"]
    complete = [x for x in sentences if x.rstrip().endswith((".", "!", "?"))]  # skip "...said:" lead-ins
    last = sentences[-1] if sentences else ""
    bible = StoryBible(
        title=title,
        synopsis=" ".join(complete[:2])[:600],
        genre="fable" if author and "aesop" in author.lower() else "short story",
        tone="classic", audience="general", locations=[Location(location_id="location_000", name=default_setting)],
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
        cast = " and ".join(c.name.lower() if c.appearance.species in c.name.lower() else c.name
                            for c in chars if c.character_id in present)
        shot = shots[i % len(shots)] if i else "establishing"
        scenes.append(SceneSpec(
            scene_id=f"scene_{i + 1:03d}", sequence=i + 1,
            title=" ".join(first.split()[:6]).rstrip(",;:") + ("…" if len(first.split()) > 6 else ""),
            duration_seconds=round(min(max_s, max(min_s, words / 2.5 + 1.5)), 1),
            location_id=location_for(scene_text), characters=present, lines=lines,
            visual_prompt=_visual_action(first),
            camera=Camera(shot_type=shot, movement=moves[i % len(moves)]),
            mood=mood, music_cue="gentle_strings" if mood in ("peaceful", "reflective") else "light_percussion",
            continuity_requirements=[f"same {c.name.lower()} design as the reference sheet" for c in chars
                                     if c.character_id in present],
        ))
    # Mark scenes for AI motion: the hook first, then the most dramatic moods.
    drama = {"tense": 0, "triumphant": 1, "joyful": 2}
    ranked = [scenes[0]] + sorted(scenes[1:], key=lambda sc: (drama.get(sc.mood, 9), sc.sequence))
    for sc in ranked[:max_animated]:
        if sc is scenes[0] or sc.mood in drama:
            who = ", ".join(c.name for c in chars if c.character_id in sc.characters) or "the scene"
            sc.animate = True
            sc.motion_prompt = (f"{who} move naturally, {sc.mood} energy, gentle wind, "
                                f"{sc.camera.movement.replace('_', ' ')}")
    bible.locations = list(locations.values()) or bible.locations
    script = Script(title=title, hook=sentences[0] if sentences else title, scenes=scenes,
                    ending=sentences[-1] if sentences else "")
    return StoryAnalysis(bible=bible, characters=chars), script
