"""Configuration loader.

All platform behavior is driven by config/settings.yaml. Values may reference
environment variables with ${VAR_NAME} placeholders, and any key can be
overridden with BEELINE__SECTION__KEY environment variables.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_CONFIG_ENV = "BEELINE_CONFIG"
_OVERRIDE_PREFIX = "BEELINE__"


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _coerce(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _apply_overrides(config: dict) -> None:
    """BEELINE__PIPELINE__CONFIDENCE__CLARIFICATION_THRESHOLD=0.7 style overrides."""
    for key, raw in os.environ.items():
        if not key.startswith(_OVERRIDE_PREFIX):
            continue
        path = [p.lower() for p in key[len(_OVERRIDE_PREFIX):].split("__")]
        node = config
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                break
        else:
            node[path[-1]] = _coerce(raw)


class Settings:
    """Dot-path access over the merged YAML configuration."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, path: str) -> dict:
        value = self.get(path, {})
        return value if isinstance(value, dict) else {}

    @property
    def raw(self) -> dict:
        return self._data

    def reload(self) -> None:
        self._data = _load_config_data()


def _config_path() -> Path:
    override = os.environ.get(_CONFIG_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "config" / "settings.yaml"


def _load_config_data() -> dict:
    path = _config_path()
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data = _expand_env(data)
    _apply_overrides(data)
    return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(_load_config_data())


def persist_connector_definitions(definitions: dict, default_id: str | None = None) -> None:
    """Write connector definitions back to the on-disk settings file."""
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    path = _config_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError as exc:
        logger.warning("Could not read settings file for connector persist: %s", exc)
        return
    connectors = data.setdefault("connectors", {})
    connectors["definitions"] = definitions
    if default_id is not None:
        connectors["default"] = default_id
    try:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except OSError as exc:
        logger.warning("Could not write connector settings to %s: %s", path, exc)
