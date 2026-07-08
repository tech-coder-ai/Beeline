"""Cache layer: Redis when available, transparent in-memory fallback otherwise."""
from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class _MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = (time.monotonic() + ttl, value)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._store.pop(key, None)

    async def clear_prefix(self, prefix: str) -> None:
        for key in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(key, None)


class Cache:
    """JSON cache with Redis primary and in-memory fallback."""

    def __init__(self) -> None:
        self._redis = None
        self._memory = _MemoryCache()
        self._redis_failed = False

    async def _backend(self):
        settings = get_settings()
        if not settings.get("cache.enabled", True) or self._redis_failed:
            return self._memory
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    settings.get("cache.redis_url"), decode_responses=True,
                    socket_connect_timeout=2,
                )
                await self._redis.ping()
            except Exception as exc:  # noqa: BLE001 - any redis failure falls back
                logger.warning("Redis unavailable, using in-memory cache: %s", exc)
                self._redis_failed = True
                self._redis = None
                return self._memory
        return self._redis

    async def get_json(self, key: str) -> Any | None:
        try:
            backend = await self._backend()
            raw = await backend.get(key)
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        try:
            backend = await self._backend()
            raw = json.dumps(value, default=str)
            if backend is self._memory:
                await backend.set(key, raw, ttl)
            else:
                await backend.set(key, raw, ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.debug("cache set failed for %s: %s", key, exc)

    async def invalidate_prefix(self, prefix: str) -> None:
        try:
            backend = await self._backend()
            if backend is self._memory:
                await backend.clear_prefix(prefix)
            else:
                keys = [k async for k in backend.scan_iter(f"{prefix}*")]
                if keys:
                    await backend.delete(*keys)
        except Exception:  # noqa: BLE001
            pass


cache = Cache()
