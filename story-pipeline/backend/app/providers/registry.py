"""Builds providers from configuration. The only place that knows concrete classes."""
from __future__ import annotations

from pathlib import Path

from app.config import Settings, VoiceCfg
from app.providers.images.base import ImageProvider
from app.providers.llm.base import LLMProvider
from app.providers.tts.base import TTSProvider
from app.providers.youtube.base import Publisher


def build_llm(settings: Settings) -> LLMProvider:
    cfg = settings.models.llm
    if cfg.provider == "ollama":
        from app.providers.llm.ollama import OllamaProvider
        return OllamaProvider(cfg)
    if cfg.provider == "openai_compatible":
        from app.providers.llm.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(cfg)
    from app.providers.llm.offline import OfflineProvider
    return OfflineProvider()


def build_image(settings: Settings) -> ImageProvider:
    cfg = settings.models.image
    if cfg.provider == "comfyui":
        from app.providers.images.comfyui import ComfyUIProvider
        return ComfyUIProvider(cfg, settings.path("comfyui-workflows"))
    from app.providers.images.placeholder import PlaceholderImageProvider
    return PlaceholderImageProvider()


def build_tts(settings: Settings, voice: VoiceCfg) -> TTSProvider:
    if voice.provider == "flite":
        from app.providers.tts.flite import FliteTTS
        return FliteTTS()
    if voice.provider == "piper":
        from app.providers.tts.piper import PiperTTS
        return PiperTTS(settings.path(settings.languages.tts_models_dir))
    from app.providers.tts.silent import SilentTTS
    return SilentTTS()


def build_publisher(settings: Settings, project_dir: Path) -> Publisher:
    if settings.publishing.provider == "youtube":
        from app.providers.youtube.youtube_api import YouTubeApiPublisher
        return YouTubeApiPublisher(settings.path(settings.publishing.token_file))
    from app.providers.youtube.dry_run import DryRunPublisher
    return DryRunPublisher(project_dir / "publishing")


def build_video(settings: Settings):
    cfg = settings.models.video
    if cfg.provider == "comfyui":
        from app.providers.video.comfyui import ComfyUIVideoProvider
        return ComfyUIVideoProvider(cfg, settings.path("comfyui-workflows"))
    if cfg.provider == "placeholder":
        from app.providers.video.placeholder import PlaceholderVideoProvider
        return PlaceholderVideoProvider()
    from app.providers.video.placeholder import NoVideoProvider
    return NoVideoProvider()
