from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.persistence.db import get_db  # noqa: F401  (re-export)


def settings_dep() -> Settings:
    return get_settings()


def wake_runner(request: Request) -> None:
    runner = getattr(request.app.state, "runner", None)
    if runner is not None:
        runner.wake()


def get_or_404(db: Session, model, obj_id: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} not found")
    return obj
