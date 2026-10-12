"""Database engine and session management.

SQLite for the MVP (zero setup); point storage.database_url at PostgreSQL
for multi-user deployments - no code changes needed.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(settings: Settings) -> Engine:
    global _engine, _SessionLocal
    url = settings.storage.database_url
    connect_args = {}
    if url.startswith("sqlite:///"):
        db_path = url.removeprefix("sqlite:///")
        if not Path(db_path).is_absolute():
            db_path = str(settings.path(db_path))
            url = f"sqlite:///{db_path}"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # The workflow runner writes from a background thread.
        connect_args = {"check_same_thread": False, "timeout": 30}
    _engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")   # readers don't block the writer
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    from app.persistence import models  # noqa: F401  (register tables)
    Base.metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    assert _engine is not None, "init_engine() not called"
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transactional unit of work: commit on success, roll back on error."""
    assert _SessionLocal is not None, "init_engine() not called"
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as s:
        yield s
