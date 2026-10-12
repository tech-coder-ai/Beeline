"""Typed configuration loaded from config/*.yaml with environment overrides.

Why typed config: a typo in YAML ("provder: olama") should fail loudly at
startup, not halfway through a two-hour render. Pydantic validates every key.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

# story-pipeline/  (this file is story-pipeline/backend/app/config.py)
ROOT_DIR = Path(__file__).resolve().parents[2]

Checkpoint = Literal["story_adaptation", "character_generation", "scene_generation", "final_render"]


class PipelineCfg(BaseModel):
    mode: Literal["approval_required", "fully_automated"] = "approval_required"
    max_parallel_scenes: int = Field(2, ge=1, le=16)
    max_attempts: int = Field(3, ge=1, le=10)
    retry_backoff_seconds: float = Field(5, ge=0)
    checkpoint_after: list[Checkpoint] = ["story_adaptation", "character_generation", "final_render"]
    target_scene_count: int = Field(6, ge=1, le=60)
    min_scene_seconds: float = 4
    max_scene_seconds: float = 40


class LLMCfg(BaseModel):
    provider: Literal["ollama", "openai_compatible", "offline"] = "offline"
    model: str = "llama3.1:8b"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    temperature: float = 0.4
    timeout_seconds: float = 300
    json_repair_attempts: int = Field(2, ge=0, le=5)
    max_source_chars: int = Field(24000, ge=1000)  # keep prompts inside small models' context windows


class ImageCfg(BaseModel):
    provider: Literal["comfyui", "placeholder"] = "placeholder"
    base_url: str = "http://localhost:8188"
    timeout_seconds: float = 600
    workflows: dict[str, str] = {}
    style: str = ""
    negative_prompt: str = ""
    width: int = 1344
    height: int = 768


class ModelsCfg(BaseModel):
    llm: LLMCfg = LLMCfg()
    image: ImageCfg = ImageCfg()


class VideoCfg(BaseModel):
    width: int = Field(1920, ge=160)
    height: int = Field(1080, ge=90)
    fps: int = Field(24, ge=1, le=60)
    format: Literal["mp4"] = "mp4"
    crf: int = Field(21, ge=0, le=51)
    preset: str = "veryfast"
    burn_subtitles: bool = True
    scene_padding_seconds: float = 0.6
    segment_gap_seconds: float = 0.35
    camera_zoom: float = Field(1.12, ge=1.0, le=2.0)
    music_path: str | None = None
    music_volume: float = Field(0.12, ge=0, le=1)


class QualityCfg(BaseModel):
    max_silence_seconds: float = 4.0
    max_black_seconds: float = 1.0
    duration_tolerance_seconds: float = 1.5
    clipping_threshold_db: float = -0.1
    max_source_similarity: float = Field(0.6, ge=0, le=1)
    thumbnail_width: int = 1280
    thumbnail_height: int = 720


class PublishingCfg(BaseModel):
    provider: Literal["youtube", "dry_run"] = "dry_run"
    default_visibility: Literal["private", "unlisted", "public"] = "private"
    require_approval: bool = True
    category_id: str = "1"
    client_secrets_file: str = "secrets/client_secret.json"
    token_file: str = "secrets/youtube_token.json"
    synthetic_content_disclosure: bool = True
    channel_attribution: str = ""


class StorageCfg(BaseModel):
    data_dir: str = "data"
    database_url: str = "sqlite:///data/pipeline.db"


class DiscoveryCfg(BaseModel):
    library_dir: str = "sample_stories"
    gutendex_url: str = "https://gutendex.com"
    rss_feeds: list[str] = []
    user_agent: str = "StoryPipeline/0.1"
    request_delay_seconds: float = 1.0
    max_story_chars: int = 60000


class VoiceCfg(BaseModel):
    voice_id: str
    provider: Literal["flite", "piper", "silent"]
    voice: str = ""
    rate: float = Field(1.0, gt=0.25, le=4.0)


class LanguageCfg(BaseModel):
    name: str
    locale: str
    narrator: VoiceCfg
    character_pool: list[VoiceCfg] = []
    fallback: VoiceCfg | None = None


class LanguagesCfg(BaseModel):
    source: str = "en"
    targets: list[str] = []
    tts_models_dir: str = "models/piper"
    languages: dict[str, LanguageCfg]

    def all_codes(self) -> list[str]:
        return [self.source] + [t for t in self.targets if t != self.source]


class Settings(BaseModel):
    pipeline: PipelineCfg = PipelineCfg()
    models: ModelsCfg = ModelsCfg()
    video: VideoCfg = VideoCfg()
    quality: QualityCfg = QualityCfg()
    publishing: PublishingCfg = PublishingCfg()
    storage: StorageCfg = StorageCfg()
    discovery: DiscoveryCfg = DiscoveryCfg()
    languages: LanguagesCfg
    config_dir: str = str(ROOT_DIR / "config")
    config_version: str = "dev"

    def path(self, value: str | Path) -> Path:
        """Resolve a configured path relative to the project root."""
        p = Path(value)
        return p if p.is_absolute() else ROOT_DIR / p

    @property
    def data_dir(self) -> Path:
        return self.path(self.storage.data_dir)

    def validate_languages(self) -> None:
        missing = [c for c in self.languages.all_codes() if c not in self.languages.languages]
        if missing:
            raise ValueError(f"languages.yaml: no voice registry entry for {missing}")


# env var -> (dotted path, caster)
ENV_OVERRIDES: dict[str, tuple[str, type]] = {
    "SPA_MODE": ("pipeline.mode", str),
    "SPA_LLM_PROVIDER": ("models.llm.provider", str),
    "SPA_LLM_MODEL": ("models.llm.model", str),
    "SPA_LLM_BASE_URL": ("models.llm.base_url", str),
    "SPA_LLM_API_KEY": ("models.llm.api_key", str),
    "SPA_IMAGE_PROVIDER": ("models.image.provider", str),
    "SPA_IMAGE_BASE_URL": ("models.image.base_url", str),
    "SPA_PUBLISH_PROVIDER": ("publishing.provider", str),
    "SPA_DATABASE_URL": ("storage.database_url", str),
    "SPA_DATA_DIR": ("storage.data_dir", str),
    "SPA_VIDEO_WIDTH": ("video.width", int),
    "SPA_VIDEO_HEIGHT": ("video.height", int),
    "SPA_VIDEO_FPS": ("video.fps", int),
    "SPA_TARGET_LANGUAGES": ("languages.targets", lambda s: [x.strip() for x in s.split(",") if x.strip()]),
}


def _set_dotted(d: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {}
        d = d[k]
    d[keys[-1]] = value


def load_settings(config_dir: str | Path | None = None) -> Settings:
    cdir = Path(config_dir or os.environ.get("SPA_CONFIG_DIR") or ROOT_DIR / "config")
    raw_pipeline = (cdir / "pipeline.yaml").read_text()
    raw_languages = (cdir / "languages.yaml").read_text()
    data = yaml.safe_load(raw_pipeline) or {}
    data["languages"] = yaml.safe_load(raw_languages) or {}
    for env, (dotted, cast) in ENV_OVERRIDES.items():
        if os.environ.get(env):
            _set_dotted(data, dotted, cast(os.environ[env]))
    # The config version lets every project record exactly which settings produced it.
    version = hashlib.sha256((raw_pipeline + raw_languages).encode()).hexdigest()[:12]
    settings = Settings(**data, config_dir=str(cdir), config_version=version)
    settings.validate_languages()
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
