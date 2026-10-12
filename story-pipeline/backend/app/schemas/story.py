"""Structured story artifacts.

These schemas are the contract between the LLM and the rest of the pipeline.
They are sent to the model (as JSON Schema, so Ollama can constrain decoding)
and every response is validated against them. Downstream stages - images,
voices, rendering - read these objects and never have to "ask the LLM" what
order the scenes are in.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

HEX = r"^#[0-9a-fA-F]{6}$"


class Appearance(BaseModel):
    species: str = Field("", description="human, fox, lion, robot ...")
    build: str = ""
    hair: str = ""
    clothing_style: str = ""
    distinctive_features: list[str] = []
    palette: list[str] = Field(default_factory=list, description="2-3 hex colours")

    @field_validator("palette")
    @classmethod
    def _palette(cls, v: list[str]) -> list[str]:
        import re
        return [c for c in v if re.match(HEX, c)][:4]


class VoiceProfile(BaseModel):
    voice_id: str | None = None
    speaking_style: str = ""


class CharacterProfile(BaseModel):
    character_id: str = Field(pattern=r"^char_\d{3}$")
    name: str = Field(min_length=1, max_length=80)
    role: Literal["protagonist", "antagonist", "supporting", "minor"] = "supporting"
    age_range: str = ""
    personality: list[str] = []
    description: str = ""
    appearance: Appearance = Appearance()
    voice_profile: VoiceProfile = VoiceProfile()


class Location(BaseModel):
    location_id: str = Field(pattern=r"^location_\d{3}$")
    name: str
    description: str = ""


class Relationship(BaseModel):
    a: str
    b: str
    relation: str


class StoryBible(BaseModel):
    title: str
    synopsis: str
    genre: str = ""
    tone: str = ""
    audience: str = "general"
    content_warnings: list[str] = []
    main_plot: str = ""
    subplots: list[str] = []
    turning_points: list[str] = []
    timeline: list[str] = []
    locations: list[Location] = Field(min_length=1)
    relationships: list[Relationship] = []
    central_conflict: str = ""
    resolution: str = ""
    moral: str = ""
    preserved_facts: list[str] = []
    permitted_changes: list[str] = []


class StoryAnalysis(BaseModel):
    """Output of the first LLM call."""
    bible: StoryBible
    characters: list[CharacterProfile] = Field(min_length=1)


class ScriptLine(BaseModel):
    """One spoken unit, in order. speaker is "narrator" or a character id."""
    speaker: str = "narrator"
    text: str = Field(min_length=1)


class Camera(BaseModel):
    shot_type: Literal["establishing", "wide", "medium", "close_up", "over_shoulder"] = "wide"
    movement: Literal["static", "slow_push_in", "slow_pull_out", "pan_left", "pan_right"] = "slow_push_in"


class SceneSpec(BaseModel):
    scene_id: str = Field(pattern=r"^scene_\d{3}$")
    sequence: int = Field(ge=1)
    title: str = ""
    duration_seconds: float = Field(gt=0, le=120)
    location_id: str
    characters: list[str] = []
    lines: list[ScriptLine] = Field(default_factory=list, description="narration and dialogue in spoken order")
    visual_prompt: str = Field(min_length=1)
    camera: Camera = Camera()
    mood: str = "neutral"
    music_cue: str = "subtle_ambient"
    continuity_requirements: list[str] = []


class Script(BaseModel):
    """Output of the second LLM call."""
    title: str
    hook: str = ""
    scenes: list[SceneSpec] = Field(min_length=1)
    ending: str = ""


class Issue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    scene_id: str | None = None


class TranslatedSegment(BaseModel):
    segment_id: str
    text: str


class Translation(BaseModel):
    segments: list[TranslatedSegment]


class VideoMetadata(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str] = []
