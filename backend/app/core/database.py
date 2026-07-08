"""Async SQLAlchemy session management for the application metadata repository."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.get("metadata_repository.url")
        kwargs: dict = {"echo": settings.get("metadata_repository.echo", False)}
        if not url.startswith("sqlite"):
            kwargs["pool_size"] = settings.get("metadata_repository.pool_size", 10)
            kwargs["max_overflow"] = settings.get("metadata_repository.max_overflow", 20)
        _engine = create_async_engine(url, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def init_db() -> None:
    """Create tables on startup (Alembic manages migrations for production)."""
    from app.models.base import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
