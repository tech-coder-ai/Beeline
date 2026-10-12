"""Prompt templates live in config/prompts/*.md (versioned with the config, not buried in code)."""
from __future__ import annotations

from pathlib import Path
from string import Template

from app.config import Settings


def render_prompt(settings: Settings, name: str, **values: object) -> str:
    """$placeholders (string.Template) so JSON braces in prompts need no escaping."""
    text = (Path(settings.config_dir) / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).safe_substitute({k: str(v) for k, v in values.items()})
