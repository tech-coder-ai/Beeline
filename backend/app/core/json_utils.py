"""Helpers for values that must be stored in JSON columns or API payloads."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def json_safe(value: Any) -> Any:
    """Convert a single value to a JSON-serializable form."""
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, UUID):
        return str(value)
    return value


def json_safe_tree(value: Any) -> Any:
    """Recursively convert dicts/lists to JSON-serializable structures."""
    if isinstance(value, dict):
        return {k: json_safe_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe_tree(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe_tree(v) for v in value]
    return json_safe(value)
