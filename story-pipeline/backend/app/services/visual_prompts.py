"""Prompt wording for image models.

Image models read prompts very differently from LLMs: CLIP-based models only see ~77 tokens, put the
most weight on the first words, and treat hex codes or long prose as noise. So prompts are built
subject-first from structured fields, with colours as words, not "#c0392b".
"""
from __future__ import annotations

from app.schemas.story import CharacterProfile

NAMED = {
    "red": (192, 57, 43), "crimson": (150, 30, 45), "orange": (230, 126, 34), "golden": (212, 160, 23),
    "yellow": (241, 196, 15), "brown": (120, 72, 40), "tan": (210, 180, 140), "green": (40, 160, 90),
    "olive": (110, 120, 50), "teal": (20, 120, 110), "blue": (46, 110, 190), "navy": (25, 40, 90),
    "purple": (120, 70, 160), "pink": (230, 140, 170), "grey": (128, 128, 128), "silver": (190, 195, 200),
    "white": (245, 245, 245), "black": (25, 25, 25), "cream": (245, 235, 210),
}


def color_name(hex_code: str) -> str:
    h = hex_code.lstrip("#")
    try:
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return ""
    return min(NAMED, key=lambda n: sum((a - b) ** 2 for a, b in zip(NAMED[n], rgb)))


def describe(c: CharacterProfile) -> str:
    """'a lion with a golden mane' / 'a young woman, dark shoulder-length hair, silver pendant'."""
    a = c.appearance
    species = a.species if a.species and a.species != "human" else ""
    noun = c.name.lower() if species and species in c.name.lower() else (f"{species} named {c.name}" if species else c.name)
    bits = [x for x in (a.build, a.hair, a.clothing_style) if x]
    bits += [f for f in a.distinctive_features if "#" not in f][:2]
    colours = ", ".join(dict.fromkeys(filter(None, (color_name(p) for p in a.palette[:2]))))
    if colours and species:
        bits.append(f"{colours} tones")
    article = "an" if noun[:1].lower() in "aeiou" else "a"
    lead = noun if not species else f"{article} {noun}"
    return lead + (f" ({', '.join(bits)})" if bits else "")


def scene_prompt(style: str, action: str, cast: list[CharacterProfile], setting: str, shot: str, mood: str,
                 continuity: list[str]) -> str:
    who = " and ".join(describe(c) for c in cast)
    parts = [action.strip().rstrip("."), f"featuring {who}" if who else "", setting,
             f"{shot.replace('_', ' ')} shot", f"{mood} mood", style]
    parts += [c for c in continuity if "#" not in c][:2]
    return ", ".join(p for p in parts if p)


def character_prompt(style: str, c: CharacterProfile) -> str:
    return (f"character reference sheet of {describe(c)}, front view, three-quarter view and side view, "
            f"full body, plain light background, consistent design, {style}")
